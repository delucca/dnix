#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
google_workspace.py -- Read/write Google Docs, Drive, and Sheets via the
taylorwilsdon/google_workspace_mcp server (PyPI: workspace-mcp), spawned as a
short-lived stdio MCP subprocess.

Spawns `uvx workspace-mcp@<pinned>` as a subprocess, performs the JSON-RPC 2.0
MCP handshake over its stdin/stdout, calls one tool, prints the result, then
terminates it. No persistent registration, no state leak between calls.

Auth: OAuth 2.0 single-user mode. Run `auth` ONCE per machine to complete the
browser consent and cache a refresh token; every later call runs headless.

Usage: google_workspace.py <subcommand> [args]
       google_workspace.py --help
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import webbrowser
from pathlib import Path

# -- Constants ----------------------------------------------------------------

# Pinned: global rule is no floating versions. Bump deliberately.
WORKSPACE_MCP_VERSION = "1.21.1"

# Which Google services to load, and the feature tier. "complete" is required
# for inspect_doc_structure / batch_update_doc / formatting tools.
TOOLS = ["docs", "drive", "sheets"]
TOOL_TIER = "complete"

OUT_DIR = Path.home() / ".cache" / "google-workspace-cm"
INLINE_LIMIT = 4000  # bytes; above this spill to disk and print path

MCP_STARTUP_TIMEOUT = 120  # uvx may install workspace-mcp + deps on first run
MCP_CALL_TIMEOUT = 120     # seconds per normal tool call
MCP_AUTH_TIMEOUT = int(os.environ.get("GW_AUTH_TIMEOUT", "600"))  # first-run consent: time for the human to click

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import credential  # noqa: E402
from mcp_stdio import MCPClient  # noqa: E402


# -- Preflight checks ---------------------------------------------------------

def find_uvx() -> str:
    """Locate uvx on PATH. Exit with a helpful message if not found."""
    uvx = shutil.which("uvx")
    if uvx is None:
        print(
            "uvx not found on PATH.\n"
            "\n"
            "Install uv (provides uvx): brew install uv  (macOS)\n"
            "                           curl -LsSf https://astral.sh/uv/install.sh | sh  (debian)\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return uvx


def load_creds() -> dict[str, str]:
    return {field: credential.read("use-google-workspace", key, label=f"Google OAuth {field}")
            for field, key in (("client_id", "clientId"), ("client_secret", "clientSecret"), ("email", "email"))}


def build_cmd(uvx: str) -> list[str]:
    """Command line to launch workspace-mcp as a stdio single-user server."""
    return [
        uvx,
        f"workspace-mcp@{WORKSPACE_MCP_VERSION}",
        "--transport", "stdio",
        "--single-user",
        "--tools", *TOOLS,
        "--tool-tier", TOOL_TIER,
    ]


def build_env(creds: dict[str, str]) -> dict[str, str]:
    """Environment for the server: OAuth client + single-user email."""
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": creds["client_id"],
        "USER_GOOGLE_EMAIL": creds["email"],
        # Allow the http://localhost callback during the one-time consent flow.
        "OAUTHLIB_INSECURE_TRANSPORT": "1",
        # webbrowser.open() can hang in this nested subprocess (uv -> python ->
        # uvx -> server), which stalls the auth flow before it can surface the
        # URL. Point BROWSER at a no-op so the call returns instantly; the server
        # still raises the auth error containing the URL, which cmd_auth prints.
        "BROWSER": "/usr/bin/true",
    }
    if creds["client_secret"]:
        env["GOOGLE_OAUTH_CLIENT_SECRET"] = creds["client_secret"]
    return env


# -- Output helpers -----------------------------------------------------------

def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def emit_text(label: str, text: str) -> None:
    """Print short text inline; spill large text to ~/.cache/google-workspace-cm/."""
    if len(text.encode()) <= INLINE_LIMIT:
        print(text)
        return
    ensure_out_dir()
    path = OUT_DIR / f"{ts()}-{label}.txt"
    path.write_text(text)
    print(f"# {label}: {len(text)} chars, saved to {path}")
    print(f"# first 1500 chars:\n{text[:1500]}")


def emit_json(label: str, data) -> None:
    emit_text(label, json.dumps(data, indent=2, ensure_ascii=False))


def extract_text_content(result: dict) -> str:
    """Concatenate all text items from a tools/call result."""
    parts: list[str] = []
    for item in result.get("content", []):
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "\n".join(parts)


# workspace-mcp answers an expired token with a normal (non-error) text result:
# this block, carrying the authorization URL.
AUTH_PROMPT_MARKER = "ACTION REQUIRED"


def is_auth_prompt(text: str) -> bool:
    """True for the server's re-consent block, not for a doc that mentions OAuth."""
    return AUTH_PROMPT_MARKER in text and find_auth_url(text) is not None


def exit_needs_auth() -> None:
    # Never print the URL: it wraps, and a copy of the wrapped text splits the
    # `scope` parameter -- Google then fails with Error 400: invalid_scope.
    sys.exit("Not authenticated (the cached token expired or was revoked).\n"
             "Run: google_workspace.py auth")


def emit_result(label: str, result: dict) -> None:
    text = extract_text_content(result)
    if text and is_auth_prompt(text):
        exit_needs_auth()
    if text:
        emit_text(label, text)
    else:
        emit_json(label, result)


# -- Client lifecycle ---------------------------------------------------------

EMAIL = ""  # set in main() from 1Password, injected into every tool call


def with_client(fn):
    """Decorator: load creds, spawn server, handshake, run fn, tear down."""
    def wrapper(*args, **kwargs):
        global EMAIL
        uvx = find_uvx()
        creds = load_creds()
        EMAIL = creds["email"]
        client = MCPClient(build_cmd(uvx), env=build_env(creds),
                           client_name="use-google-workspace",
                           process_label="workspace-mcp", call_timeout=MCP_CALL_TIMEOUT)
        try:
            client.initialize(MCP_STARTUP_TIMEOUT)
            return fn(client, *args, **kwargs)
        except TimeoutError as e:
            sys.exit(f"Timeout: {e}")
        except RuntimeError as e:
            msg = str(e)
            if is_auth_prompt(msg):
                exit_needs_auth()
            sys.exit(f"MCP error: {msg}\n\nNot authenticated yet? Run: google_workspace.py auth")
        finally:
            client.close()
    return wrapper


def with_email(d: dict) -> dict:
    """Inject the required user_google_email into a tool-arguments dict."""
    d.setdefault("user_google_email", EMAIL)
    return d


def parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


# -- auth: one-time consent bootstrap -----------------------------------------

def credentials_dir() -> Path:
    """Where workspace-mcp caches the OAuth token."""
    d = (os.environ.get("GOOGLE_MCP_CREDENTIALS_DIR")
         or os.environ.get("WORKSPACE_MCP_CREDENTIALS_DIR"))
    if d:
        return Path(d).expanduser()
    return Path.home() / ".google_workspace_mcp" / "credentials"


def find_auth_url(text: str) -> str | None:
    """Pull the Google authorization URL out of a tool result or error string."""
    if not text:
        return None
    m = re.search(r"https://accounts\.google\.com/[^\s'\"<>)]+", text)
    if m:
        return m.group(0)
    m = re.search(r"https://[^\s'\"<>)]*oauth[^\s'\"<>)]*", text)
    return m.group(0) if m else None


_AUTH_URL_RE = re.compile(r"https://accounts\.google\.com/\S+")
_REDACTED = "<authorization URL suppressed -- see the box below>"


def make_auth_url_redactor():
    """Build a stderr line filter that strips the authorization URL, wrap and all.

    workspace-mcp logs the URL plainly, then logs it again inside a rich-rendered
    traceback that hard-wraps it across a dozen lines. A copy of either carries a
    line break into the `scope` parameter and Google fails the flow with
    `Error 400: invalid_scope`, so drop every piece: print_auth_url stages the
    real URL to a file and prints how to open it. Stateful, hence the closure --
    the wrapped continuations only make sense as "the lines after a hit".
    """
    in_wrapped_url = False

    def redact(line: str) -> str | None:
        nonlocal in_wrapped_url
        if _AUTH_URL_RE.search(line):
            in_wrapped_url = True
            return _AUTH_URL_RE.sub(_REDACTED, line)
        body = line.strip()
        if in_wrapped_url and body:
            if not any(c.isspace() for c in body):
                return None  # a wrapped continuation: one unbroken URL token
            in_wrapped_url = False
        return line

    return redact


def print_auth_url(url: str, browser_already_open: bool = False) -> None:
    """Route the URL to a browser without anyone having to copy it.

    The authorization URL is ~700 characters, so every terminal wraps it. A copy
    of the wrapped text carries the line breaks, they arrive as spaces inside the
    `scope` parameter, and Google splits the scopes at those points and rejects
    the flow with `Error 400: invalid_scope`. So park the URL in a file and print
    only commands short enough to survive the wrap.
    """
    # Not the credentials dir: cmd_auth polls that for a token write, and a new
    # file appearing there would read as one and report success before the click.
    path = OUT_DIR / "auth_url.txt"
    try:
        ensure_out_dir()
        path.write_text(url + "\n")
        path.chmod(0o600)
    except OSError:
        path = None

    opened = browser_already_open
    if not opened:
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False

    sep = "=" * 70
    print(f"\n{sep}")
    print("A browser tab is open: sign in and click Allow."
          if opened else "No browser opened automatically. Open the page with:")
    if path:
        # ~ keeps both commands under 80 columns, so they don't wrap in turn.
        short = f"~/{path.relative_to(Path.home())}" if path.is_relative_to(Path.home()) else path
        print("\n  # on this machine:")
        print(f'  open "$(cat {short})"')
        print("\n  # or, if `auth` is running on a remote host, from your laptop:")
        print(f'  open "$(ssh <host> cat {short})"')
        print("\nRun one of those. Never copy the URL itself out of a terminal:")
        print("the wrap becomes a space inside `scope` -> Error 400: invalid_scope.")
    else:
        print(f"\n{url}")
        print("\n(could not stage the URL on disk, so it is printed raw -- if the")
        print("paste fails with Error 400: invalid_scope, the wrap corrupted it)")
    print(sep)
    print("(unverified-app screen: Advanced -> Go to ... (unsafe) -> Allow)\n", flush=True)


def _creds_snapshot(cdir) -> dict:
    """Map each token file to (mtime_ns, size).

    Comparing signatures rather than path identity means a re-consent that
    rewrites the SAME per-email token file (workspace-mcp's behavior) is detected
    as a change, not missed by a `now - before` set difference.
    """
    snap: dict = {}
    if cdir.exists():
        # Only the per-email token files: anything else in there is not evidence
        # of consent. oauth_states.json in particular is rewritten when a flow
        # *starts*, so watching it reports success before the user clicks Allow.
        for p in cdir.glob("*.json"):
            if p.is_file() and p.name != "oauth_states.json":
                try:
                    st = p.stat()
                    snap[p] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    pass
    return snap


def cmd_auth(args) -> None:
    """Trigger the one-time OAuth consent and cache a refresh token.

    workspace-mcp opens the browser itself on stdio; when it cannot (headless),
    we open it here. Either way the URL is staged to a file so it is reachable by
    a short command instead of a copy. We keep the local callback listener alive
    (http://localhost:8000/oauth2callback) and poll the credentials directory
    until the token file appears. Works the same on a laptop or, via an SSH
    tunnel, on a headless host.
    """
    global EMAIL
    uvx = find_uvx()
    creds = load_creds()
    EMAIL = creds["email"]
    cdir = credentials_dir()
    before = _creds_snapshot(cdir)

    print(f"Authenticating {creds['email']} ...", file=sys.stderr)
    client = MCPClient(build_cmd(uvx), env=build_env(creds),
                       client_name="use-google-workspace", process_label="workspace-mcp",
                       call_timeout=MCP_CALL_TIMEOUT, stderr_to_terminal=True,
                       stderr_line_filter=make_auth_url_redactor())
    try:
        client.initialize(MCP_STARTUP_TIMEOUT)
        # A trivial Drive call forces the auth flow. When the browser can't be
        # opened, the server returns the authorization URL in the result (or in
        # an error); surface it so the user can open it manually.
        try:
            result = client.call_tool(
                "search_drive_files",
                with_email({"query": "name contains '.'", "page_size": 1}),
                timeout=MCP_AUTH_TIMEOUT,
            )
            payload = extract_text_content(result)
        except RuntimeError as e:
            payload = str(e)

        url = find_auth_url(payload)
        if not url:
            # No auth URL and the probe returned real data -> a token already
            # existed or consent already completed. There is nothing to wait for,
            # so return now instead of polling for a "fresh" file that will never
            # appear (which otherwise hung MCP_AUTH_TIMEOUT then reported failure).
            if payload:
                print(payload[:500])
            print(f"\n✓ Already authenticated as {creds['email']}. "
                  f"Token cached to {cdir}. Future calls run headless.")
            return

        print_auth_url(url, "automatically opened in your browser" in payload)

        # Keep the subprocess (and its callback server) alive until a token file
        # appears OR an existing per-email token is rewritten by a re-consent.
        deadline = time.monotonic() + MCP_AUTH_TIMEOUT
        while time.monotonic() < deadline:
            now = _creds_snapshot(cdir)
            changed = [p for p, sig in now.items() if sig[1] > 0 and before.get(p) != sig]
            if changed:
                print(f"\n✓ Authenticated as {creds['email']}. "
                      f"Token cached to {cdir}. Future calls run headless.")
                return
            time.sleep(3)
        sys.exit(
            "Timed out waiting for consent. Open the URL above, finish the Allow "
            "step, then re-run `auth`. (Quit stray browser tabs on localhost:8000 first.)"
        )
    except TimeoutError:
        sys.exit("Auth timed out before an authorization URL was produced. Retry "
                 "after fully quitting your browser.")
    finally:
        client.close()


# -- tools: discovery ---------------------------------------------------------

@with_client
def cmd_tools(client: MCPClient, args) -> None:
    tools = client.list_tools()
    if args.schema:
        emit_json("tools", tools)
        return
    out = []
    for t in tools:
        desc = (t.get("description") or "").strip().replace("\n", " ")
        out.append(f"- {t.get('name')}: {desc[:140]}")
    emit_text("tools", "\n".join(out))


# -- Docs ---------------------------------------------------------------------

@with_client
def cmd_doc_get(client: MCPClient, args) -> None:
    a = with_email({"document_id": args.document_id})
    if args.suggestions:
        a["suggestions_view_mode"] = args.suggestions
    emit_result("doc-get", client.call_tool("get_doc_content", a))


@with_client
def cmd_doc_md(client: MCPClient, args) -> None:
    a = with_email({"document_id": args.document_id})
    if args.no_comments:
        a["include_comments"] = False
    if args.include_resolved:
        a["include_resolved"] = True
    emit_result("doc-md", client.call_tool("get_doc_as_markdown", a))


@with_client
def cmd_doc_create(client: MCPClient, args) -> None:
    a = with_email({"title": args.title})
    if args.content:
        a["content"] = args.content
    emit_result("doc-create", client.call_tool("create_doc", a))


@with_client
def cmd_doc_inspect(client: MCPClient, args) -> None:
    a = with_email({"document_id": args.document_id})
    if args.detailed:
        a["detailed"] = True
    if args.tab:
        a["tab_id"] = args.tab
    emit_result("doc-inspect", client.call_tool("inspect_doc_structure", a))


@with_client
def cmd_doc_modify(client: MCPClient, args) -> None:
    a = with_email({"document_id": args.document_id, "start_index": args.start})
    if args.end is not None:
        a["end_index"] = args.end
    if args.text is not None:
        a["text"] = args.text
    if args.segment_id:
        a["segment_id"] = args.segment_id
    if args.tab:
        a["tab_id"] = args.tab
    if args.bold:
        a["bold"] = True
    if args.italic:
        a["italic"] = True
    if args.underline:
        a["underline"] = True
    if args.font_size is not None:
        a["font_size"] = args.font_size
    if args.font_family:
        a["font_family"] = args.font_family
    if args.text_color:
        a["text_color"] = args.text_color
    if args.link_url:
        a["link_url"] = args.link_url
    emit_result("doc-modify", client.call_tool("modify_doc_text", a))


@with_client
def cmd_doc_find_replace(client: MCPClient, args) -> None:
    a = with_email({
        "document_id": args.document_id,
        "find_text": args.find,
        "replace_text": args.replace,
    })
    if args.match_case:
        a["match_case"] = True
    if args.tab:
        a["tab_id"] = args.tab
    emit_result("doc-find-replace", client.call_tool("find_and_replace_doc", a))


# -- Drive --------------------------------------------------------------------

@with_client
def cmd_drive_search(client: MCPClient, args) -> None:
    a = with_email({"query": args.query, "page_size": args.limit})
    if args.type:
        a["file_type"] = args.type
    if args.order_by:
        a["order_by"] = args.order_by
    emit_result("drive-search", client.call_tool("search_drive_files", a))


@with_client
def cmd_drive_list(client: MCPClient, args) -> None:
    a = with_email({"folder_id": args.folder_id, "page_size": args.limit})
    if args.type:
        a["file_type"] = args.type
    emit_result("drive-list", client.call_tool("list_drive_items", a))


@with_client
def cmd_drive_get(client: MCPClient, args) -> None:
    emit_result("drive-get",
                client.call_tool("get_drive_file_content",
                                 with_email({"file_id": args.file_id})))


@with_client
def cmd_drive_create(client: MCPClient, args) -> None:
    a = with_email({"file_name": args.file_name})
    if args.content is not None:
        a["content"] = args.content
    if args.folder:
        a["folder_id"] = args.folder
    if args.mime:
        a["mime_type"] = args.mime
    if args.url:
        a["fileUrl"] = args.url
    emit_result("drive-create", client.call_tool("create_drive_file", a))


@with_client
def cmd_drive_link(client: MCPClient, args) -> None:
    emit_result("drive-link",
                client.call_tool("get_drive_shareable_link",
                                 with_email({"file_id": args.file_id})))


# -- Sheets -------------------------------------------------------------------

@with_client
def cmd_sheet_read(client: MCPClient, args) -> None:
    a = with_email({"spreadsheet_id": args.spreadsheet_id, "range_name": args.range})
    if args.formulas:
        a["include_formulas"] = True
    if args.notes:
        a["include_notes"] = True
    if args.hyperlinks:
        a["include_hyperlinks"] = True
    emit_result("sheet-read", client.call_tool("read_sheet_values", a))


@with_client
def cmd_sheet_write(client: MCPClient, args) -> None:
    a = with_email({"spreadsheet_id": args.spreadsheet_id, "range_name": args.range})
    if args.clear:
        a["clear_values"] = True
    elif args.values is not None:
        try:
            a["values"] = json.loads(args.values)
        except json.JSONDecodeError:
            a["values"] = args.values  # allow a plain string
    if args.raw:
        a["value_input_option"] = "RAW"
    emit_result("sheet-write", client.call_tool("modify_sheet_values", a))


@with_client
def cmd_sheet_create(client: MCPClient, args) -> None:
    a = with_email({"title": args.title})
    sheets = parse_csv(args.sheets)
    if sheets:
        a["sheet_names"] = sheets
    emit_result("sheet-create", client.call_tool("create_spreadsheet", a))


@with_client
def cmd_sheet_info(client: MCPClient, args) -> None:
    emit_result("sheet-info",
                client.call_tool("get_spreadsheet_info",
                                 with_email({"spreadsheet_id": args.spreadsheet_id})))


# -- raw escape hatch ---------------------------------------------------------

@with_client
def cmd_raw(client: MCPClient, args) -> None:
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        sys.exit(f"--args must be valid JSON: {e}")
    if not isinstance(tool_args, dict):
        sys.exit("--args must be a JSON object")
    emit_result(f"raw-{args.tool}", client.call_tool(args.tool, with_email(tool_args)))


# -- Argument parsing ---------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        prog="google_workspace",
        description="Read/write Google Docs, Drive, Sheets via workspace-mcp (stdio subprocess).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("auth", help="One-time OAuth consent; caches a refresh token")
    sp.set_defaults(func=cmd_auth)

    sp = sub.add_parser("tools", help="List the tools the server exposes")
    sp.add_argument("--schema", action="store_true", help="Include full input schemas")
    sp.set_defaults(func=cmd_tools)

    # -- Docs --
    sp = sub.add_parser("doc-get", help="Get a doc's text content")
    sp.add_argument("document_id")
    sp.add_argument("--suggestions", help="suggestions_view_mode (e.g. PREVIEW_WITHOUT_SUGGESTIONS)")
    sp.set_defaults(func=cmd_doc_get)

    sp = sub.add_parser("doc-md", help="Get a doc as Markdown (with comments)")
    sp.add_argument("document_id")
    sp.add_argument("--no-comments", action="store_true", dest="no_comments")
    sp.add_argument("--include-resolved", action="store_true", dest="include_resolved")
    sp.set_defaults(func=cmd_doc_md)

    sp = sub.add_parser("doc-create", help="Create a new Google Doc")
    sp.add_argument("title")
    sp.add_argument("--content", help="Initial body text")
    sp.set_defaults(func=cmd_doc_create)

    sp = sub.add_parser("doc-inspect",
                        help="Inspect structure: safe indexes, segments, tables, named ranges")
    sp.add_argument("document_id")
    sp.add_argument("--detailed", action="store_true")
    sp.add_argument("--tab", help="tab_id to scope to a specific tab")
    sp.set_defaults(func=cmd_doc_inspect)

    sp = sub.add_parser("doc-modify",
                        help="Insert/replace/format text at a UTF-16 index range")
    sp.add_argument("document_id")
    sp.add_argument("--start", type=int, required=True, help="start_index (UTF-16 code units)")
    sp.add_argument("--end", type=int, help="end_index (omit to insert at start)")
    sp.add_argument("--text", help="Text to insert/replace")
    sp.add_argument("--segment-id", dest="segment_id", help="header/footer/footnote segment id")
    sp.add_argument("--tab", help="tab_id")
    sp.add_argument("--bold", action="store_true")
    sp.add_argument("--italic", action="store_true")
    sp.add_argument("--underline", action="store_true")
    sp.add_argument("--font-size", type=int, dest="font_size")
    sp.add_argument("--font-family", dest="font_family")
    sp.add_argument("--text-color", dest="text_color", help="hex e.g. #1155cc")
    sp.add_argument("--link-url", dest="link_url")
    sp.set_defaults(func=cmd_doc_modify)

    sp = sub.add_parser("doc-find-replace", help="Find and replace text across a doc")
    sp.add_argument("document_id")
    sp.add_argument("--find", required=True)
    sp.add_argument("--replace", required=True)
    sp.add_argument("--match-case", action="store_true", dest="match_case")
    sp.add_argument("--tab", help="tab_id")
    sp.set_defaults(func=cmd_doc_find_replace)

    # -- Drive --
    sp = sub.add_parser("drive-search", help="Search Drive (Google query syntax)")
    sp.add_argument("query", help="e.g. \"name contains 'budget' and mimeType='application/vnd.google-apps.document'\"")
    sp.add_argument("--limit", type=int, default=10, help="page_size")
    sp.add_argument("--type", help="file_type filter (e.g. document, spreadsheet, folder)")
    sp.add_argument("--order-by", dest="order_by", help="e.g. modifiedTime desc")
    sp.set_defaults(func=cmd_drive_search)

    sp = sub.add_parser("drive-list", help="List items in a folder")
    sp.add_argument("folder_id", nargs="?", default="root")
    sp.add_argument("--limit", type=int, default=100, help="page_size")
    sp.add_argument("--type", help="file_type filter")
    sp.set_defaults(func=cmd_drive_list)

    sp = sub.add_parser("drive-get", help="Get a Drive file's content by id")
    sp.add_argument("file_id")
    sp.set_defaults(func=cmd_drive_get)

    sp = sub.add_parser("drive-create", help="Create a Drive file")
    sp.add_argument("file_name")
    sp.add_argument("--content", help="Inline text content")
    sp.add_argument("--folder", help="folder_id (default root)")
    sp.add_argument("--mime", help="mime_type (default text/plain)")
    sp.add_argument("--url", help="fileUrl to import from")
    sp.set_defaults(func=cmd_drive_create)

    sp = sub.add_parser("drive-link", help="Get a shareable link for a file")
    sp.add_argument("file_id")
    sp.set_defaults(func=cmd_drive_link)

    # -- Sheets --
    sp = sub.add_parser("sheet-read", help="Read a range of cell values")
    sp.add_argument("spreadsheet_id")
    sp.add_argument("range", nargs="?", default="A1:Z1000", help="A1 range (default A1:Z1000)")
    sp.add_argument("--formulas", action="store_true")
    sp.add_argument("--notes", action="store_true")
    sp.add_argument("--hyperlinks", action="store_true")
    sp.set_defaults(func=cmd_sheet_read)

    sp = sub.add_parser("sheet-write", help="Write/clear a range of cell values")
    sp.add_argument("spreadsheet_id")
    sp.add_argument("range", help="A1 range")
    sp.add_argument("--values", help="JSON list-of-lists, e.g. [[\"a\",1],[\"b\",2]]")
    sp.add_argument("--raw", action="store_true", help="value_input_option=RAW (default USER_ENTERED)")
    sp.add_argument("--clear", action="store_true", help="Clear the range instead of writing")
    sp.set_defaults(func=cmd_sheet_write)

    sp = sub.add_parser("sheet-create", help="Create a spreadsheet")
    sp.add_argument("title")
    sp.add_argument("--sheets", help="Comma-separated tab names")
    sp.set_defaults(func=cmd_sheet_create)

    sp = sub.add_parser("sheet-info", help="Get spreadsheet metadata (sheets, ids, sizes)")
    sp.add_argument("spreadsheet_id")
    sp.set_defaults(func=cmd_sheet_info)

    # -- raw --
    sp = sub.add_parser("raw", help="Call any workspace-mcp tool with raw JSON args")
    sp.add_argument("tool", help="Tool name (see `tools`)")
    sp.add_argument("--args", default="{}", help="JSON-encoded arguments object")
    sp.set_defaults(func=cmd_raw)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
