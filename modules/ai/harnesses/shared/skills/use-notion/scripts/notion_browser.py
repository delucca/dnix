#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "websocket-client==1.9.0",
# ]
# ///
"""
notion_browser.py -- the browser transport for use-notion.

Some workspaces cannot be reached with an integration token: Notion gates its
integration platform and its MCP connector by role and by an admin allowlist, so
on those a guest or restricted member has no token to obtain. This transport
reaches such a workspace the way `use-slack` reaches Enterprise Grid -- by running
the request INSIDE a logged-in page over the Chrome DevTools Protocol.

Nothing is extracted or stored: `fetch(..., credentials: 'include')` runs in an
app.notion.com tab, so the session cookies ride along and the request originates
from Notion's own origin. There is no token on disk and nothing to rotate.

Read-only by design. It speaks Notion's private /api/v3, which is undocumented and
can change shape without notice, so it is the fallback a profile opts into -- never
the default. Writes stay on the integration transport, where the API is supported.

Usage: notion_browser.py entry-points
       notion_browser.py read <page-url-or-id>
       notion_browser.py search <query> [--limit N]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.request

import websocket  # noqa: E402

CDP_PORT = 9222              # the debug-profile Chrome that `chrome_up` manages
APP_ORIGIN = "app.notion.com"
APP_URL = f"https://{APP_ORIGIN}/"

CDP_TIMEOUT = 25
PAGE_LOAD_WAIT = 8           # seconds to let a freshly opened tab authenticate
CHUNK_LIMIT = 100            # blocks per loadPageChunk call
MAX_CHUNKS = 20              # hard stop so a huge page cannot spin forever
SEARCH_MAX_PAGES = 400       # nodes visited by the title walk before giving up
FILL_BATCH = 80              # ids per syncRecordValues call
FILL_ROUNDS = 6              # backfill passes for lazily-loaded descendants
ASSET_CALL_BUDGET = 12       # getSignedFileUrls calls per page when splitting
# Sanity bound, not a transport limit: a CDP frame carried 48 MiB base64-encoded in
# testing, so this simply refuses absurd downloads instead of buffering them whole.
ASSET_MAX_BYTES = 32 * 1024 * 1024
# 32 KiB per String.fromCharCode call -- spreading a whole image blows the argument
# limit and throws on anything but a tiny file.
B64_CHUNK = 0x8000

# Leading bytes that must match when the server declares a known image type; a
# mismatch means the buffer is truncated or is an error page, not an image.
MAGIC = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff",
         "image/gif": b"GIF8", "application/pdf": b"%PDF"}


class BrowserTransportError(Exception):
    """The browser transport could not serve the request."""


# -- CDP plumbing --------------------------------------------------------------

def _cdp_targets() -> list[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        raise BrowserTransportError(
            f"Chrome is not reachable on 127.0.0.1:{CDP_PORT} ({type(e).__name__}).\n"
            "Start it with `chrome_up`, then sign in to Notion in that window."
        )


def _open_notion_tab() -> dict:
    """Open an app.notion.com tab and return its target once it exists."""
    url = f"http://127.0.0.1:{CDP_PORT}/json/new?{APP_URL}"
    try:
        req = urllib.request.Request(url, method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            json.loads(r.read().decode())
    except Exception:
        # Older Chrome builds only accept GET on /json/new.
        try:
            with urllib.request.urlopen(url, timeout=10):
                pass
        except Exception as e:
            raise BrowserTransportError(f"Could not open a Notion tab: {e}")
    time.sleep(PAGE_LOAD_WAIT)
    for t in _cdp_targets():
        if t.get("type") == "page" and APP_ORIGIN in (t.get("url") or ""):
            return t
    raise BrowserTransportError(
        f"Opened {APP_URL} but no {APP_ORIGIN} page target appeared.")


class NotionBrowser:
    """A CDP connection to a logged-in Notion tab, used to call /api/v3 in-page."""

    def __init__(self) -> None:
        self._mid = 0
        self._ws: websocket.WebSocket | None = None

    def connect(self) -> None:
        pages = [t for t in _cdp_targets()
                 if t.get("type") == "page" and APP_ORIGIN in (t.get("url") or "")]
        target = pages[0] if pages else _open_notion_tab()
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            raise BrowserTransportError("CDP target has no webSocketDebuggerUrl.")
        try:
            # Chromium rejects any Origin not passed to --remote-allow-origins;
            # websocket-client would synthesize one, so suppress it entirely.
            self._ws = websocket.create_connection(ws_url, timeout=CDP_TIMEOUT,
                                                   suppress_origin=True)
        except Exception as e:
            raise BrowserTransportError(f"CDP websocket failed: {type(e).__name__}: {e}")

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def _eval(self, expression: str):
        if self._ws is None:
            raise BrowserTransportError("not connected")
        self._mid += 1
        mid = self._mid
        self._ws.send(json.dumps({
            "id": mid, "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True,
                       "awaitPromise": True},
        }))
        while True:
            try:
                msg = json.loads(self._ws.recv())
            except ValueError:
                continue
            except Exception as e:
                raise BrowserTransportError(f"CDP recv failed: {type(e).__name__}: {e}")
            if msg.get("id") != mid:
                continue  # interleaved event frame
            if msg.get("error"):
                raise BrowserTransportError(f"CDP error: {msg['error'].get('message')}")
            res = msg.get("result", {}).get("result", {})
            if res.get("subtype") == "error":
                raise BrowserTransportError(f"JS error: {res.get('description', '?')}")
            return res.get("value")

    def api(self, path: str, body: dict) -> dict:
        """POST to a /api/v3 path from inside the page; cookies ride along."""
        expr = (
            "(async () => {"
            f"  const r = await fetch({json.dumps('/api/v3/' + path)},"
            "    {method:'POST', headers:{'Content-Type':'application/json'},"
            "     credentials:'include', body:" + json.dumps(json.dumps(body)) + "});"
            "  const t = await r.text();"
            "  return JSON.stringify({ok:r.ok, status:r.status, body:t.slice(0,4000000)});"
            "})()"
        )
        raw = self._eval(expr)
        if raw is None:
            raise BrowserTransportError(f"{path}: no response from the page.")
        env = json.loads(raw)
        if not env.get("ok"):
            detail = (env.get("body") or "")[:300]
            if env.get("status") == 401:
                raise BrowserTransportError(
                    "Notion returned 401 -- the browser session is signed out.\n"
                    "Sign in again at https://app.notion.com in the debug Chrome window.")
            if env.get("status") == 429:
                # Bulk reads trip this. Say so plainly: a rate limit that reads as
                # "no content" is the same silent-absence failure as an auth error.
                raise BrowserTransportError(
                    f"Notion rate-limited this session (429) on {path}. Nothing is "
                    "missing -- wait a few minutes and retry. Reading many pages "
                    "back to back is what triggers it.")
            raise BrowserTransportError(f"{path}: HTTP {env.get('status')} {detail}")
        return json.loads(env["body"])


# -- record helpers ------------------------------------------------------------

def unwrap(rec) -> dict:
    """Records arrive as {value:{value:{...}}} on current builds, {value:{...}} on older."""
    if not isinstance(rec, dict):
        return {}
    v = rec.get("value")
    if isinstance(v, dict) and isinstance(v.get("value"), dict):
        return v["value"]
    return v if isinstance(v, dict) else {}


def _flush(run: list, out: list) -> None:
    """Close one formatting run, wrapping the whole thing in its markers once."""
    if not run:
        return
    (bold, italic, strike, href), parts = run[0], run[1]
    text = "".join(parts)
    run.clear()
    if not text:
        return
    # Markers must sit inside the whitespace or Markdown will not close them.
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = text.strip()
    if core:
        if bold:
            core = f"**{core}**"
        if italic:
            core = f"*{core}*"
        if strike:
            core = f"~~{core}~~"
        if href:
            core = f"[{core}]({href})"
        text = f"{lead}{core}{trail}"
    out.append(text)


def rich_text(prop, blocks: dict | None = None) -> str:
    """Flatten Notion's [[text, [[format, value]]], ...] rich-text array to Markdown.

    Formats are not decoration that can be dropped: inline code and bold are the
    two most common spans in a real workspace, and a page mention puts its target
    id in the format while its text is only the bare marker U+2023. Dropping
    formats loses the payload, not just the styling.
    """
    if not isinstance(prop, list):
        return ""
    out: list = []
    run: list = []          # [signature, [text, ...]] for the open formatting run
    for span in prop:
        if not (isinstance(span, list) and span and isinstance(span[0], str)):
            continue
        text = span[0]
        formats = span[1] if len(span) > 1 and isinstance(span[1], list) else []
        f_map: dict = {}
        for f in formats:
            if isinstance(f, list) and f:
                f_map[f[0]] = f[1] if len(f) > 1 else True

        # Mentions, equations, dates and users replace their span's text wholesale,
        # so they end any open formatting run instead of joining it.
        special = None
        if "p" in f_map or "page" in f_map:
            target = f_map.get("p") or f_map.get("page")
            title = ""
            if blocks:
                # One level only -- a mention inside the target's own title would
                # otherwise recurse.
                title = rich_text((unwrap(blocks.get(target, {})).get("properties")
                                   or {}).get("title"))
            special = f"[[page]] {title} `{target}`" if title else f"[[page]] `{target}`"
        elif "eoi" in f_map:  # inline external object; the URL lives on its block
            ref = unwrap(blocks.get(f_map["eoi"], {})) if blocks else {}
            url = (ref.get("format") or {}).get("original_url", "")
            special = f"<{url}>" if url else "[[embed]]"
        elif "e" in f_map:  # equation: value is LaTeX, text is the bare marker
            special = f"${f_map['e']}$"
        elif "d" in f_map:
            d = f_map["d"]
            special = d.get("start_date", text) if isinstance(d, dict) else text
        elif "u" in f_map:
            special = "@user"
        if special is not None:
            _flush(run, out)
            out.append(special)
            continue

        # Notion splits a styled run into one span per edit, so "**a**" + "**b**"
        # would emit `**a****b**`, which renders as literal asterisks. Buffer the
        # run and close the markers once, when the formatting actually changes.
        href = f_map.get("a")
        if not href and isinstance(f_map.get("lm"), dict):
            href = f_map["lm"].get("href")
        # Dropped on purpose: `h` (colour) and `_` (underline) have no Markdown
        # equivalent, and `m` marks a comment thread rather than content.
        # Inline code lives INSIDE the emphasis run: treating it as run-breaking
        # closes and reopens `**` between adjacent spans, emitting a literal `****`.
        if "c" in f_map and text.strip():
            text = f"`{text}`"
        sig = (("b" in f_map), ("i" in f_map), ("s" in f_map), href)
        if run and run[0] == sig:
            run[1].append(text)
        else:
            _flush(run, out)
            run[:] = [sig, [text]]
    _flush(run, out)
    return "".join(out)


def block_title(block: dict, blocks: dict | None = None) -> str:
    return rich_text((block.get("properties") or {}).get("title"), blocks)


HEX32 = re.compile(r"([0-9a-fA-F]{32})$")
DASHED = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def to_id(ref: str) -> str:
    """Notion URL / bare 32-hex / dashed UUID -> dashed UUID (id is segment-final)."""
    ref = ref.strip()
    if DASHED.fullmatch(ref):
        return ref.lower()
    seg = ref.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    m = DASHED.search(seg)
    if m:
        return m.group(0).lower()
    m = HEX32.search(seg)
    if not m:
        raise BrowserTransportError(f"No Notion id found in {ref!r}.")
    h = m.group(1).lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# -- blocks -> markdown --------------------------------------------------------

HEADINGS = {"header": "#", "sub_header": "##", "sub_sub_header": "###"}

# Only these nest their children as list items; indenting under anything else
# would invent a nesting level the document does not have.
LIST_TYPES = {"bulleted_list", "numbered_list", "to_do", "toggle"}

# Layout-only wrappers that carry no text: emit nothing, recurse at the same level.
PASSTHROUGH = {"column_list", "column", "transclusion_container", "synced_block"}

MEDIA = ("bookmark", "embed", "video", "file", "pdf", "audio")

# Blocks whose source may be an internal "attachment:" ref needing a signed URL.
ASSET_TYPES = ("image", "file", "pdf", "video", "audio")


def block_source(block: dict) -> str:
    props, fmt = block.get("properties") or {}, block.get("format") or {}
    return (rich_text(props.get("source")) or rich_text(props.get("link"))
            or fmt.get("display_source") or "")


def _prefix_lines(text: str, prefix: str) -> str:
    return "\n".join(prefix + ln for ln in text.split("\n"))


def _media_url(block: dict) -> str:
    props, fmt = block.get("properties") or {}, block.get("format") or {}
    for key in ("source", "link"):
        val = rich_text(props.get(key))
        if val:
            return val
    return fmt.get("display_source") or fmt.get("original_url") or ""


def _render_table(block: dict, blocks: dict, pad: str) -> str | None:
    """Notion table -> a GitHub-flavoured Markdown table.

    Row properties are keyed by opaque column id, so the column order in
    `format.table_block_column_order` is the only thing that makes them a table.
    """
    fmt = block.get("format") or {}
    cols = fmt.get("table_block_column_order") or []
    if not cols:
        return None
    rows = []
    for rid in block.get("content", []) or []:
        rb = unwrap(blocks.get(rid, {}))
        if rb.get("type") != "table_row":
            continue
        rp = rb.get("properties") or {}
        rows.append([rich_text(rp.get(c), blocks).replace("|", "\\|").replace("\n", " ")
                     for c in cols])
    if not rows:
        return None
    # Markdown requires a header row. Notion sets table_block_header_row when the
    # first row is styled as one; absent, that first row still reads as the header.
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return _prefix_lines("\n".join(lines), pad)


def _render(bid: str, blocks: dict, indent: int, seen: set,
            chunks: list, ordinal: int = 0, assets: dict | None = None) -> None:
    """Append (is_list_item, markdown) chunks for one block and its children."""
    if bid in seen or len(seen) > 20000:
        return
    seen.add(bid)
    block = unwrap(blocks.get(bid, {}))
    if not block:
        chunks.append((False, f"{'  ' * indent}[[unresolved block `{bid}`]]"))
        return

    btype = block.get("type", "")
    props = block.get("properties") or {}
    text = rich_text(props.get("title"), blocks)
    pad = "  " * indent
    child_indent = indent

    if btype in PASSTHROUGH:
        pass
    elif btype == "transclusion_reference":
        # A synced block: the content lives on the container it points at.
        ptr = ((block.get("format") or {})
               .get("transclusion_reference_pointer") or {}).get("id")
        if ptr and ptr in blocks:
            _render(ptr, blocks, indent, seen, chunks, assets=assets)
        else:
            chunks.append((False, f"{pad}[[synced block `{ptr or '?'}` not loaded]]"))
        return
    elif btype in HEADINGS:
        chunks.append((False, f"{HEADINGS[btype]} {text}"))
    elif btype == "bulleted_list":
        chunks.append((True, f"{pad}- {text}"))
        child_indent = indent + 1
    elif btype == "numbered_list":
        chunks.append((True, f"{pad}{ordinal or 1}. {text}"))
        child_indent = indent + 1
    elif btype == "to_do":
        mark = "x" if rich_text(props.get("checked")).lower() == "yes" else " "
        chunks.append((True, f"{pad}- [{mark}] {text}"))
        child_indent = indent + 1
    elif btype == "toggle":
        chunks.append((True, f"{pad}- {text}"))
        child_indent = indent + 1
    elif btype == "code":
        lang = rich_text(props.get("language")).lower().replace(" ", "")
        chunks.append((False, f"{pad}```{lang}\n{_prefix_lines(text, pad)}\n{pad}```"))
    elif btype == "quote":
        chunks.append((False, _prefix_lines(text, f"{pad}> ")))
    elif btype == "callout":
        icon = ((block.get("format") or {}).get("page_icon") or "").strip()
        body = f"{icon} {text}".strip() if icon else text
        chunks.append((False, _prefix_lines(body, f"{pad}> ")))
    elif btype == "divider":
        chunks.append((False, f"{pad}---"))
    elif btype == "equation":
        chunks.append((False, f"{pad}$${text}$$"))
    elif btype == "table":
        table = _render_table(block, blocks, pad)
        chunks.append((False, table or f"{pad}[[empty table]]"))
        return  # rows are consumed by the table itself
    elif btype == "image":
        src = (assets or {}).get(bid) or block_source(block)
        chunks.append((False, f"{pad}![{text or 'image'}]({src})"))
    elif btype in MEDIA:
        url = (assets or {}).get(bid) or _media_url(block)
        label = text or btype
        chunks.append((False, f"{pad}[{label}]({url})" if url else f"{pad}[[{btype}]]"))
    elif btype == "external_object_instance":
        fmt = block.get("format") or {}
        url = fmt.get("original_url", "")
        chunks.append((False, f"{pad}[{fmt.get('domain') or 'link'}]({url})"
                       if url else f"{pad}[[embed]]"))
    elif btype == "page":
        chunks.append((True, f"{pad}- [[page]] {text or '(untitled)'}  `{bid}`"))
    elif btype in ("collection_view", "collection_view_page"):
        chunks.append((True, f"{pad}- [[database]] {text or '(untitled)'}  `{bid}`"))
    elif btype == "table_of_contents":
        chunks.append((False, f"{pad}[[table of contents]]"))
    elif btype == "text":
        if text:
            chunks.append((False, f"{pad}{text}"))
        # An empty text block is Notion's blank line; the joiner already spaces.
    else:
        # Never drop a block silently -- an unhandled type must still be visible.
        chunks.append((False, f"{pad}{text}" if text else f"{pad}[[{btype or 'unknown'}]]"))

    # A child page or database is its own document: link it, never inline its body.
    # (The page being read enters through blocks_to_markdown, not here.)
    if btype in ("page", "collection_view_page"):
        return
    _render_children(block, blocks, child_indent, seen, chunks, assets)


def _render_children(block: dict, blocks: dict, indent: int, seen: set,
                     chunks: list, assets: dict | None = None) -> None:
    ordinal = 0
    for cid in block.get("content", []) or []:
        child = unwrap(blocks.get(cid, {}))
        ordinal = ordinal + 1 if child.get("type") == "numbered_list" else 0
        _render(cid, blocks, indent, seen, chunks, ordinal, assets)


def _join(chunks: list) -> str:
    """Blank line between blocks, single newline between adjacent list items."""
    out: list[str] = []
    prev_is_list = False
    for i, (is_list, text) in enumerate(chunks):
        if i:
            out.append("\n" if (is_list and prev_is_list) else "\n\n")
        out.append(text)
        prev_is_list = is_list
    return "".join(out)


def blocks_to_markdown(root_id: str, blocks: dict, assets: dict | None = None) -> str:
    """Render a loaded page to Markdown, title first.

    `assets` maps a block id to a resolved file URL. It is optional so this stays
    a pure function for callers without a transport; without it, media keeps its
    raw `attachment:` reference rather than breaking.
    """
    root = unwrap(blocks.get(root_id, {}))
    if not root:
        return ""
    seen = {root_id}
    chunks: list = []
    title = rich_text((root.get("properties") or {}).get("title"), blocks)
    if title:
        chunks.append((False, f"# {title}"))
    _render_children(root, blocks, 0, seen, chunks, assets)
    return _join(chunks)


# -- capability layer ----------------------------------------------------------

class BrowserTransport:
    """Read-only Notion access through a logged-in browser session."""

    supports_writes = False
    name = "browser"

    def __init__(self) -> None:
        self._c = NotionBrowser()
        self._c.connect()

    def close(self) -> None:
        self._c.close()

    def entry_points(self) -> dict:
        """Spaces plus the shared root pages -- a guest gets roots, not a workspace."""
        data = self._c.api("getSpaces", {})
        spaces, roots = [], []
        for user_payload in data.values():
            for sid, rec in (user_payload.get("space") or {}).items():
                v = unwrap(rec)
                spaces.append({"id": sid, "name": v.get("name", "(unnamed)"),
                               "plan": v.get("plan_type")})
            for bid, rec in (user_payload.get("block") or {}).items():
                v = unwrap(rec)
                if v.get("type") in ("page", "collection_view_page"):
                    roots.append({"id": bid, "title": block_title(v) or "(untitled)",
                                  "space": rec.get("spaceId") or v.get("space_id"),
                                  "type": v.get("type")})
        return {"spaces": spaces, "roots": roots}

    def _load_page(self, page_id: str) -> dict:
        """loadPageChunk until the page is exhausted; returns the block record map."""
        blocks: dict = {}
        cursor = {"stack": []}
        for n in range(MAX_CHUNKS):
            payload = self._c.api("loadPageChunk", {
                "pageId": page_id, "limit": CHUNK_LIMIT, "cursor": cursor,
                "chunkNumber": n, "verticalColumns": False,
            })
            rm = payload.get("recordMap") or {}
            blocks.update(rm.get("block") or {})
            cursor = payload.get("cursor") or {"stack": []}
            if not cursor.get("stack"):
                break
        if not blocks:
            raise BrowserTransportError(
                f"{page_id} returned no blocks -- the signed-in account may not have "
                "access to that page.")
        return self._fill_missing(blocks)

    def _fill_missing(self, blocks: dict) -> dict:
        """Fetch children that loadPageChunk omitted.

        Notion lazy-loads the body of a collapsed toggle (and other deferred
        subtrees), so the chunk response can reference child ids it never sends.
        Rendering straight from it silently drops that content -- a truncated
        export that looks complete. syncRecordValues resolves them by id.
        """
        # Records that arrive from syncRecordValues carry no spaceId of their own,
        # and a null spaceId is a 400 -- so keep the page's space as the fallback.
        default_space = next((r.get("spaceId") for r in blocks.values()
                              if isinstance(r, dict) and r.get("spaceId")), None)
        for _ in range(FILL_ROUNDS):
            # Carry each child's own parent space: a synced block can transclude
            # content from another space, and requesting it under the wrong
            # spaceId comes back empty.
            missing: dict = {}
            for rec in blocks.values():
                parent = unwrap(rec)
                # A linked child page keeps its body on its own page and is never
                # inlined, so fetching its children would pull hundreds of blocks
                # this render will discard.
                if parent.get("type") in ("page", "collection_view_page"):
                    continue
                parent_space = rec.get("spaceId") if isinstance(rec, dict) else None
                for cid in parent.get("content", []) or []:
                    if cid not in blocks:
                        missing.setdefault(cid, parent_space or default_space)
            if not missing:
                break
            batch = list(missing.items())[:FILL_BATCH]
            try:
                got = self._c.api("syncRecordValues", {"requests": [
                    {"pointer": {"table": "block", "id": i, "spaceId": sp},
                     "version": -1} for i, sp in batch]})
            except BrowserTransportError:
                break  # partial content beats no content; unresolved ids stay visible
            new = ((got.get("recordMap") or got).get("block")) or {}
            fetched = {k: v for k, v in new.items() if unwrap(v)}
            if not fetched:
                break
            before = len(blocks)
            blocks.update(fetched)
            if len(blocks) == before:
                break
        return blocks

    def _resolve_assets(self, blocks: dict) -> dict:
        """Map media block id -> fetchable URL for internal `attachment:` refs.

        An `attachment:` source is meaningless outside Notion, so exported Markdown
        would carry dead image links. getSignedFileUrls takes a LIST, so every
        asset on the page is resolved in one call rather than one call per image.

        The signed URL carries an `expirationTimestamp` (epoch ms, roughly 7 hours
        out): an archived export keeps working only until then, and re-reading the
        page mints fresh links. Nothing here tries to work around that.
        """
        wanted = []
        for bid, rec in blocks.items():
            v = unwrap(rec)
            if v.get("type") not in ASSET_TYPES:
                continue
            src = block_source(v)
            # Only internal refs need signing; an external https source is already usable.
            if src.startswith("attachment:"):
                wanted.append((bid, src))
        return self._sign(wanted, [ASSET_CALL_BUDGET]) if wanted else {}

    def _sign(self, items: list, budget: list) -> dict:
        """Sign a batch, splitting on failure.

        The endpoint is all-or-nothing: one unresolvable record 404s the whole
        request, which would cost a page every image because of a single stale
        asset. Halving on failure isolates the bad one while the common case --
        everything resolvable -- still costs exactly one call.
        """
        if not items or budget[0] <= 0:
            return {}
        budget[0] -= 1
        try:
            res = self._c.api("getSignedFileUrls", {"urls": [
                {"url": src, "permissionRecord": {"table": "block", "id": bid}}
                for bid, src in items]})
        except BrowserTransportError:
            if len(items) == 1:
                return {}  # unresolvable; the caller keeps the raw ref
            mid = len(items) // 2
            out = self._sign(items[:mid], budget)
            out.update(self._sign(items[mid:], budget))
            return out
        signed = res.get("signedUrls") or []
        # Positional response: pair by index, and leave any shortfall unresolved
        # rather than mismatching a URL to the wrong block.
        return {bid: signed[i] for i, (bid, _) in enumerate(items)
                if i < len(signed) and signed[i]}

    def _describe_database(self, page_id: str) -> str:
        """Render what a database exposes without its rows.

        loadPageChunk ships the collection record -- name and column schema -- but
        never the rows; those need queryCollection, whose request shape could not be
        observed because the app refuses to open either database this account can
        reach ("You may not have access"). Guessing that body could return
        plausible-but-wrong rows, so the schema is reported and the gap is stated.
        """
        payload = self._c.api("loadPageChunk", {
            "pageId": page_id, "limit": CHUNK_LIMIT, "cursor": {"stack": []},
            "chunkNumber": 0, "verticalColumns": False})
        rm = payload.get("recordMap") or {}
        colls = rm.get("collection") if isinstance(rm.get("collection"), dict) else {}
        views = rm.get("collection_view") if isinstance(rm.get("collection_view"), dict) else {}

        coll = next((unwrap(r) for r in colls.values() if unwrap(r)), {})
        name = rich_text(coll.get("name")) or "(untitled)"
        out = [f"# {name}", f"`database {page_id}`"]

        # Each section is one string: sections are separated by a blank line, but
        # the rows inside a table must not be.
        schema = coll.get("schema") or {}
        if schema:
            rows = ["| Column | Type |", "|---|---|"]
            for col in schema.values():
                label = str(col.get("name", "")).replace("|", "\\|").replace("\n", " ")
                rows.append(f"| {label} | {col.get('type', '?')} |")
            out.append("## Columns\n\n" + "\n".join(rows))
        else:
            out.append("[[schema unavailable]]")

        named_views = [f"- {unwrap(v).get('name') or '(unnamed)'} "
                       f"({unwrap(v).get('type', '?')})" for v in views.values() if unwrap(v)]
        if named_views:
            out.append("## Views\n\n" + "\n".join(named_views))

        out.append("[[rows unavailable: the browser transport cannot query a "
                   "collection -- use an account with transport = \"local\"]]")
        return "\n\n".join(out)

    def fetch_asset(self, url: str) -> bytes:
        """Download an asset through the logged-in page and return its bytes.

        A file.notion.com URL is signed but still requires the session cookies, so
        an out-of-band GET is refused with 403. Fetching in-page keeps them
        attached -- the same reason api() runs there. Runtime.evaluate can only
        return JSON, so the body comes back base64 and is decoded here.
        """
        js = """(async () => {
          try {
            const r = await fetch(%s, {credentials:'include'});
            if (!r.ok) return JSON.stringify({error:'http', status:r.status});
            const declared = r.headers.get('content-length');
            if (declared && +declared > %d)
              return JSON.stringify({error:'too_large', length:+declared});
            const buf = new Uint8Array(await r.arrayBuffer());
            if (buf.length > %d)
              return JSON.stringify({error:'too_large', length:buf.length});
            let s = '';
            for (let i = 0; i < buf.length; i += %d)
              s += String.fromCharCode.apply(null, buf.subarray(i, i + %d));
            return JSON.stringify({status:r.status, ctype:r.headers.get('content-type'),
                                   length:buf.length, declared:declared, b64:btoa(s)});
          } catch (e) { return JSON.stringify({error:'js', message:String(e)}); }
        })()""" % (json.dumps(url), ASSET_MAX_BYTES, ASSET_MAX_BYTES, B64_CHUNK, B64_CHUNK)

        raw = self._c._eval(js)
        if not raw:
            raise BrowserTransportError(f"No response fetching asset: {url[:90]}")
        env = json.loads(raw)
        if env.get("error") == "http":
            raise BrowserTransportError(
                f"Asset fetch returned HTTP {env.get('status')}. A signed Notion URL "
                "expires (~7h) and needs the session cookies; re-read the page to "
                "mint a fresh one.")
        if env.get("error") == "too_large":
            raise BrowserTransportError(
                f"Asset is {env.get('length')} bytes, over the "
                f"{ASSET_MAX_BYTES} byte cap; refusing rather than buffering it whole.")
        if env.get("error"):
            raise BrowserTransportError(f"Asset fetch failed: {env.get('message', '?')}")

        data = base64.b64decode(env.get("b64") or "")
        # A truncated buffer written out as a complete file is silent corruption,
        # so both the byte count and the type signature have to agree.
        if len(data) != env.get("length"):
            raise BrowserTransportError(
                f"Asset truncated in transfer: got {len(data)} bytes, "
                f"page read {env.get('length')}.")
        declared = env.get("declared")
        if declared and int(declared) != len(data):
            raise BrowserTransportError(
                f"Asset size mismatch: content-length {declared}, got {len(data)}.")
        ctype = (env.get("ctype") or "").split(";")[0].strip().lower()
        magic = MAGIC.get(ctype)
        if magic and not data.startswith(magic):
            raise BrowserTransportError(
                f"Asset does not match its declared type {ctype!r} "
                f"(leading bytes {data[:8]!r}); refusing to hand back a bad file.")
        return data

    def read_markdown(self, ref: str) -> str:
        page_id = to_id(ref)
        blocks = self._load_page(page_id)
        root = unwrap(blocks.get(page_id, {}))

        # A database keeps its rows in a collection, not in `content`, so the block
        # walk renders nothing. Say so instead of returning an empty string that
        # reads as "this page is blank".
        if root.get("type") in ("collection_view", "collection_view_page"):
            return self._describe_database(page_id)

        md = blocks_to_markdown(page_id, blocks, self._resolve_assets(blocks))
        if not md.strip():
            raise BrowserTransportError(
                f"{page_id} rendered no content ({len(blocks)} block(s) loaded, root "
                f"type {root.get('type', 'unknown')!r}). Refusing to report an empty "
                "page as though it were blank.")
        return md

    def search(self, query: str, limit: int = 25) -> list[dict]:
        """Title search by walking the shared roots.

        Notion's private /api/v3 search rejects every request shape we tried, and
        guessing at an undocumented body is not worth the fragility -- so this walks
        the page tree from the entry points and matches titles, which is the same
        title-only semantics the integration transport's search has.
        """
        q = query.lower().strip()
        entry = self.entry_points()
        queue = [r["id"] for r in entry["roots"]]
        seen: set = set()
        hits: list[dict] = []
        visited = 0
        while queue and visited < SEARCH_MAX_PAGES and len(hits) < limit:
            pid = queue.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            visited += 1
            try:
                blocks = self._load_page(pid)
            except BrowserTransportError:
                continue
            for bid, rec in blocks.items():
                v = unwrap(rec)
                if v.get("type") not in ("page", "collection_view_page"):
                    continue
                title = block_title(v)
                if bid not in seen:
                    queue.append(bid)
                if q and q not in title.lower():
                    continue
                if any(h["id"] == bid for h in hits):
                    continue
                hits.append({"id": bid, "title": title or "(untitled)",
                             "type": v.get("type"),
                             "url": f"https://{APP_ORIGIN}/{bid.replace('-', '')}"})
                if len(hits) >= limit:
                    break
        return hits


# -- CLI (standalone use; notion.py imports the class directly) ----------------

def main() -> None:
    p = argparse.ArgumentParser(prog="notion_browser.py",
                                description="Read Notion through a logged-in browser session.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("entry-points", help="List spaces and shared root pages.")
    s = sub.add_parser("read", help="Read a page as Markdown.")
    s.add_argument("page")
    s = sub.add_parser("search", help="Title search by walking the shared roots.")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--limit", type=int, default=25)
    args = p.parse_args()

    try:
        t = BrowserTransport()
    except BrowserTransportError as e:
        sys.exit(str(e))
    try:
        if args.cmd == "entry-points":
            e = t.entry_points()
            for sp in e["spaces"]:
                print(f"space  {sp['name']}  [{sp['plan']}]  {sp['id']}")
            for r in e["roots"]:
                print(f"root   {r['title']}  ({r['type']})  {r['id']}")
        elif args.cmd == "read":
            print(t.read_markdown(args.page))
        elif args.cmd == "search":
            for h in t.search(args.query, args.limit):
                print(f"- {h['title']}\n    {h['id']}\n    {h['url']}")
    except BrowserTransportError as e:
        sys.exit(str(e))
    finally:
        t.close()


if __name__ == "__main__":
    main()
