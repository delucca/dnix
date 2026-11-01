#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "websocket-client==1.9.0",
# ]
# ///
"""
notion.py -- Read and write Notion across several workspaces (stdio MCP subprocess).

Spawns @notionhq/notion-mcp-server as a short-lived subprocess, sends JSON-RPC 2.0
over its stdin/stdout, and terminates it after the call. NOTION_TOKEN is chosen per
--account from the skill's settings, so one workspace is reachable per invocation.

Usage: notion.py <subcommand> [args]
       notion.py --help
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

# -- Constants ----------------------------------------------------------------

NPX_REGISTRY = "--registry=https://registry.npmjs.org/"
# Pinned so `npx` does not float the server to whatever is newest at call time.
MCP_PACKAGE = "@notionhq/notion-mcp-server@2.5.1"

SKILL = "use-notion"

OUT_DIR = Path.home() / ".cache" / "notion-cm"
INLINE_LIMIT = 4000  # bytes; above this spill to disk and print path

MCP_STARTUP_TIMEOUT = 60   # seconds to wait for initialize (npx may install)
MCP_CALL_TIMEOUT = 120     # seconds per tool call

# Notion allows ~3 requests/sec per integration; stay just under it.
MIN_CALL_INTERVAL = 0.34

# How an account is reached. `local` is the supported path (integration token +
# MCP server). `browser` drives a logged-in session for workspaces where Notion's
# integration platform is closed to this user's role; it is read-only. `auto`
# prefers local and falls back to browser when no token resolves.
TRANSPORTS = ("local", "browser", "auto")
DEFAULT_TRANSPORT = "local"

# Tools that mutate the workspace. `raw` refuses these without --yes.
WRITE_TOOLS = {
    "API-post-page", "API-patch-page", "API-update-page-markdown",
    "API-patch-block-children", "API-update-a-block", "API-delete-a-block",
    "API-create-a-comment", "API-create-a-data-source", "API-update-a-data-source",
    "API-move-page",
}

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import credential  # noqa: E402
from mcp_stdio import MCPClient  # noqa: E402


# -- Account registry ----------------------------------------------------------

def load_accounts() -> dict:
    """Every account named in settings.accounts or settings.secrets, with its secret ref."""
    cfg = credential.settings(SKILL)
    secrets = cfg.get("secrets") or {}
    accounts = {name: dict(entry) for name, entry in (cfg.get("accounts") or {}).items()}
    for name, ref in secrets.items():
        accounts.setdefault(name, {})["secret"] = ref
    if not accounts:
        sys.exit(
            "No Notion accounts configured.\n"
            f"Set dnix.ai.skills.{SKILL}.settings.secrets.<name> to a token reference, "
            f"or settings.accounts.<name>.transport = \"browser\"."
        )
    return accounts


def resolve_account(requested: str | None) -> tuple[str, dict]:
    """Pick the account to act on: --account, then default = true, then a lone entry."""
    accounts = load_accounts()
    if requested:
        if requested not in accounts:
            known = ", ".join(sorted(accounts))
            sys.exit(f"Unknown account {requested!r}. Configured: {known}")
        return requested, accounts[requested]

    defaults = [n for n, e in accounts.items() if e.get("default")]
    if len(defaults) > 1:
        sys.exit(f"Several accounts set default = true: {', '.join(sorted(defaults))}")
    if defaults:
        return defaults[0], accounts[defaults[0]]
    if len(accounts) == 1:
        name = next(iter(accounts))
        return name, accounts[name]

    known = ", ".join(sorted(accounts))
    sys.exit(
        f"Several accounts configured and none marked default = true: {known}\n"
        "Pass --account <name>, or set NOTION_ACCOUNT, or mark one default."
    )


def account_token(name: str, entry: dict) -> str:
    return credential.read(SKILL, name, label=f"{name} integration token")


def account_transport(name: str, entry: dict) -> str:
    t = (entry.get("transport") or DEFAULT_TRANSPORT).lower()
    if t not in TRANSPORTS:
        sys.exit(f"Account {name!r} declares transport {t!r}; "
                 f"expected one of {', '.join(TRANSPORTS)}.")
    return t


def load_browser_transport():
    """Import the sibling browser module only when a profile actually needs it."""
    import importlib.util
    path = Path(__file__).resolve().parent / "notion_browser.py"
    if not path.is_file():
        sys.exit("The browser transport module is missing next to this script.")
    spec = importlib.util.spec_from_file_location("notion_browser", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LocalTransport:
    """The supported path: integration token through the local MCP server."""

    supports_writes = True
    name = "local"

    def __init__(self, account: str, token: str):
        self.account = account
        self._n = Notion(account, token)

    def close(self):
        self._n.close()

    def call(self, tool, args=None):
        return self._n.call(tool, args)

    def list_tools(self) -> list[dict]:
        return self._n.list_tools()

    def read_markdown(self, ref: str) -> str:
        r = self._n.call("API-retrieve-page-markdown", {"page_id": to_id(ref)})
        if r.get("isError"):
            sys.exit(f"Notion error: {extract_text(r)}")
        payload = result_payload(r)
        raise_if_notion_error(payload)
        return payload if isinstance(payload, str) else json.dumps(payload, indent=2)

    def search(self, query: str, limit: int = 25, obj_type: str | None = None,
               oldest_first: bool = False) -> list[dict]:
        base = {"page_size": min(limit, 100)}
        if query:
            base["query"] = query
        if obj_type:
            base["filter"] = {"property": "object", "value": obj_type}
        if oldest_first:
            base["sort"] = {"direction": "ascending", "timestamp": "last_edited_time"}
        rows = paginate(self._n, "API-post-search", base, "search", limit)
        return [{"id": r.get("id"), "title": title_of(r), "type": r.get("object"),
                 "url": r.get("url", "")} for r in rows]


def open_transport(args):
    """Resolve the account and open whichever transport its profile declares."""
    name, entry = resolve_account(args.account)
    want = account_transport(name, entry)
    browser_only = want == "browser"

    if not browser_only:
        try:
            token = account_token(name, entry)
        except SystemExit:
            if want != "auto":
                raise
            browser_only = True
        if not browser_only:
            return name, LocalTransport(name, token)

    mod = load_browser_transport()
    try:
        return name, mod.BrowserTransport()
    except Exception as e:
        sys.exit(f"Account {name!r}: browser transport unavailable -- {e}")


# -- Reference parsing ---------------------------------------------------------

HEX32 = re.compile(r"[0-9a-fA-F]{32}")
DASHED = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _dash(h: str) -> str:
    h = h.lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def to_id(ref: str) -> str:
    """Turn a Notion URL, bare 32-hex id, or dashed UUID into a dashed UUID.

    Notion puts the id at the END of the last path segment, after the title slug:
    .../Some-Page-Title-<32 hex>?v=<view id>. The id is anchored to the segment end
    rather than searched for loosely, because a slug ending in a hex letter
    ("...-Title-<id>") otherwise lets the 32-char window slide one character left
    and yields a valid-looking but wrong id.
    """
    ref = ref.strip()
    if DASHED.fullmatch(ref):
        return ref.lower()
    if HEX32.fullmatch(ref):
        return _dash(ref)

    segment = ref.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    m = DASHED.search(segment)
    if m:
        return m.group(0).lower()
    m = re.search(r"([0-9a-fA-F]{32})$", segment)
    if m:
        return _dash(m.group(1))
    sys.exit(f"Could not find a Notion id in {ref!r}. Pass a page URL or a UUID.")


# -- Output helpers ------------------------------------------------------------

def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def emit_text(label: str, text: str, ext: str = "md") -> None:
    """Print short text inline; spill large text to ~/.cache/notion-cm/."""
    ensure_out_dir()
    if len(text.encode()) <= INLINE_LIMIT:
        print(text)
        return
    path = OUT_DIR / f"{ts()}-{label}.{ext}"
    path.write_text(text)
    print(f"# {label}: {len(text)} chars, saved to {path}")
    print(f"# first 1500 chars:\n{text[:1500]}")


def emit_json(label: str, data) -> None:
    emit_text(label, json.dumps(data, indent=2, ensure_ascii=False), ext="json")


def extract_text(result: dict) -> str | None:
    for item in result.get("content", []):
        if item.get("type") == "text":
            return item.get("text", "")
        if item.get("type") == "resource":
            res = item.get("resource", {})
            if "text" in res:
                return res["text"]
    return None


def result_payload(result: dict):
    """Return the tool result as parsed JSON when it is JSON, else raw text."""
    text = extract_text(result)
    if text is None:
        return result
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def raise_if_notion_error(payload) -> None:
    """Fail loudly on a Notion error body.

    The MCP server does not always set isError: an invalid token comes back as a
    normal result whose text is {"object":"error","code":"unauthorized",...}. Left
    unchecked, a paginating caller finds no "results" key and reports zero rows --
    turning an auth failure into "nothing matched", which is the single most
    misleading answer this skill can give.
    """
    if not isinstance(payload, dict):
        return
    if payload.get("object") == "error" or (
            payload.get("code") and payload.get("message") and "results" not in payload):
        sys.exit(f"Notion error [{payload.get('code', '?')}]: "
                 f"{payload.get('message', json.dumps(payload)[:200])}")


def emit_result(label: str, result: dict, as_json: bool = False) -> None:
    if result.get("isError"):
        sys.exit(f"Notion error: {extract_text(result) or json.dumps(result)}")
    payload = result_payload(result)
    raise_if_notion_error(payload)
    if isinstance(payload, str) and not as_json:
        emit_text(label, payload)
    else:
        emit_json(label, payload)


# -- Client lifecycle ----------------------------------------------------------

def find_npx() -> str:
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx not found on PATH.\n"
                 "Install Node.js/npm, or if using Volta: volta install node")
    return npx


class Notion:
    """One MCP subprocess bound to one account, with request throttling."""

    def __init__(self, account: str, token: str):
        self.account = account
        cmd = [find_npx(), NPX_REGISTRY, "-y", MCP_PACKAGE]
        self._client = MCPClient(cmd, env={"NOTION_TOKEN": token},
                                 client_name="use-notion", process_label="notion-mcp",
                                 call_timeout=MCP_CALL_TIMEOUT)
        self._client.initialize(MCP_STARTUP_TIMEOUT)
        self._last = 0.0

    def call(self, tool: str, args: dict | None = None) -> dict:
        wait = MIN_CALL_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            result = self._client.call_tool(tool, args or {})
        finally:
            self._last = time.monotonic()
        return result

    def list_tools(self) -> list[dict]:
        return self._client.list_tools()

    def close(self) -> None:
        self._client.close()


def with_client(fn):
    """Decorator for subcommands that need raw MCP tool calls (local transport only)."""
    def wrapper(args):
        name, client = open_transport(args)
        if not isinstance(client, LocalTransport):
            client.close()
            sys.exit(f"`{args.cmd}` is not available on the {client.name} transport "
                     f"for account {name!r}.\n"
                     "That transport covers `search` and `read` only; the rest needs an "
                     "integration token (transport = \"local\").")
        try:
            return fn(client, args)
        except TimeoutError as e:
            sys.exit(f"Timeout: {e}")
        except RuntimeError as e:
            sys.exit(f"MCP error: {e}")
        finally:
            client.close()
    return wrapper


def require_yes(args, action: str) -> None:
    """Refuse a write without --yes, printing what would have happened."""
    if not args.yes:
        sys.exit(f"Refusing to write without --yes.\nWould have: {action}\n"
                 "Re-run with --yes once the user has confirmed.")


def paginate(client: Notion, tool: str, base: dict, label: str, limit: int | None):
    """Follow next_cursor until exhausted or `limit` results collected."""
    out, cursor = [], None
    while True:
        args = dict(base)
        if cursor:
            args["start_cursor"] = cursor
        result = client.call(tool, args)
        if result.get("isError"):
            sys.exit(f"Notion error: {extract_text(result)}")
        payload = result_payload(result)
        raise_if_notion_error(payload)
        if not isinstance(payload, dict):
            return payload
        out.extend(payload.get("results", []))
        cursor = payload.get("next_cursor")
        if not payload.get("has_more") or not cursor:
            break
        if limit and len(out) >= limit:
            break
    return out[:limit] if limit else out


# -- Subcommands: discovery ----------------------------------------------------

def cmd_accounts(args) -> None:
    """List configured accounts and, unless --no-verify, check each one is reachable."""
    accounts = load_accounts()
    for name in sorted(accounts):
        entry = accounts[name]
        marks = " (default)" if entry.get("default") else ""
        transport = account_transport(name, entry)
        print(f"{name}{marks}\n  transport: {transport}")
        if transport != "browser":
            src = entry.get("secret") or "(none)"
            print(f"  token:     {src}")
        if args.no_verify:
            continue

        probe = argparse.Namespace(account=name, cmd="accounts")
        try:
            _, t = open_transport(probe)
        except SystemExit as e:
            print(f"  status:    NOT READY -- {e}")
            continue
        try:
            if isinstance(t, LocalTransport):
                payload = result_payload(t.call("API-get-self"))
                if isinstance(payload, dict) and payload.get("object") == "user":
                    bot = payload.get("bot", {})
                    ws = bot.get("workspace_name") or "(name not exposed)"
                    print(f"  status:    ok -- workspace {ws!r}, bot {payload.get('name')!r}")
                else:
                    print(f"  status:    unexpected -- {json.dumps(payload)[:180]}")
            else:
                e = t.entry_points()
                names = ", ".join(sp["name"] for sp in e["spaces"]) or "(none)"
                print(f"  status:    ok -- {len(e['roots'])} shared root(s); "
                      f"spaces: {names}")
        except Exception as ex:
            print(f"  status:    FAILED -- {ex}")
        finally:
            t.close()


def cmd_search(args) -> None:
    name, t = open_transport(args)
    # One try/finally around everything: paginate() exits via SystemExit on a Notion
    # error, which `except Exception` does not catch, so a split try leaked the MCP
    # subprocess on exactly the failure path that matters.
    try:
        local = isinstance(t, LocalTransport)
        if not local and (args.type or args.oldest_first):
            sys.exit(f"--type/--oldest-first need transport = \"local\"; "
                     f"account {name!r} uses {t.name}.")
        if local:
            rows = t.search(args.query or "", args.limit or 25,
                            obj_type=args.type, oldest_first=args.oldest_first)
        else:
            rows = t.search(args.query or "", args.limit or 25)

        if args.json:
            emit_json("search", rows)
            return
        lines = [f"{len(rows)} result(s) in account {name!r} via {t.name}"]
        for r in rows:
            lines.append(f"- [{r.get('type')}] {r.get('title')}\n"
                         f"    id:  {r.get('id')}\n"
                         f"    url: {r.get('url', '')}")
        emit_text("search", "\n".join(lines))
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"search failed on the {t.name} transport: {e}")
    finally:
        t.close()


def title_of(obj: dict) -> str:
    """Pull a human title out of a page or data source object."""
    if obj.get("title"):
        joined = "".join(t.get("plain_text", "") for t in obj["title"])
        if joined:
            return joined
    for prop in (obj.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "(untitled)"
    return "(untitled)"


def cmd_read(args) -> None:
    name, t = open_transport(args)
    try:
        local = isinstance(t, LocalTransport)
        if args.transcript and not local:
            sys.exit(f"--transcript needs transport = \"local\"; "
                     f"account {name!r} uses {t.name}.")
        if local:
            # Straight through the tool so --json returns the server's own payload
            # rather than a markdown string wrapped after the fact.
            result = t.call("API-retrieve-page-markdown",
                            {"page_id": to_id(args.page),
                             "include_transcript": bool(args.transcript)})
            emit_result("read", result, as_json=args.json)
            return
        md = t.read_markdown(args.page)
        if args.json:
            emit_json("read", {"id": to_id(args.page), "markdown": md})
        else:
            emit_text("read", md)
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"read failed on the {t.name} transport: {e}")
    finally:
        t.close()


@with_client
def cmd_props(client: Notion, args) -> None:
    emit_result("props", client.call("API-retrieve-a-page", {"page_id": to_id(args.page)}),
                as_json=True)


@with_client
def cmd_db(client: Notion, args) -> None:
    """Retrieve a database and surface its data source ids -- what `query` needs."""
    payload = result_payload(client.call("API-retrieve-a-database",
                                         {"database_id": to_id(args.database)}))
    raise_if_notion_error(payload)
    if args.json or not isinstance(payload, dict):
        emit_json("db", payload)
        return
    sources = payload.get("data_sources") or []
    lines = [f"database: {title_of(payload)}",
             f"id:       {payload.get('id')}",
             f"url:      {payload.get('url', '')}",
             "",
             f"data sources ({len(sources)}) -- pass one to `query`:"]
    for s in sources:
        lines.append(f"  - {s.get('name', '(unnamed)')}\n      {s.get('id')}")
    if not sources:
        lines.append("  (none returned; the integration may lack access to this database)")
    emit_text("db", "\n".join(lines))


@with_client
def cmd_query(client: Notion, args) -> None:
    base: dict = {"data_source_id": to_id(args.data_source),
                  "page_size": min(args.limit or 100, 100)}
    if args.filter:
        base["filter"] = parse_json_arg(args.filter, "--filter")
    if args.sorts:
        base["sorts"] = parse_json_arg(args.sorts, "--sorts")
    results = paginate(client, "API-query-data-source", base, "query", args.limit)
    if args.json:
        emit_json("query", results)
        return
    lines = [f"{len(results)} row(s)"]
    for r in results:
        lines.append(f"- {title_of(r)}\n    id: {r.get('id')}\n    url: {r.get('url', '')}")
    emit_text("query", "\n".join(lines))


@with_client
def cmd_comments(client: Notion, args) -> None:
    results = paginate(client, "API-retrieve-a-comment",
                       {"block_id": to_id(args.page)}, "comments", args.limit)
    emit_json("comments", results)


@with_client
def cmd_users(client: Notion, args) -> None:
    results = paginate(client, "API-get-users", {}, "users", args.limit)
    if args.json:
        emit_json("users", results)
        return
    lines = []
    for u in results:
        email = (u.get("person") or {}).get("email", "")
        lines.append(f"- {u.get('name')} [{u.get('type')}] {email}\n    {u.get('id')}")
    emit_text("users", "\n".join(lines))


# -- Subcommands: writes (all --yes gated) -------------------------------------

def parse_json_arg(raw: str, flag: str):
    """Accept inline JSON or @path/to/file.json."""
    if raw.startswith("@"):
        path = Path(raw[1:]).expanduser()
        if not path.is_file():
            sys.exit(f"{flag}: no such file {path}")
        raw = path.read_text()
    try:
        return json.loads(raw)
    except ValueError as e:
        sys.exit(f"{flag} is not valid JSON: {e}")


def read_markdown(args) -> str | None:
    if args.md_file:
        path = Path(args.md_file).expanduser()
        if not path.is_file():
            sys.exit(f"--md-file: no such file {path}")
        return path.read_text()
    return args.md


def write_command(plan):
    """Build a write subcommand from a planner.

    ``plan(args)`` returns ``(action, run)`` and touches nothing but ``args``, so a
    dry run costs no token read and no subprocess -- previewing a write works even
    on a machine where the account's token is not configured yet. Only once --yes
    is present does the client open and ``run(client)`` fire.
    """
    def wrapper(args) -> None:
        action, run = plan(args)
        require_yes(args, action)
        name, client = open_transport(args)
        if not client.supports_writes:
            client.close()
            sys.exit(f"Account {name!r} uses the {client.name} transport, which is "
                     "read-only.\nWrites need an integration token "
                     "(transport = \"local\").")
        try:
            run(client)
        except TimeoutError as e:
            sys.exit(f"Timeout: {e}")
        except RuntimeError as e:
            sys.exit(f"MCP error: {e}")
        finally:
            client.close()
    return wrapper


def plan_create(args):
    """Create a page, then fill its body with markdown in a second call.

    API-post-page takes block JSON, not markdown, so the body goes in via
    API-update-page-markdown right after -- one page, two calls.
    """
    parent_id = to_id(args.parent)
    parent = {"type": "database_id", "database_id": parent_id} if args.in_database \
        else {"page_id": parent_id}
    properties = parse_json_arg(args.properties, "--properties") if args.properties \
        else {args.title_property: {"title": [{"text": {"content": args.title}}]}}
    body = read_markdown(args)

    where = "database" if args.in_database else "page"
    action = (f"create page {args.title!r} under {where} {parent_id}"
              + (f" with {len(body)} chars of markdown" if body else ""))

    def run(client: Notion) -> None:
        result = client.call("API-post-page", {"parent": parent, "properties": properties})
        if result.get("isError"):
            sys.exit(f"Notion error creating page: {extract_text(result)}")
        payload = result_payload(result)
        raise_if_notion_error(payload)
        page_id = payload.get("id") if isinstance(payload, dict) else None
        if not page_id:
            sys.exit(f"Page creation returned no id: {json.dumps(payload)[:300]}")
        url = payload.get("url", "") if isinstance(payload, dict) else ""
        print(f"created: {page_id}\nurl: {url}")
        if body and page_id:
            upd = client.call("API-update-page-markdown", {
                "page_id": page_id, "type": "replace_content",
                "replace_content": {"new_str": body},
            })
            if upd.get("isError"):
                sys.exit(f"Page created but body failed: {extract_text(upd)}")
            print(f"body written: {len(body)} chars")

    return action, run


def plan_update(args):
    """Edit page content as markdown: targeted find-and-replace, or a full overwrite."""
    page_id = to_id(args.page)
    body = read_markdown(args)

    if body is not None and args.edit:
        sys.exit("Pass either --md/--md-file (full overwrite) or --edit "
                 "(find-and-replace), not both.")

    if body is not None:
        action = (f"OVERWRITE the entire content of page {page_id} "
                  f"with {len(body)} chars of markdown")
        payload: dict = {"page_id": page_id, "type": "replace_content",
                         "replace_content": {"new_str": body}}
        if args.allow_deleting:
            payload["replace_content"]["allow_deleting_content"] = True
    elif args.edit:
        updates = [{"old_str": old, "new_str": new, "replace_all_matches": bool(args.all)}
                   for old, new in args.edit]
        if len(updates) > 100:
            sys.exit("update_content accepts at most 100 edits per call.")
        preview = "; ".join(f"{o[:40]!r} -> {n[:40]!r}" for o, n in args.edit)
        action = f"apply {len(updates)} edit(s) to page {page_id}: {preview}"
        payload = {"page_id": page_id, "type": "update_content",
                   "update_content": {"content_updates": updates}}
        if args.allow_deleting:
            payload["update_content"]["allow_deleting_content"] = True
    else:
        sys.exit("Nothing to do: pass --edit OLD NEW, or --md/--md-file to overwrite.")

    def run(client: Notion) -> None:
        emit_result("update", client.call("API-update-page-markdown", payload),
                    as_json=args.json)

    return action, run


def plan_set_props(args):
    props = parse_json_arg(args.properties, "--properties")
    page_id = to_id(args.page)
    action = f"set properties {list(props)} on page {page_id}"

    def run(client: Notion) -> None:
        emit_result("set-props", client.call(
            "API-patch-page", {"page_id": page_id, "properties": props}), as_json=True)

    return action, run


def plan_comment(args):
    page_id = to_id(args.page)
    action = f"post a comment on page {page_id}: {args.text[:80]!r}"

    def run(client: Notion) -> None:
        emit_result("comment", client.call("API-create-a-comment", {
            "parent": {"page_id": page_id},
            "rich_text": [{"text": {"content": args.text}}],
        }), as_json=True)

    return action, run


def plan_move(args):
    page_id, dest = to_id(args.page), to_id(args.to)
    parent = {"type": "database_id", "database_id": dest} if args.in_database \
        else {"type": "page_id", "page_id": dest}
    action = f"move page {page_id} under {dest}"

    def run(client: Notion) -> None:
        emit_result("move", client.call(
            "API-move-page", {"page_id": page_id, "parent": parent}), as_json=True)

    return action, run


def plan_archive(args):
    page_id = to_id(args.page)
    restoring = bool(args.restore)
    action = f"{'restore' if restoring else 'move to trash'} page {page_id}"

    def run(client: Notion) -> None:
        emit_result("archive", client.call(
            "API-patch-page", {"page_id": page_id, "in_trash": not restoring}), as_json=True)

    return action, run


cmd_create = write_command(plan_create)
cmd_update = write_command(plan_update)
cmd_set_props = write_command(plan_set_props)
cmd_comment = write_command(plan_comment)
cmd_move = write_command(plan_move)
cmd_archive = write_command(plan_archive)


# -- Subcommands: escape hatches -----------------------------------------------

@with_client
def cmd_tools(client: Notion, args) -> None:
    tools = client.list_tools()
    lines = [f"{len(tools)} tools on {MCP_PACKAGE}"]
    for t in sorted(tools, key=lambda x: x["name"]):
        props = list((t.get("inputSchema") or {}).get("properties", {}))
        req = (t.get("inputSchema") or {}).get("required", [])
        gate = " [WRITE]" if t["name"] in WRITE_TOOLS else ""
        lines.append(f"- {t['name']}{gate}\n    args: {props}\n    required: {req}")
    emit_text("tools", "\n".join(lines))


def plan_raw(args):
    tool_args = parse_json_arg(args.args_json, "--args") if args.args_json else {}
    action = (f"call write tool {args.tool} with {json.dumps(tool_args)[:200]}"
              if args.tool in WRITE_TOOLS else None)

    def run(client: Notion) -> None:
        emit_result("raw", client.call(args.tool, tool_args), as_json=args.json)

    return action, run


def cmd_raw(args) -> None:
    """Read tools go straight through; write tools take the same --yes gate."""
    # `raw` speaks MCP tool names, which only the local transport has. Check the
    # declared transport up front so a browser profile gets that reason instead of
    # write_command's read-only message, which is wrong for a read-only tool.
    name, entry = resolve_account(args.account)
    if account_transport(name, entry) == "browser":
        sys.exit(f"`raw` needs transport = \"local\"; account {name!r} uses browser, "
                 "which speaks Notion's private API and has no MCP tools.")
    action, run = plan_raw(args)
    if action is None:
        args.yes = True  # read-only tool: nothing to gate
    write_command(lambda a: (action or f"call {a.tool}", run))(args)


# -- Subcommand: export (recursive subtree + local assets) --------------------

# The renderer emits page/database references as a stable machine-readable
# sentinel, `[[page]] Title `<dashed-uuid>``, both as whole-line child markers
# and inline mentions. Discovering children and rewriting cross-links both key
# off this sentinel -- NOT off prose -- so the walk stays robust and works on any
# transport whose read_markdown emits it. (The ideal is a transport child_pages()
# method; until every transport has one, the sentinel is the portable contract.)
PAGE_TOKEN = re.compile(
    r"\[\[(page|database)\]\]\s*(.*?)\s*`([0-9a-fA-F][0-9a-fA-F-]{30,36})`")

EXPORT_DEPTH_DEFAULT = 3
EXPORT_MAX_PAGES = 500     # hard cap; a Notion tree can fan out without bound
EXPORT_RETRIES = 3         # per-page read attempts; a big walk trips Notion's 429
ASSET_MAX_BYTES = 50 * 1024 * 1024
ASSET_URL = re.compile(r"https://file\.notion\.com/[^\s)\"']+")


def _slugify(title: str) -> str:
    """ASCII, lowercase, hyphenated -- filenames come from a client workspace."""
    norm = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return slug[:60] or "untitled"


def _short(page_id: str) -> str:
    return page_id.replace("-", "")[:8]


def _title_from_md(md: str, page_id: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or f"page-{_short(page_id)}"
    return f"page-{_short(page_id)}"


def _child_ids(md: str) -> list[str]:
    """Ids of whole-line page markers -- the structural children, not inline mentions.

    A child-page block renders as its own line (after an optional `- ` and indent);
    an inline mention sits mid-sentence. Recursing only whole-line markers keeps a
    subtree export to the actual subtree instead of chasing every page ever mentioned.
    """
    out = []
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        m = PAGE_TOKEN.fullmatch(stripped)
        if m and m.group(1) == "page":
            out.append(m.group(3).lower())
    return out


def _rewrite_links(md: str, filenames: dict) -> str:
    """Turn in-export page/database sentinels into relative links; leave the rest visible.

    A reference to a page we exported becomes `[Title](file.md)`. One we did not
    (out of depth, a database, inaccessible) stays as the `[[page]] ... `id`` marker
    -- visibly unresolved rather than a link that goes nowhere.
    """
    def repl(m):
        title = m.group(2).strip() or "untitled"
        target = m.group(3).lower()
        fname = filenames.get(target)
        return f"[{title}]({fname})" if fname else m.group(0)
    return PAGE_TOKEN.sub(repl, md)


def _http_download(url: str) -> bytes | None:
    """Plain HTTPS GET with a browser UA. Returns bytes, or None on any failure.

    Works for already-public assets (external images, and any presigned URL that
    does not require a session cookie). Notion-hosted `file.notion.com` signed URLs
    return 403 without the session cookie (verified) -- those need the transport's
    own in-page fetch, so a transport may expose fetch_asset(url) to override this.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/151.0.0.0 Safari/537.36")})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(ASSET_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if not data or len(data) > ASSET_MAX_BYTES:
        return None
    return data


def _asset_name(url: str, data: bytes) -> str:
    """Stable, collision-proof, sanitized filename for a downloaded asset."""
    base = url.split("?", 1)[0].rsplit("/", 1)[-1] or "asset"
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-.") or "asset"
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]  # dedupe + uniqueness
    return f"{digest}-{base}"


def _download_assets(pages: dict, transport, out_dir: Path) -> dict:
    """Download every file.notion.com asset once, rewrite links to assets/<name>.

    Returns a summary {downloaded, failed, urls_failed}. A failed download leaves
    the original URL in place (never a truncated file, never a silent drop).
    """
    fetch = getattr(transport, "fetch_asset", None)  # transport may own auth'd fetch
    assets_dir = out_dir / "assets"
    urls = {u for p in pages.values() for u in ASSET_URL.findall(p["markdown"])}
    resolved: dict = {}
    failed: list = []
    for url in sorted(urls):
        data = fetch(url) if callable(fetch) else None
        if data is None:
            data = _http_download(url)
        if not data:
            failed.append(url)
            continue
        assets_dir.mkdir(parents=True, exist_ok=True)
        name = _asset_name(url, data)
        (assets_dir / name).write_bytes(data)
        resolved[url] = f"assets/{name}"
    if resolved:
        for p in pages.values():
            md = p["markdown"]
            for url, rel in resolved.items():
                md = md.replace(url, rel)
            p["markdown"] = md
    return {"downloaded": len(resolved), "failed": len(failed), "urls_failed": failed}


def cmd_export(args) -> None:
    """Walk a page subtree and write one Markdown file per page, links rewired local."""
    out_dir = Path(args.out).expanduser().resolve()
    depth = args.depth if args.depth is not None else EXPORT_DEPTH_DEFAULT
    name, t = open_transport(args)

    pages: dict = {}       # id -> {id, title, markdown, children}
    skipped: list = []     # (id, reason)
    try:
        root_id = to_id(args.root)
        queue = [(root_id, 0)]
        while queue and len(pages) < EXPORT_MAX_PAGES:
            pid, d = queue.pop(0)
            if pid in pages or any(pid == s[0] for s in skipped):
                continue  # cycle / already handled
            md = None
            for attempt in range(EXPORT_RETRIES):
                try:
                    md = t.read_markdown(pid)
                    break
                except SystemExit:
                    raise
                except Exception as e:
                    msg = str(e).splitlines()[0]
                    # A 429 is transient: a big walk trips Notion's rate limit, and
                    # dropping the page would silently truncate the tree. Back off and
                    # retry before giving up on it.
                    if "429" in msg and attempt < EXPORT_RETRIES - 1:
                        time.sleep(2 * (attempt + 1))
                        continue
                    skipped.append((pid, msg[:120]))
                    break
            if md is None:
                continue
            title = _title_from_md(md, pid)
            children = _child_ids(md)
            pages[pid] = {"id": pid, "title": title, "markdown": md, "children": children}
            if d < depth:
                for cid in children:
                    if cid not in pages:
                        queue.append((cid, d + 1))
    finally:
        # Assets need the transport's auth, so download before closing it.
        asset_summary = {"downloaded": 0, "failed": 0, "urls_failed": []}
        if args.assets and pages:
            asset_summary = _download_assets(pages, t, out_dir)
        t.close()

    if not pages:
        # Never report "nothing reachable" bare: a transient error on the root would
        # otherwise read as an empty tree. Surface exactly why each attempt failed.
        why = "; ".join(f"{sid}: {reason}" for sid, reason in skipped[:5]) or "no pages found"
        sys.exit(f"export: nothing written from {args.root!r} via {t.name} -- {why}")

    # Assign unique filenames up front, so links can be rewritten to point at them.
    filenames: dict = {}
    used: set = set()
    for pid in pages:
        base = f"{_slugify(pages[pid]['title'])}-{_short(pid)}"
        fname = f"{base}.md"
        n = 2
        while fname in used:  # near-impossible, but never overwrite a sibling
            fname = f"{base}-{n}.md"
            n += 1
        used.add(fname)
        filenames[pid] = fname

    out_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    for pid, page in pages.items():
        body = _rewrite_links(page["markdown"], filenames)
        dest = out_dir / filenames[pid]
        # Guard against any filename escaping the output dir.
        if out_dir not in dest.resolve().parents and dest.resolve() != out_dir / dest.name:
            skipped.append((pid, "unsafe filename"))
            continue
        dest.write_text(body)
        total_bytes += len(body.encode())

    lines = [f"export of {args.root!r} via {t.name} -> {out_dir}",
             f"  pages written: {len(pages)}",
             f"  total size:    {total_bytes:,} bytes"]
    if args.assets:
        lines.append(f"  assets:        {asset_summary['downloaded']} downloaded, "
                     f"{asset_summary['failed']} failed")
        for u in asset_summary["urls_failed"][:5]:
            lines.append(f"    ! {u[:90]}")
    if skipped:
        lines.append(f"  skipped:       {len(skipped)}")
        for sid, reason in skipped[:10]:
            lines.append(f"    - {sid}: {reason}")
    print("\n".join(lines))


# -- CLI -----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="notion.py",
        description="Read and write Notion across several workspaces.")
    p.add_argument("--account", "-a", default=None,
                   help="Account from the skill's settings (default: the one marked default).")
    p.add_argument("--json", action="store_true", help="Emit raw JSON instead of a digest.")

    # The same two flags on every subparser so they work on either side of the
    # subcommand. SUPPRESS is what makes that safe: without it the subparser would
    # write its own default over a value already given before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--account", "-a", default=argparse.SUPPRESS,
                        help="Account from the skill's settings.")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="Emit raw JSON instead of a digest.")

    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("accounts", parents=[common], help="List configured accounts and verify their tokens.")
    s.add_argument("--no-verify", action="store_true",
                   help="Skip the live API check (no subprocess spawned).")
    s.set_defaults(func=cmd_accounts)

    s = sub.add_parser("search", parents=[common], help="Search pages and data sources BY TITLE.")
    s.add_argument("query", nargs="?", help="Title text. Omit to list everything shared.")
    s.add_argument("--type", choices=["page", "data_source"], help="Restrict object type.")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--oldest-first", action="store_true")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("read", parents=[common], help="Read a page's content as Markdown.")
    s.add_argument("page", help="Page URL or id.")
    s.add_argument("--transcript", action="store_true",
                   help="Include meeting-note transcripts instead of a placeholder link.")
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("export", parents=[common],
                       help="Recursively export a page subtree to Markdown files.")
    s.add_argument("root", help="Root page URL or id.")
    s.add_argument("--out", required=True, help="Output directory.")
    s.add_argument("--depth", type=int, default=None,
                   help=f"How many levels of child pages to follow (default {EXPORT_DEPTH_DEFAULT}).")
    s.add_argument("--assets", action="store_true",
                   help="Download images/files locally and rewrite links to assets/.")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("props", parents=[common], help="Read a page's property values as JSON.")
    s.add_argument("page")
    s.set_defaults(func=cmd_props)

    s = sub.add_parser("db", parents=[common], help="Describe a database and list its data source ids.")
    s.add_argument("database", help="Database URL or id.")
    s.set_defaults(func=cmd_db)

    s = sub.add_parser("query", parents=[common], help="Query a DATA SOURCE (not a database id -- see `db`).")
    s.add_argument("data_source", help="Data source id from `db`.")
    s.add_argument("--filter", help="Filter object as JSON, or @file.json.")
    s.add_argument("--sorts", help="Sorts array as JSON, or @file.json.")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("comments", parents=[common], help="List comments on a page.")
    s.add_argument("page")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_comments)

    s = sub.add_parser("users", parents=[common], help="List workspace members.")
    s.add_argument("--limit", type=int, default=100)
    s.set_defaults(func=cmd_users)

    s = sub.add_parser("create", parents=[common], help="Create a page (write; needs --yes).")
    s.add_argument("--parent", required=True, help="Parent page or database URL/id.")
    s.add_argument("--in-database", action="store_true",
                   help="Treat --parent as a database rather than a page.")
    s.add_argument("--title", default="Untitled")
    s.add_argument("--title-property", default="title",
                   help="Name of the title property when creating in a database.")
    s.add_argument("--properties", help="Full properties object as JSON, or @file.json.")
    s.add_argument("--md", help="Page body as Markdown.")
    s.add_argument("--md-file", help="Read the page body from a Markdown file.")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_create)

    s = sub.add_parser("update", parents=[common], help="Edit page content as Markdown (write; needs --yes).")
    s.add_argument("page")
    s.add_argument("--edit", nargs=2, metavar=("OLD", "NEW"), action="append",
                   help="Find-and-replace. Repeatable, up to 100.")
    s.add_argument("--all", action="store_true",
                   help="With --edit, replace every match instead of the first.")
    s.add_argument("--md", help="Replace the WHOLE page with this Markdown.")
    s.add_argument("--md-file", help="Replace the WHOLE page with this file's Markdown.")
    s.add_argument("--allow-deleting", action="store_true",
                   help="Permit removing child pages/databases the edit drops.")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("set-props", parents=[common], help="Set page properties (write; needs --yes).")
    s.add_argument("page")
    s.add_argument("--properties", required=True, help="Properties object as JSON, or @file.json.")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_set_props)

    s = sub.add_parser("comment", parents=[common], help="Post a comment on a page (write; needs --yes).")
    s.add_argument("page")
    s.add_argument("text")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_comment)

    s = sub.add_parser("move", parents=[common], help="Move a page to a new parent (write; needs --yes).")
    s.add_argument("page")
    s.add_argument("--to", required=True, help="Destination page or database URL/id.")
    s.add_argument("--in-database", action="store_true")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_move)

    s = sub.add_parser("archive", parents=[common], help="Move a page to trash or restore it (write; needs --yes).")
    s.add_argument("page")
    s.add_argument("--restore", action="store_true", help="Pull the page back out of the trash.")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_archive)

    s = sub.add_parser("tools", parents=[common], help="List the server's tools and their arguments.")
    s.set_defaults(func=cmd_tools)

    s = sub.add_parser("raw", parents=[common], help="Call any tool directly.")
    s.add_argument("tool", help="Tool name, e.g. API-retrieve-a-block.")
    s.add_argument("--args", dest="args_json", help="Arguments as JSON, or @file.json.")
    s.add_argument("--yes", action="store_true", help="Required for write tools.")
    s.set_defaults(func=cmd_raw)

    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.account is None:
        args.account = os.environ.get("NOTION_ACCOUNT") or None
    args.func(args)


if __name__ == "__main__":
    main()
