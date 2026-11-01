#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "cryptography==49.0.0",
#     "requests==2.34.2",
#     "websocket-client==1.9.0",
# ]
# ///
"""
slack.py — personal Slack transport + interactive CLI for the /use-slack skill.

This file is the single source of truth for talking to Slack from a personal
machine. It does two jobs:

  1. TRANSPORT (importable). Everything from `# ─── TRANSPORT ───` down to the
     end of `CdpClient` is the proven Slack-over-CDP path: extract one xoxc
     token per workspace + the shared `d` session cookie from the live Slack
     desktop app, then route every API call through Slack's own Electron
     renderer via Chrome DevTools Protocol. This is the ONLY known way to reach
     Enterprise Grid workspaces — the public endpoints return
     `enterprise_is_restricted`, but the internal ones the desktop client uses
     succeed when the call originates from inside the Slack-signed renderer.

  2. CLI (interactive). The subcommands — read, thread, search, find-channel,
     find-user, list-dms, send, raw — build ad-hoc operations on top of the
     transport. One CdpClient drives every signed-in workspace by varying the
     `token` form field per call (the renderer origin satisfies the policy
     filter; the token scopes to the right workspace).

Auth is extracted live from the debug-profile Slack's local state on every run
— no bot tokens, no app install, nothing to manage. Slack desktop must be
installed; the script launches its own instance on SLACK_PROFILE on demand.

Read endpoints are unrestricted. `send` is gated behind --yes (and offers
--dry-run), and `raw` requires --yes for any method outside a read-only
allowlist (see cmd_raw) so it can't fire chat.postMessage / chat.delete /
conversations.invite from automation. Confirm with the human before writing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
import websocket

# chromium_cookies does the AES decrypt via `cryptography` when importable (this
# script's uv env pins it in the deps above) else the openssl CLI. cryptography
# stays in the deps for that fast path even though it is no longer imported
# here directly.
from chromium_cookies import CookieDecryptError, decrypt_cookie, derive_key  # noqa: E402


# ════════════════════════════════════════════════════════════════════════
# TRANSPORT — the CDP transport layer for the /use-slack CLI. Kept import-safe
# (no side effects at module load).
# ════════════════════════════════════════════════════════════════════════

SLACK_PROFILE = Path.home() / ".slack-debug-profile"
COOKIES_FILE = SLACK_PROFILE / "Cookies"
ROOT_STATE_FILE = SLACK_PROFILE / "storage" / "root-state.json"
LAUNCH_LOG = SLACK_PROFILE / "debug-launch.log"
SLACK_APP_PATH = "/Applications/Slack.app"

# Tokens come from /ssb/redirect HTML responses. The body embeds several
# xoxc-... refs; the one we want is the workspace's bootstrap api_token.
XOXC_RE = re.compile(r"xoxc-[0-9A-Za-z-]{20,}")
SSB_API_TOKEN_RE = re.compile(r'"api_token"\s*:\s*"(xoxc-[^"]+)"')

API_BASE = "https://slack.com/api"
CDP_PORT = 9229
# Policy-blocked workspaces report these from public endpoints. We work around
# them via CDP (calls from inside the renderer aren't blocked); seeing one of
# these means CDP wasn't actually used.
POLICY_BLOCKED_ERRORS = {"enterprise_is_restricted", "not_allowed_token_type"}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Slack/4.45.69 Chrome/130.0.6723.137 Electron/33.4.11 Safari/537.36 "
    "Slack_SSB/4.45.69"
)


class SlackChannelError(Exception):
    """A failure that should fail-loud the Slack transport."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ─── Slack desktop lifecycle (CDP debug port self-bootstrap) ───────────
#
# Slack 4.53+ refuses --remote-debugging-port on the default profile, so the
# transport runs its own instance on SLACK_PROFILE beside the everyday one,
# which it never touches. Launched on demand; Cmd+Q is respected between runs.

NOT_SIGNED_IN = (
    f"slack_debug_profile_not_signed_in: sign in to your workspaces in the debug "
    f"Slack window (profile {SLACK_PROFILE}), then retry; any command but "
    f"discover opens that window"
)


def _debug_instance_running() -> bool:
    try:
        subprocess.run(
            ["/usr/bin/pgrep", "-f", f"user-data-dir={SLACK_PROFILE}"],
            check=True, capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _cdp_targets() -> list[dict[str, Any]] | None:
    """The debug port's targets, or None when nothing answers on it."""
    try:
        r = requests.get(f"http://localhost:{CDP_PORT}/json", timeout=2)
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def _is_workspace_page(t: dict[str, Any]) -> bool:
    # The signed-out window is also on app.slack.com (/ssb/first, /ssb/signin).
    u = urlparse(t.get("url") or "")
    return t.get("type") == "page" and u.netloc == "app.slack.com" and u.path.startswith("/client")


def _cdp_has_slack_page() -> bool:
    return any(_is_workspace_page(t) for t in _cdp_targets() or [])


def _profile_has_workspaces() -> bool:
    try:
        return bool(json.loads(ROOT_STATE_FILE.read_text()).get("workspaces"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def _launch_slack_with_debug() -> subprocess.Popen:
    SLACK_PROFILE.mkdir(parents=True, exist_ok=True)
    with open(LAUNCH_LOG, "wb") as log:
        return subprocess.Popen(
            [
                f"{SLACK_APP_PATH}/Contents/MacOS/Slack",
                f"--user-data-dir={SLACK_PROFILE}",
                f"--remote-debugging-port={CDP_PORT}",
            ],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _launch_failure() -> str:
    try:
        lines = LAUNCH_LOG.read_text(errors="replace").strip().splitlines()
    except OSError:
        lines = []
    return f"slack_debug_launch_exited: {lines[-1] if lines else 'no output'} (log {LAUNCH_LOG})"


def _ensure_slack_cdp_ready() -> None:
    """Ensure the debug-profile Slack is up on CDP with a workspace page loaded.

    Reuses a running debug instance, launches one otherwise, and polls up to
    60s. A profile with no workspaces fails as soon as its window is up.
    """
    if _cdp_has_slack_page():
        return
    if not Path(SLACK_APP_PATH).exists():
        raise SlackChannelError("slack_app_not_installed")
    proc = None
    if not _debug_instance_running():
        print(f"[slack] launching debug Slack on {SLACK_PROFILE}", file=sys.stderr)
        proc = _launch_slack_with_debug()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        targets = _cdp_targets()
        if targets is not None:
            if any(_is_workspace_page(t) for t in targets):
                return
            if any(t.get("type") == "page" for t in targets) and not _profile_has_workspaces():
                raise SlackChannelError(NOT_SIGNED_IN)
        if proc is not None and proc.poll() is not None:
            raise SlackChannelError(_launch_failure())
        time.sleep(1.0)
    raise SlackChannelError("slack_cdp_not_ready_within_timeout")


@dataclass
class WorkspaceAuth:
    team_id: str
    team_domain: str
    team_name: str
    user_id: str
    xoxc_token: str
    d_cookie: str
    enterprise_id: str | None = None


# ─── Token / cookie discovery from Slack desktop ───────────────────────


def _check_slack_installed() -> None:
    if not Path(SLACK_APP_PATH).exists():
        raise SlackChannelError("slack_desktop_not_installed")
    if not ROOT_STATE_FILE.exists():
        raise SlackChannelError(NOT_SIGNED_IN)
    if not COOKIES_FILE.exists():
        raise SlackChannelError("slack_cookies_db_missing")


def _snapshot_cookies_db() -> Path:
    """Copy Cookies sqlite to tempdir to dodge Slack's writer-locks."""
    tmp = Path(tempfile.mkdtemp(prefix="use-slack-"))
    shutil.copy2(COOKIES_FILE, tmp / "Cookies")
    return tmp / "Cookies"


def _get_keychain_password() -> bytes:
    """Read 'Slack Safe Storage' password from the macOS Login keychain.
    May prompt the first time; subsequent runs use the cached ACL approval."""
    try:
        out = subprocess.check_output(
            ["security", "find-generic-password", "-s", "Slack Safe Storage", "-w"],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="replace").strip()
        raise SlackChannelError(f"keychain_read_failed: {err!r}")
    return out.strip()


def _decrypt_cookie_value(encrypted_value: bytes, key: bytes, host_key: str) -> str:
    """Chromium-style AES-128-CBC decrypt for cookie values (v10/v11 prefix).

    Delegates to the sibling chromium_cookies module (v10/v11, PKCS7 pad
    validation, conditional SHA256(host_key) prefix strip).
    """
    if not encrypted_value:
        raise SlackChannelError("d_cookie_empty")
    try:
        return decrypt_cookie(encrypted_value, key, host_key)
    except CookieDecryptError as e:
        raise SlackChannelError(f"d_cookie_decrypt_failed: {e}")


def _extract_d_cookie(cookies_db: Path) -> str:
    keychain_password = _get_keychain_password()
    key = derive_key(keychain_password)
    conn = sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT host_key, encrypted_value FROM cookies "
            "WHERE host_key='.slack.com' AND name='d' LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise SlackChannelError("d_cookie_not_in_db")
    return _decrypt_cookie_value(row[1], key, row[0])


def _read_workspaces_meta() -> list[dict[str, Any]]:
    """Parse root-state.json to get every workspace the user is signed into.
    Returns [{id, name, domain, url, order}, ...] in sidebar order."""
    try:
        data = json.loads(ROOT_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SlackChannelError(f"root_state_unreadable:{e}")
    workspaces = data.get("workspaces", {}) or {}
    out: list[dict[str, Any]] = []
    for tid, meta in workspaces.items():
        if not isinstance(meta, dict):
            continue
        out.append({
            "id": meta.get("id") or tid,
            "name": meta.get("name") or tid,
            "domain": meta.get("domain") or "unknown",
            "url": (meta.get("url") or "").rstrip("/"),
            "order": meta.get("order", 999),
        })
    out.sort(key=lambda w: w["order"])
    return out


def _fetch_xoxc_via_ssb_redirect(workspace_url: str, d_cookie: str) -> str:
    """GET <workspace_url>/ssb/redirect with the d cookie; Slack returns an
    HTML+JS bootstrap page whose body embeds an `api_token` field carrying the
    workspace's xoxc-... token (one per grid workspace). Status is typically
    403 but the body still contains the token."""
    if not workspace_url:
        raise SlackChannelError("workspace_url_missing")
    url = f"{workspace_url}/ssb/redirect"
    try:
        r = _http_session().get(
            url,
            headers={"Cookie": f"d={d_cookie}", "User-Agent": USER_AGENT},
            timeout=20,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        raise SlackChannelError(f"ssb_request_failed:{type(e).__name__}:{e}")
    m = SSB_API_TOKEN_RE.search(r.text)
    if m:
        return m.group(1)
    fallback = XOXC_RE.findall(r.text)
    if fallback:
        return fallback[0]
    raise SlackChannelError(f"xoxc_not_in_ssb_body:status={r.status_code}")


def discover_workspaces() -> list[WorkspaceAuth]:
    """Return one WorkspaceAuth per workspace the user is signed into in Slack
    desktop. Source of truth is root-state.json; per-workspace xoxc is fetched
    on demand via /ssb/redirect using the shared d cookie.

    Per-workspace failures (xoxc fetch) are logged and dropped rather than
    raising — a single dead workspace shouldn't kill the others.
    """
    _check_slack_installed()
    snapshot = _snapshot_cookies_db()
    try:
        d_cookie = _extract_d_cookie(snapshot)
    finally:
        shutil.rmtree(snapshot.parent, ignore_errors=True)

    workspaces_meta = _read_workspaces_meta()
    if not workspaces_meta:
        raise SlackChannelError("no_workspaces_in_root_state")

    out: list[WorkspaceAuth] = []
    for meta in workspaces_meta:
        try:
            token = _fetch_xoxc_via_ssb_redirect(meta["url"], d_cookie)
        except SlackChannelError as e:
            print(f"[slack/{meta['domain']}] xoxc fetch failed: {e.reason}", file=sys.stderr)
            continue
        out.append(WorkspaceAuth(
            team_id=meta["id"],
            team_domain=meta["domain"],
            team_name=meta["name"],
            user_id="",  # populated from client.userBoot.self on demand
            xoxc_token=token,
            d_cookie=d_cookie,
            enterprise_id=None,
        ))
    return out


# ─── HTTP session (for /ssb/redirect token discovery only) ─────────────


_session: requests.Session | None = None


def _http_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        _session = s
    return _session


# ─── CDP client — bridges Python to Slack desktop's renderer ───────────
#
# All real Slack API calls go through here. Each call is a `fetch()` invoked
# via `Runtime.evaluate` inside Slack's renderer. From Slack's server's
# perspective the request originates from `app.slack.com` inside a Slack-signed
# Electron renderer, which is what the enterprise policy requires. The xoxc
# token in the form body scopes to the right workspace — so ONE connected
# client can serve every workspace by varying the token argument.


class CdpClient:
    """One persistent WebSocket connection to a Slack page target."""

    def __init__(self) -> None:
        self._mid = 0
        self._ws: websocket.WebSocket | None = None
        self._target_url = ""

    def connect(self) -> None:
        """Locate a Slack page target on the debug port and open a WS."""
        _ensure_slack_cdp_ready()
        try:
            targets = requests.get(
                f"http://localhost:{CDP_PORT}/json", timeout=3,
            ).json()
        except requests.RequestException as e:
            raise SlackChannelError(f"cdp_unreachable: {type(e).__name__}:{e}")
        pages = [t for t in targets if _is_workspace_page(t)]
        if not pages:
            raise SlackChannelError("no_slack_page_in_cdp")
        target = pages[0]
        self._target_url = target.get("url", "")
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            raise SlackChannelError("cdp_target_missing_ws_url")
        try:
            # Chromium's DevTools endpoint rejects any Origin that is not
            # allowlisted via --remote-allow-origins. websocket-client would
            # otherwise derive one from the URL, so suppress it entirely.
            self._ws = websocket.create_connection(
                ws_url, timeout=20, suppress_origin=True,
            )
        except Exception as e:
            raise SlackChannelError(f"cdp_ws_connect_failed:{type(e).__name__}:{e}")

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    @property
    def target_url(self) -> str:
        return self._target_url

    def _eval(self, expression: str) -> Any:
        """Run JS in the renderer, await promise resolution, return JSON value."""
        assert self._ws is not None, "CdpClient not connected"
        self._mid += 1
        my_id = self._mid
        req = {
            "id": my_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }
        self._ws.send(json.dumps(req))
        # Drain frames until we see our id (CDP can interleave events).
        while True:
            try:
                raw = self._ws.recv()
            except Exception as e:
                raise SlackChannelError(f"cdp_ws_recv_failed:{type(e).__name__}:{e}")
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("id") != my_id:
                continue  # ignore event frames
            err = msg.get("error")
            if err:
                raise SlackChannelError(f"cdp_eval_error:{err.get('message','?')}")
            result = msg.get("result", {}).get("result", {})
            if result.get("subtype") == "error":
                raise SlackChannelError(f"cdp_runtime_error:{result.get('description','?')}")
            return result.get("value")

    def slack_api(self, path: str, token: str, **params: Any) -> dict[str, Any]:
        """POST to a Slack API path from inside the renderer. Returns parsed JSON.

        `path` is a /api/<method> path. We pass the xoxc as the `token` form
        field (Slack accepts this in lieu of the Authorization header; matches
        what the desktop client does). Handles 429 + ratelimited with backoff.
        """
        params_with_token = {"token": token, **{k: str(v) for k, v in params.items()}}
        js_params = json.dumps(params_with_token)
        path_js = json.dumps(path)
        js = (
            "(async () => {"
            "  const p = " + js_params + ";"
            "  const fd = new FormData();"
            "  for (const [k,v] of Object.entries(p)) fd.append(k, v);"
            "  for (let attempt = 0; attempt < 4; attempt++) {"
            "    const r = await fetch(" + path_js + ", {method:'POST', body: fd, credentials:'include'});"
            "    if (r.status === 429) {"
            "      const wait = parseInt(r.headers.get('Retry-After') || '2', 10);"
            "      await new Promise(res => setTimeout(res, Math.min(wait, 30) * 1000));"
            "      continue;"
            "    }"
            "    const txt = await r.text();"
            "    let body;"
            "    try { body = JSON.parse(txt); } catch (e) { return {ok:false, error:'non_json_response:' + r.status}; }"
            "    if (!body.ok && body.error === 'ratelimited') {"
            "      await new Promise(res => setTimeout(res, (1 << attempt) * 1000));"
            "      continue;"
            "    }"
            "    return body;"
            "  }"
            "  return {ok:false, error:'exceeded_max_retries'};"
            "})()"
        )
        val = self._eval(js)
        if not isinstance(val, dict):
            return {"ok": False, "error": f"cdp_unexpected_value:{type(val).__name__}"}
        return val


# ─── Shared formatting helpers ──────


def _ts_to_iso(ts: str | float) -> str:
    """Slack timestamps are 'sssssssssss.uuuuuu' floats since epoch."""
    f = float(ts) if isinstance(ts, str) else ts
    return datetime.fromtimestamp(f, tz=timezone.utc).isoformat()


def _construct_permalink(team_domain: str, channel_id: str, ts: str, thread_ts: str | None) -> str:
    """Build a Slack permalink without an API round-trip. Slack's format is
    deterministic: <workspace>.slack.com/archives/<CID>/p<ts_no_dot>."""
    ts_compact = ts.replace(".", "")
    base = f"https://{team_domain}.slack.com/archives/{channel_id}/p{ts_compact}"
    if thread_ts and thread_ts != ts:
        return f"{base}?thread_ts={thread_ts}&cid={channel_id}"
    return base


def _harvest_users(*payloads: dict[str, Any]) -> dict[str, str]:
    """Extract uid -> display-name from any response that embeds a `users` /
    `bots` array. Cheaper than separate users.info calls. Skips non-dict
    entries (enterprise search sometimes embeds bare id strings)."""
    out: dict[str, str] = {}
    for p in payloads:
        if not isinstance(p, dict):
            continue
        for u in (p.get("users") or []):
            if not isinstance(u, dict):
                continue
            uid = u.get("id")
            if not uid:
                continue
            profile = u.get("profile", {}) or {}
            if not isinstance(profile, dict):
                profile = {}
            out[uid] = (profile.get("display_name") or profile.get("real_name")
                        or u.get("name") or uid)
        for b in (p.get("bots") or []):
            if not isinstance(b, dict):
                continue
            bid = b.get("id")
            if bid:
                out[bid] = b.get("name") or bid
    return out


def _channel_label(conv: dict[str, Any], user_names: dict[str, str]) -> str:
    """Human-readable label for a conversation."""
    if conv.get("is_im"):
        return f"DM:{user_names.get(conv.get('user', ''), '?')}"
    if conv.get("is_mpim"):
        return conv.get("name") or "group-dm"
    return f"#{conv.get('name', '?')}"


# ════════════════════════════════════════════════════════════════════════
# CLI — interactive Slack operations built on the transport above.
# ════════════════════════════════════════════════════════════════════════

SPILL_DIR = Path.home() / ".cache" / "slack-cm"
INLINE_LIMIT = 4000          # chars; larger output spills to a file
PREVIEW_CHARS = 1500         # chars shown inline when output spills
ID_RE = re.compile(r"^[CDG][A-Z0-9]{6,}$")   # channel / DM / group-DM id


def _emit(label: str, text: str) -> None:
    """Print small output inline; spill large output to a temp file + preview."""
    if len(text) <= INLINE_LIMIT:
        print(text)
        return
    SPILL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = SPILL_DIR / f"{stamp}-{label}.txt"
    path.write_text(text)
    print(text[:PREVIEW_CHARS])
    print(f"\n[... truncated. Full output ({len(text)} chars): {path} ]")


def _connect() -> tuple[list[WorkspaceAuth], CdpClient]:
    """Open one shared CDP client and discover signed-in workspaces."""
    cdp = CdpClient()
    cdp.connect()
    workspaces = discover_workspaces()
    if not workspaces:
        raise SlackChannelError("no_workspaces_available")
    return workspaces, cdp


def _scope(workspaces: list[WorkspaceAuth], want: str | None) -> list[WorkspaceAuth]:
    """All workspaces, or just the one matching `want` (by domain or name)."""
    if not want:
        return workspaces
    w = want.lower()
    hits = [a for a in workspaces
            if a.team_domain.lower() == w or a.team_name.lower() == w]
    if not hits:
        avail = ", ".join(a.team_domain for a in workspaces)
        raise SlackChannelError(f"workspace_not_found:{want} (have: {avail})")
    return hits


def _pick_workspace(workspaces: list[WorkspaceAuth], want: str | None) -> WorkspaceAuth:
    """Pick exactly one workspace for id-based ops (thread/raw)."""
    if want:
        return _scope(workspaces, want)[0]
    if len(workspaces) == 1:
        return workspaces[0]
    avail = ", ".join(a.team_domain for a in workspaces)
    raise SlackChannelError(f"ambiguous_workspace: pass --workspace (have: {avail})")


def _bootstrap_conversations(
    cdp: CdpClient, auth: WorkspaceAuth,
) -> tuple[list[dict[str, Any]], dict[str, str], str]:
    """client.userBoot → (conversations, uid->name seed, self_id)."""
    boot = cdp.slack_api("/api/client.userBoot", auth.xoxc_token, flannel_api_ver="4")
    if not boot.get("ok"):
        raise SlackChannelError(f"client.userBoot_failed:{boot.get('error','?')}")
    self_obj = boot.get("self") or {}
    self_id = (self_obj.get("id") if isinstance(self_obj, dict) else "") or ""
    if self_id and not auth.user_id:
        auth.user_id = self_id

    def _list(key: str) -> list[dict[str, Any]]:
        v = boot.get(key)
        return v if isinstance(v, list) else []

    channels = _list("channels")
    groups = _list("groups")     # legacy private channels
    ims = _list("ims")           # 1:1 DMs
    mpims = _list("mpims")       # group DMs
    for im in ims:
        if isinstance(im, dict):
            im.setdefault("is_im", True)
    for mp in mpims:
        if isinstance(mp, dict):
            mp.setdefault("is_mpim", True)
    convs_by_id: dict[str, dict[str, Any]] = {}
    for c in channels + groups + ims + mpims:
        if isinstance(c, dict) and c.get("id"):
            convs_by_id[c["id"]] = c
    return list(convs_by_id.values()), _harvest_users(boot), self_id


def _resolve_channel(
    convs: list[dict[str, Any]], user_names: dict[str, str], ref: str,
) -> tuple[str | None, str]:
    """Resolve a #name / name / Cxxxx ref to (channel_id, label) within one
    workspace's known conversations. Returns (None, ref) if unresolved."""
    r = ref.strip()
    if ID_RE.match(r):
        for c in convs:
            if c.get("id") == r:
                return r, _channel_label(c, user_names)
        return r, r  # raw id, not in this workspace's boot list
    name = r.lstrip("#").lower()
    partial: list[dict[str, Any]] = []
    for c in convs:
        if c.get("is_im"):
            pname = user_names.get(c.get("user", ""), "").lower()
            if pname and name in pname:
                partial.append(c)
            continue
        cn = (c.get("name") or "").lower()
        if cn == name:
            return c["id"], _channel_label(c, user_names)
        if name and name in cn:
            partial.append(c)
    if partial:
        return partial[0]["id"], _channel_label(partial[0], user_names)
    return None, ref


def _resolve_for(
    cdp: CdpClient, workspaces: list[WorkspaceAuth], ref: str, want: str | None,
):
    """Find which workspace owns `ref` and resolve it. Returns
    (auth, convs, user_names, self_id, channel_id, label)."""
    targets = _scope(workspaces, want)
    id_like = bool(ID_RE.match(ref.strip()))
    fallback = None
    for auth in targets:
        convs, names, self_id = _bootstrap_conversations(cdp, auth)
        cid, label = _resolve_channel(convs, names, ref)
        if cid and any(c.get("id") == cid for c in convs):
            return auth, convs, names, self_id, cid, label
        if id_like and fallback is None:
            fallback = (auth, convs, names, self_id, ref, ref)
    if id_like and fallback is not None:
        # Raw id not present in any boot list; best-effort on the first target
        # (correct when --workspace was given, since targets is then size 1).
        return fallback
    raise SlackChannelError(f"channel_not_found:{ref}")


def _parse_permalink(url: str) -> dict[str, Any]:
    """Pull workspace domain, channel id, message ts, and thread_ts out of a
    Slack archives permalink."""
    u = urlparse(url)
    domain = (u.netloc or "").split(".")[0]
    parts = [p for p in u.path.split("/") if p]   # ['archives', 'C...', 'p169...']
    if len(parts) < 3 or parts[0] != "archives":
        raise SlackChannelError(f"unrecognized_permalink:{url}")
    channel = parts[1]
    praw = parts[2]
    digits = praw[1:] if praw.startswith("p") else praw
    ts = f"{digits[:-6]}.{digits[-6:]}" if len(digits) > 6 else digits
    thread_ts = parse_qs(u.query).get("thread_ts", [None])[0]
    return {"domain": domain, "channel": channel, "ts": ts, "thread_ts": thread_ts}


def _fmt_messages(
    msgs: list[dict[str, Any]], user_names: dict[str, str],
    team_domain: str, channel_id: str,
) -> str:
    lines: list[str] = []
    for m in sorted(msgs, key=lambda x: float(x.get("ts", "0") or 0)):
        ts = m.get("ts")
        sender = m.get("user") or m.get("bot_id") or "?"
        who = user_names.get(sender, m.get("username") or sender)
        when = _ts_to_iso(ts) if ts else "?"
        text = (m.get("text") or "").strip()
        link = _construct_permalink(team_domain, channel_id, ts, m.get("thread_ts")) if ts else ""
        lines.append(f"[{when}] {who}: {text}\n    {link}")
    return "\n".join(lines) if lines else "(no messages)"


# ─── Subcommands ───────────────────────────────────────────────────────


def cmd_read(args: argparse.Namespace) -> int:
    workspaces, cdp = _connect()
    try:
        auth, convs, names, _self, cid, label = _resolve_for(
            cdp, workspaces, args.channel, args.workspace)
        params: dict[str, Any] = {"channel": cid, "count": str(args.limit)}
        if args.oldest:
            params["oldest"] = args.oldest
        resp = cdp.slack_api("/api/conversations.view", auth.xoxc_token, **params)
        if not resp.get("ok"):
            hist_params: dict[str, Any] = {"channel": cid, "limit": str(args.limit)}
            if args.oldest:
                hist_params["oldest"] = args.oldest
            resp = cdp.slack_api("/api/conversations.history", auth.xoxc_token, **hist_params)
        if not resp.get("ok"):
            print(f"error: {resp.get('error')}", file=sys.stderr)
            return 1
        names.update(_harvest_users(resp))
        msgs = (resp.get("history") or {}).get("messages") or resp.get("messages") or []
        header = f"# {label}  ({auth.team_name})  [{cid}]  {len(msgs)} message(s)"
        _emit("read", header + "\n" + _fmt_messages(msgs, names, auth.team_domain, cid))
    finally:
        cdp.close()
    return 0


def cmd_thread(args: argparse.Namespace) -> int:
    if args.url:
        info = _parse_permalink(args.url)
        cid = info["channel"]
        root_ts = info["thread_ts"] or info["ts"]
        want = info["domain"]
    else:
        if not args.channel or not args.ts:
            print("thread needs either --url or both --channel and --ts", file=sys.stderr)
            return 2
        cid, root_ts, want = args.channel, args.ts, args.workspace
    workspaces, cdp = _connect()
    try:
        auth = _pick_workspace(workspaces, want)
        resp = cdp.slack_api(
            "/api/conversations.replies", auth.xoxc_token,
            channel=cid, ts=root_ts, limit=str(args.limit))
        if not resp.get("ok"):
            print(f"error: {resp.get('error')}", file=sys.stderr)
            return 1
        names = _harvest_users(resp)
        msgs = resp.get("messages") or []
        header = f"# thread in [{cid}]  ({auth.team_name})  {len(msgs)} message(s)"
        _emit("thread", header + "\n" + _fmt_messages(msgs, names, auth.team_domain, cid))
    finally:
        cdp.close()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    workspaces, cdp = _connect()
    try:
        blocks: list[str] = []
        for auth in _scope(workspaces, args.workspace):
            resp = cdp.slack_api(
                "/api/search.messages", auth.xoxc_token,
                query=args.query, sort="timestamp", sort_dir="desc",
                count=str(args.limit), page="1")
            if not resp.get("ok"):
                blocks.append(f"## {auth.team_name}: error {resp.get('error')}")
                continue
            names = _harvest_users(resp)
            matches = (resp.get("messages") or {}).get("matches") or []
            if not matches:
                blocks.append(f"## {auth.team_name}: no matches")
                continue
            lines = [f"## {auth.team_name} ({len(matches)} shown)"]
            for m in matches:
                ch = m.get("channel") or {}
                cid = ch.get("id", "?")
                cname = ch.get("name") or cid
                sender = m.get("user") or m.get("bot_id") or "?"
                who = names.get(sender, m.get("username") or sender)
                text = (m.get("text") or "").strip().replace("\n", " ")
                link = m.get("permalink") or _construct_permalink(
                    auth.team_domain, cid, m.get("ts", ""), m.get("thread_ts"))
                lines.append(f"[#{cname}] {who}: {text[:240]}\n    {link}")
            blocks.append("\n".join(lines))
        _emit("search", "\n\n".join(blocks))
    finally:
        cdp.close()
    return 0


def cmd_find_channel(args: argparse.Namespace) -> int:
    workspaces, cdp = _connect()
    try:
        q = args.query.lstrip("#").lower()
        lines: list[str] = []
        for auth in _scope(workspaces, args.workspace):
            convs, names, _self = _bootstrap_conversations(cdp, auth)
            hits = [c for c in convs
                    if not c.get("is_im") and q in (c.get("name") or "").lower()]
            for c in sorted(hits, key=lambda x: x.get("name") or ""):
                kind = "private" if c.get("is_private") else (
                    "group-dm" if c.get("is_mpim") else "public")
                lines.append(f"{c['id']}  #{c.get('name','?')}  ({auth.team_name}, {kind})")
        if not lines:
            print("(no matching channels in your membership; "
                  "find-channel only sees channels you belong to)")
            return 0
        _emit("find-channel", "\n".join(lines))
    finally:
        cdp.close()
    return 0


def cmd_find_user(args: argparse.Namespace) -> int:
    workspaces, cdp = _connect()
    try:
        is_email = "@" in args.query and "." in args.query.split("@")[-1]
        q = args.query.lower()
        lines: list[str] = []
        for auth in _scope(workspaces, args.workspace):
            if is_email:
                resp = cdp.slack_api(
                    "/api/users.lookupByEmail", auth.xoxc_token, email=args.query)
                if resp.get("ok"):
                    u = resp.get("user") or {}
                    prof = u.get("profile") or {}
                    lines.append(
                        f"{u.get('id','?')}  {prof.get('display_name') or prof.get('real_name') or u.get('name','?')}"
                        f"  <{prof.get('email','')}>  ({auth.team_name})")
                else:
                    lines.append(f"{auth.team_name}: {resp.get('error')}")
                continue
            # Name fragment: best-effort scan of users.list (capped). Large orgs
            # may truncate; for an exact person prefer the email lookup.
            resp = cdp.slack_api(
                "/api/users.list", auth.xoxc_token, limit="200")
            if not resp.get("ok"):
                lines.append(f"{auth.team_name}: {resp.get('error')}")
                continue
            for u in resp.get("members") or []:
                if not isinstance(u, dict) or u.get("deleted"):
                    continue
                prof = u.get("profile") or {}
                hay = " ".join(filter(None, [
                    u.get("name"), prof.get("display_name"),
                    prof.get("real_name"), prof.get("email")])).lower()
                if q in hay:
                    lines.append(
                        f"{u.get('id','?')}  {prof.get('display_name') or prof.get('real_name') or u.get('name','?')}"
                        f"  <{prof.get('email','')}>  ({auth.team_name})")
        _emit("find-user", "\n".join(lines) if lines else "(no matches)")
    finally:
        cdp.close()
    return 0


def cmd_list_dms(args: argparse.Namespace) -> int:
    workspaces, cdp = _connect()
    try:
        lines: list[str] = []
        for auth in _scope(workspaces, args.workspace):
            convs, names, _self = _bootstrap_conversations(cdp, auth)
            dms = [c for c in convs if c.get("is_im") or c.get("is_mpim")][:args.limit]
            for c in dms:
                if c.get("is_im") and c.get("user") and c["user"] not in names:
                    info = cdp.slack_api("/api/users.info", auth.xoxc_token, user=c["user"])
                    if info.get("ok"):
                        names.update(_harvest_users({"users": [info.get("user", {})]}))
                lines.append(f"{c['id']}  {_channel_label(c, names)}  ({auth.team_name})")
        _emit("list-dms", "\n".join(lines) if lines else "(no DMs)")
    finally:
        cdp.close()
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    workspaces, cdp = _connect()
    try:
        auth, _convs, _names, _self, cid, label = _resolve_for(
            cdp, workspaces, args.channel, args.workspace)
        payload: dict[str, Any] = {"channel": cid, "text": args.text}
        if args.thread_ts:
            payload["thread_ts"] = args.thread_ts
        if args.dry_run:
            print(json.dumps({
                "would_send": True,
                "workspace": auth.team_name,
                "channel": label,
                "channel_id": cid,
                "thread_ts": args.thread_ts,
                "text": args.text,
            }, indent=2))
            return 0
        if not args.yes:
            print("refusing to send without --yes — confirm the exact text and "
                  "destination with the user first, then pass --yes", file=sys.stderr)
            return 2
        resp = cdp.slack_api("/api/chat.postMessage", auth.xoxc_token, **payload)
        if not resp.get("ok"):
            print(f"error: {resp.get('error')}", file=sys.stderr)
            return 1
        ts = resp.get("ts", "")
        link = _construct_permalink(auth.team_domain, cid, ts, args.thread_ts) if ts else ""
        print(f"sent to {label} ({auth.team_name})  ts={ts}\n    {link}")
    finally:
        cdp.close()
    return 0


# Read-only Slack methods callable via `raw` without --yes. Anything else —
# chat.*, reactions.*, conversations.create/invite/kick/archive, files.upload,
# admin.* — can mutate a workspace, so it requires --yes. Mirrors the proxmox
# raw gate: the guard lives in code, not just in SKILL.md prose.
_READONLY_RAW_SUFFIXES = (".list", ".info", ".history", ".replies", ".members")
_READONLY_RAW_PREFIXES = ("search.", "users.")


def _is_readonly_method(method: str) -> bool:
    m = method.lstrip("/")
    if m.startswith("api/"):
        m = m[len("api/"):]
    return m.endswith(_READONLY_RAW_SUFFIXES) or m.startswith(_READONLY_RAW_PREFIXES)


def cmd_raw(args: argparse.Namespace) -> int:
    if not _is_readonly_method(args.method) and not args.yes:
        print(f"refusing to call '{args.method}' without --yes — raw can hit write "
              "methods (chat.postMessage, chat.delete, conversations.invite, ...). "
              "Confirm the exact call with the user first, then pass --yes.",
              file=sys.stderr)
        return 2
    workspaces, cdp = _connect()
    try:
        auth = _pick_workspace(workspaces, args.workspace)
        params = json.loads(args.args) if args.args else {}
        if not isinstance(params, dict):
            print("--args must be a JSON object", file=sys.stderr)
            return 2
        path = args.method if args.method.startswith("/") else f"/api/{args.method}"
        resp = cdp.slack_api(path, auth.xoxc_token, **params)
        _emit("raw", json.dumps(resp, indent=2))
    finally:
        cdp.close()
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    """List signed-in workspaces (no CDP needed). Setup verification."""
    try:
        ws = discover_workspaces()
    except SlackChannelError as e:
        print(json.dumps({"ok": False, "error": e.reason}))
        return 1
    print(json.dumps({
        "ok": True,
        "workspaces": [{
            "team_id": w.team_id, "team_domain": w.team_domain,
            "team_name": w.team_name,
        } for w in ws],
    }, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="slack",
        description="Personal Slack over CDP — read/search/send across every "
                    "signed-in workspace.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _ws(p: argparse.ArgumentParser) -> None:
        p.add_argument("--workspace", help="Scope to one workspace (domain or name)")

    p = sub.add_parser("read", help="Read recent messages in a channel/DM")
    p.add_argument("channel", help="#name, name, or Cxxxx/Dxxxx/Gxxxx id")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--oldest", help="Only messages at/after this Slack ts")
    _ws(p)
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("thread", help="Read a thread (by permalink or channel+ts)")
    p.add_argument("--url", help="Slack archives permalink (easiest)")
    p.add_argument("--channel", help="Channel id (with --ts)")
    p.add_argument("--ts", help="Thread root ts (with --channel)")
    p.add_argument("--limit", type=int, default=100)
    _ws(p)
    p.set_defaults(func=cmd_thread)

    p = sub.add_parser("search", help="Search messages (Slack search operators)")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    _ws(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("find-channel", help="Find a channel you belong to by name")
    p.add_argument("query")
    _ws(p)
    p.set_defaults(func=cmd_find_channel)

    p = sub.add_parser("find-user", help="Look up a user by email (exact) or name")
    p.add_argument("query")
    _ws(p)
    p.set_defaults(func=cmd_find_user)

    p = sub.add_parser("list-dms", help="List your DMs and group DMs")
    p.add_argument("--limit", type=int, default=30)
    _ws(p)
    p.set_defaults(func=cmd_list_dms)

    p = sub.add_parser("send", help="Post a message (requires --yes)")
    p.add_argument("channel", help="#name, name, or Cxxxx id")
    p.add_argument("text", help="Message text")
    p.add_argument("--thread-ts", dest="thread_ts", help="Reply in this thread")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the resolved destination + text without sending")
    p.add_argument("--yes", action="store_true",
                   help="Confirm send (required outside a TTY)")
    _ws(p)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("raw", help="Call any Slack API method directly")
    p.add_argument("method", help="e.g. conversations.info")
    p.add_argument("--args", help="JSON object of params")
    p.add_argument("--yes", action="store_true",
                   help="Required for non-read-only methods (writes like "
                        "chat.postMessage, chat.delete, conversations.invite)")
    _ws(p)
    p.set_defaults(func=cmd_raw)

    p = sub.add_parser("discover", help="List signed-in workspaces (setup check)")
    p.set_defaults(func=cmd_discover)

    return ap


def main() -> int:
    args = _build_parser().parse_args()
    try:
        return args.func(args)
    except SlackChannelError as e:
        print(f"slack error: {e.reason}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
