#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
notion_oauth.py -- OAuth client for Notion's hosted MCP (https://mcp.notion.com/mcp).

The fallback transport for a workspace where an admin has disabled member-created
integrations, which is what blocks the local server's NOTION_TOKEN path. OAuth
authorizes the USER rather than an integration, so no integration has to exist.

Notion's authorization server advertises dynamic client registration (RFC 7591)
and refresh_token grants, so this registers itself once, runs one browser consent,
then refreshes silently -- no repeat browser flow every 8 hours.

Usage: notion_oauth.py login <account> [--no-browser]
       notion_oauth.py status <account>
       notion_oauth.py logout <account>
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AS_BASE = "https://mcp.notion.com"
RESOURCE = "https://mcp.notion.com/mcp"
DISCOVERY = f"{AS_BASE}/.well-known/oauth-authorization-server"

# Registered at DCR time, so it must be stable across logins and refreshes.
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"
CDP_PORT = 9222              # the debug-profile Chrome that holds the Notion session

# Cloudflare fronts mcp.notion.com and 403s the default Python-urllib agent, so
# every request here carries a browser-shaped one.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

CACHE_DIR = Path.home() / ".config" / "notion" / "oauth"
CONSENT_TIMEOUT = 300  # seconds to wait for the browser consent to come back
REFRESH_SKEW = 120     # refresh this many seconds before the token actually expires


# -- small HTTP helpers --------------------------------------------------------

def _send(req: urllib.request.Request, what: str) -> dict:
    """Run a request and parse JSON, turning transport faults into plain messages.

    urllib raises URLError for DNS/TLS/offline, which would otherwise surface as a
    traceback in the middle of an interactive consent flow.
    """
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as e:
        sys.exit(f"{what}: cannot reach {AS_BASE} ({e.reason}).")
    try:
        return json.loads(raw)
    except ValueError:
        sys.exit(f"{what}: response was not JSON: {raw[:300]}")


def _post_json(url: str, payload: dict) -> dict:
    return _send(urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": USER_AGENT}), "registration")


def _post_form(url: str, form: dict) -> dict:
    return _send(urllib.request.Request(
        url, data=urllib.parse.urlencode(form).encode(), method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json", "User-Agent": USER_AGENT}), "token endpoint")


def _get_json(url: str) -> dict:
    return _send(urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}),
        "discovery")


def _require_token(payload: dict, what: str) -> dict:
    """A 200 carrying {"error": ...} must not be cached as if it were a token."""
    if not isinstance(payload, dict) or not payload.get("access_token"):
        err = (payload or {}).get("error", "no access_token in response")
        desc = (payload or {}).get("error_description", "")
        sys.exit(f"{what} returned no access token: {err} {desc}".rstrip())
    return payload


def _http_error_detail(e: urllib.error.HTTPError) -> str:
    try:
        return f"{e.code} {e.read().decode()[:400]}"
    except Exception:
        return str(e.code)


# -- token cache ---------------------------------------------------------------

def cache_path(account: str) -> Path:
    return CACHE_DIR / f"{account}.json"


def load_cache(account: str) -> dict:
    p = cache_path(account)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except ValueError:
        return {}


def save_cache(account: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    p = cache_path(account)
    # Created 0600 up front: writing then chmod'ing leaves the bearer token and
    # client secret world-readable for the window in between.
    fd = os.open(p, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)


# -- OAuth mechanics -----------------------------------------------------------

def discover() -> dict:
    return _get_json(DISCOVERY)


def register_client(meta: dict) -> dict:
    """Dynamic client registration -- no pre-provisioned app needed."""
    endpoint = meta.get("registration_endpoint")
    if not endpoint:
        sys.exit("Notion's OAuth metadata advertises no registration_endpoint.")
    reg = _post_json(endpoint, {
        "client_name": "use-notion (Claude Code)",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
        "scope": "default",
    })
    if not reg.get("client_id"):
        sys.exit(f"Registration returned no client_id: {json.dumps(reg)[:300]}")
    return reg


def _open_callback_server() -> http.server.HTTPServer:
    """Bind the loopback listener, naming the conflict when the port is taken.

    The port is fixed because it is baked into the redirect_uri at registration
    time, so a stale holder is a real blocker rather than something to route around.
    """
    try:
        return http.server.HTTPServer((CALLBACK_HOST, CALLBACK_PORT), _CallbackHandler)
    except OSError as e:
        sys.exit(f"Cannot listen on {CALLBACK_HOST}:{CALLBACK_PORT} ({e.strerror}).\n"
                 f"The redirect URI is registered against that exact port. Free it "
                 f"(lsof -ti:{CALLBACK_PORT}) and retry.")


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        q = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.result = {k: v[0] for k, v in q.items()}
        ok = "code" in _CallbackHandler.result
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = ("Authorized. You can close this tab and return to the terminal."
               if ok else
               f"Authorization failed: {_CallbackHandler.result.get('error', 'unknown')}")
        self.wfile.write(f"<html><body style='font:16px system-ui;padding:3rem'>"
                         f"<p>{msg}</p></body></html>".encode())

    def log_message(self, *a):  # silence the default stderr access log
        pass


def _open_in_browser(url: str, use_browser: bool) -> None:
    """Open the consent URL in the debug-profile Chrome, else the default browser.

    The consent screen only works in a profile already signed in to Notion, and
    that is the CDP profile -- the default browser is usually a different one, so
    try the debug port first.
    """
    if not use_browser:
        return
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{CDP_PORT}/json/new?{url}", method="PUT")
        with urllib.request.urlopen(req, timeout=5):
            return
    except Exception:
        pass
    opener = shutil.which("open")
    if opener:
        subprocess.run([opener, url], check=False)


def login(account: str, use_browser: bool = True) -> dict:
    meta = discover()
    cache = load_cache(account)

    client = cache.get("client")
    if not client or not client.get("client_id"):
        try:
            client = register_client(meta)
        except urllib.error.HTTPError as e:
            sys.exit(f"Dynamic client registration failed: {_http_error_detail(e)}")
        cache["client"] = client

    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": REDIRECT_URI,
        "scope": "default",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    }
    auth_url = f"{meta['authorization_endpoint']}?{urllib.parse.urlencode(params)}"

    _CallbackHandler.result = {}
    server = _open_callback_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # flush: the wait below blocks, so a buffered stdout would hide the URL from
    # anyone piping this (or driving it from an agent) until the flow timed out.
    print(f"Open this URL to authorize (it should open by itself):\n\n  {auth_url}\n",
          flush=True)
    _open_in_browser(auth_url, use_browser)

    deadline = time.monotonic() + CONSENT_TIMEOUT
    while not _CallbackHandler.result and time.monotonic() < deadline:
        time.sleep(0.4)
    server.shutdown()
    server.server_close()  # shutdown() only stops the loop; the port stays bound

    res = _CallbackHandler.result
    if not res:
        sys.exit(f"No callback within {CONSENT_TIMEOUT}s. Re-run `login` and complete "
                 "the consent screen in the browser.")
    if "code" not in res:
        sys.exit(f"Authorization denied: {res.get('error')} "
                 f"{res.get('error_description', '')}\n"
                 "If this says the workspace forbids it, an admin has blocked "
                 "third-party/AI connectors and this transport is unavailable.")
    if res.get("state") != state:
        sys.exit("State mismatch on the OAuth callback -- aborting rather than "
                 "trusting the response.")

    form = {
        "grant_type": "authorization_code",
        "code": res["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client["client_id"],
        "code_verifier": verifier,
        "resource": RESOURCE,
    }
    if client.get("client_secret"):
        form["client_secret"] = client["client_secret"]
    try:
        tok = _require_token(_post_form(meta["token_endpoint"], form), "Token exchange")
    except urllib.error.HTTPError as e:
        sys.exit(f"Token exchange failed: {_http_error_detail(e)}")

    cache["token"] = tok
    cache["obtained_at"] = int(time.time())
    save_cache(account, cache)
    return cache


def refresh(account: str, cache: dict) -> dict:
    meta = discover()
    client, tok = cache.get("client", {}), cache.get("token", {})
    if not tok.get("refresh_token"):
        sys.exit(f"Account {account!r} has no refresh token. Run:\n"
                 f"  notion_oauth.py login {account}")
    form = {
        "grant_type": "refresh_token",
        "refresh_token": tok["refresh_token"],
        "client_id": client.get("client_id", ""),
        "resource": RESOURCE,
    }
    if client.get("client_secret"):
        form["client_secret"] = client["client_secret"]
    try:
        new = _require_token(_post_form(meta["token_endpoint"], form), "Refresh")
    except urllib.error.HTTPError as e:
        sys.exit(f"Refresh failed ({_http_error_detail(e)}). Run:\n"
                 f"  notion_oauth.py login {account}")
    # Notion may omit the refresh token on refresh; keep the existing one.
    new.setdefault("refresh_token", tok["refresh_token"])
    cache["token"] = new
    cache["obtained_at"] = int(time.time())
    save_cache(account, cache)
    return cache


def access_token(account: str) -> str:
    """Return a live bearer token, refreshing when it is close to expiry."""
    cache = load_cache(account)
    tok = cache.get("token")
    if not tok:
        sys.exit(f"Account {account!r} is not authorized for the hosted transport.\n"
                 f"Run: notion_oauth.py login {account}")
    expires_in = tok.get("expires_in")
    if expires_in:
        age = time.time() - cache.get("obtained_at", 0)
        if age > (expires_in - REFRESH_SKEW):
            cache = refresh(account, cache)
            tok = cache["token"]
    if not tok.get("access_token"):
        sys.exit(f"Account {account!r} has a cached entry with no access token. Run:\n"
                 f"  notion_oauth.py login {account}")
    return tok["access_token"]


def status(account: str) -> None:
    cache = load_cache(account)
    if not cache:
        print(f"{account}: not authorized (no cache at {cache_path(account)})")
        return
    tok = cache.get("token", {})
    client = cache.get("client", {})
    print(f"{account}:")
    print(f"  client_id:     {client.get('client_id', '(none)')}")
    print(f"  has token:     {bool(tok.get('access_token'))}")
    print(f"  has refresh:   {bool(tok.get('refresh_token'))}")
    if tok.get("expires_in") and cache.get("obtained_at"):
        left = int(cache["obtained_at"] + tok["expires_in"] - time.time())
        print(f"  expires in:    {left}s" + ("  (will refresh on next call)"
                                             if left < REFRESH_SKEW else ""))
    print(f"  cache:         {cache_path(account)}")


def main() -> None:
    p = argparse.ArgumentParser(prog="notion_oauth.py",
                                description="OAuth for Notion's hosted MCP.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("login", help="Run the browser consent and cache the tokens.")
    s.add_argument("account")
    s.add_argument("--no-browser", action="store_true",
                   help="Print the URL instead of opening it.")
    s = sub.add_parser("status", help="Show cached authorization state.")
    s.add_argument("account")
    s = sub.add_parser("logout", help="Delete the cached tokens.")
    s.add_argument("account")
    args = p.parse_args()

    if args.cmd == "login":
        login(args.account, use_browser=not args.no_browser)
        print()
        status(args.account)
    elif args.cmd == "status":
        status(args.account)
    elif args.cmd == "logout":
        cache_path(args.account).unlink(missing_ok=True)
        print(f"{args.account}: cached tokens removed")


if __name__ == "__main__":
    main()
