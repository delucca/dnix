#!/usr/bin/env python3
"""
use-chrome.py — Control a running Chrome browser via chrome-devtools-mcp (stdio MCP client).

Spawns chrome-devtools-mcp as a short-lived subprocess, sends JSON-RPC 2.0 messages
over its stdin/stdout, and terminates it after each skill call. Chrome must be running
with --remote-debugging-port=9222 before invoking any subcommand.

Usage: use-chrome.py <subcommand> [args]
       use-chrome.py --help
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# use-chrome runs under plain python3 (not uv); mcp_stdio is pure stdlib.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from mcp_stdio import MCPClient  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────

# chrome-devtools-mcp is launched directly with `node`, NOT via `npx`. Two reasons
# this matters on managed dev machines:
#   1. The MCP's Node engine floor is `^20.19 || ^22.12 || >=23`; some devpods bake
#      an older Node (e.g. 22.11) first in PATH, which the MCP refuses to run on.
#   2. `npx` on npm 11 (Node 24) hangs indefinitely against the legacy ~/.npmrc
#      (always-auth/unpm), so every call looked like a 30s startup timeout.
# So: resolve a compatible Node, install a *pinned* copy once into a stable cache,
# and run its bin with that Node. No floating `@latest` — a silent 1.x bump that
# dropped Node 22.11 is what broke this in the first place.
#
# On a nix machine none of that runs: dnix packages chrome-devtools-mcp with its
# own Node, and a `chrome-devtools-mcp` on PATH is used as-is. The Node/npm
# route below is the fallback for devpods and anything else without nix.
MCP_PACKAGE = "chrome-devtools-mcp"
MCP_VERSION = "1.2.0"  # bump deliberately; do not float
NPX_REGISTRY = "--registry=https://registry.npmjs.org/"
BROWSER_URL = "http://127.0.0.1:9222"
DEBUG_VERSION_URL = f"{BROWSER_URL}/json/version"
MCP_HOME = Path.home() / ".cache" / "use-chrome-mcp"
MCP_BIN = MCP_HOME / "node_modules" / MCP_PACKAGE / "build" / "src" / "bin" / "chrome-devtools-mcp.js"

# Per-user spill dir: a fixed, world-predictable /tmp/chrome-cm let any local
# user read spilled screenshots / page source (or pre-create the path). Namespace
# by uid; ensure_out_dir creates it 0700 and refuses a path we don't own.
OUT_DIR = Path(tempfile.gettempdir()) / f"chrome-cm-{os.getuid()}"
INLINE_LIMIT = 4000  # bytes; above this spill to disk and print path

MCP_STARTUP_TIMEOUT = 30   # seconds to wait for the initialize response
MCP_CALL_TIMEOUT = 60      # seconds per tool call


def _node_ok(major: int, minor: int) -> bool:
    return major >= 23 or (major == 22 and minor >= 12) or (major == 20 and minor >= 19)


def _node_version(node: str) -> tuple[int, int, int] | None:
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None
    m = re.match(r"v(\d+)\.(\d+)\.(\d+)", out)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _nvm_best_node() -> str | None:
    roots = [os.environ.get("NVM_DIR", ""), "/opt/nodejs/.nvm", str(Path.home() / ".nvm")]
    best: tuple[tuple[int, int, int], str] | None = None
    for root in roots:
        if not root:
            continue
        base = Path(root) / "versions" / "node"
        if not base.is_dir():
            continue
        for vdir in base.iterdir():
            m = re.match(r"v(\d+)\.(\d+)\.(\d+)$", vdir.name)
            node = vdir / "bin" / "node"
            if not m or not node.exists():
                continue
            ver = (int(m[1]), int(m[2]), int(m[3]))
            if _node_ok(ver[0], ver[1]) and (best is None or ver > best[0]):
                best = (ver, str(node))
    return best[1] if best else None


def _resolve_node() -> str:
    # Volta (laptop) first, if it satisfies the engine.
    volta = Path.home() / ".volta/bin/node"
    if volta.exists():
        v = _node_version(str(volta))
        if v and _node_ok(*v[:2]):
            return str(volta)
    # Newest nvm-installed Node that satisfies the engine (covers devpods whose
    # baked-in PATH Node is too old).
    nvm = _nvm_best_node()
    if nvm:
        return nvm
    # PATH Node, only if it satisfies the engine.
    which = shutil.which("node")
    if which:
        v = _node_version(which)
        if v and _node_ok(*v[:2]):
            return which
    return "node"


PACKAGED_MCP = shutil.which("chrome-devtools-mcp")
NODE = "node" if PACKAGED_MCP else _resolve_node()
NPM = str(Path(NODE).with_name("npm")) if os.path.isabs(NODE) else "npm"

# Run the MCP with the chosen Node's bin dir first in PATH so its watchdog child
# (spawned via process.execPath) resolves the same Node regardless of the devpod's
# baked-in PATH.
MCP_ENV = dict(os.environ)
if os.path.isabs(NODE):
    MCP_ENV["PATH"] = os.path.dirname(NODE) + os.pathsep + MCP_ENV.get("PATH", "")

MCP_CMD = ([PACKAGED_MCP] if PACKAGED_MCP else [NODE, str(MCP_BIN)]) + [f"--browserUrl={BROWSER_URL}"]


def _installed_mcp_version() -> str | None:
    """Version recorded in the cached package's package.json, or None if absent."""
    pkg = MCP_HOME / "node_modules" / MCP_PACKAGE / "package.json"
    try:
        return json.loads(pkg.read_text()).get("version")
    except (OSError, json.JSONDecodeError):
        return None


def ensure_mcp_installed() -> None:
    """Install the pinned chrome-devtools-mcp into MCP_HOME. Idempotent.

    Reinstalls when the on-disk version differs from MCP_VERSION so a deliberate
    pin bump actually takes effect -- a bare MCP_BIN.exists() check would leave
    whatever version was installed first running forever, defeating the pinning.
    """
    if PACKAGED_MCP or (MCP_BIN.exists() and _installed_mcp_version() == MCP_VERSION):
        return
    MCP_HOME.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [NPM, "install", "--prefix", str(MCP_HOME), f"{MCP_PACKAGE}@{MCP_VERSION}",
             NPX_REGISTRY, "--no-audit", "--no-fund", "--loglevel=error"],
            env=MCP_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
    except FileNotFoundError:
        sys.exit(f"npm not found at {NPM!r}. Install Node via Volta/nvm or put npm on PATH.")
    if proc.returncode != 0 or not MCP_BIN.exists():
        sys.exit(f"Failed to install {MCP_PACKAGE}@{MCP_VERSION} into {MCP_HOME}:\n{proc.stderr}")


# ── Preflight check ────────────────────────────────────────────────────────────

def check_chrome() -> dict:
    """Verify Chrome is reachable on the debug port. Exit 1 with instructions if not."""
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(DEBUG_VERSION_URL, timeout=3) as r:
            data = json.loads(r.read())
            return data
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        print(
            "Chrome not reachable at 127.0.0.1:9222.\n"
            "\n"
            "On the laptop: run `chrome_up` (launchd debug-profile Chrome).\n"
            "On a remote machine: Chrome AND the reverse tunnel must be up on the\n"
            "laptop (chrome_up there; launchd agent com.chrome-devtools.tunnel-<host>).\n"
            "\n"
            "Ad-hoc fallback on macOS:\n"
            "    open -a \"Google Chrome\" --args --remote-debugging-port=9222 --no-first-run\n"
            "\n"
            "Wait ~2 seconds, then retry. Verify with:\n"
            "    curl http://127.0.0.1:9222/json/version\n",
            file=sys.stderr,
        )
        sys.exit(1)


# ── Output helpers ─────────────────────────────────────────────────────────────

def ensure_out_dir() -> None:
    OUT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = OUT_DIR.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        sys.exit(f"Refusing to use {OUT_DIR}: not a directory you own.")
    if st.st_mode & 0o077:
        OUT_DIR.chmod(0o700)


def ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def emit_text(label: str, text: str) -> None:
    """Print short text inline; spill large text to /tmp/chrome-cm-<uid>/."""
    ensure_out_dir()
    if len(text.encode()) <= INLINE_LIMIT:
        print(text)
        return
    ext = "html" if "<html" in text[:200].lower() else "txt"
    path = OUT_DIR / f"{ts()}-{label}.{ext}"
    path.write_text(text)
    print(f"# {label}: {len(text)} chars, saved to {path}")
    print(f"# first 1500 chars:\n{text[:1500]}")


def emit_json(label: str, data: dict | list) -> None:
    emit_text(label, json.dumps(data, indent=2, ensure_ascii=False))


def save_image(label: str, b64_data: str, output: str | None = None) -> Path:
    """Decode a base64 PNG and save it. Returns the saved path."""
    return save_binary(label, b64_data, "png", output)


def save_binary(label: str, b64_data: str, ext: str, output: str | None = None) -> Path:
    ensure_out_dir()
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path = OUT_DIR / f"{ts()}-{label}.{ext}"
    path.write_bytes(base64.b64decode(b64_data))
    return path


def extract_content(result: dict) -> tuple[str | None, str | None, str | None]:
    """Extract (text, image_b64, mime_type) from a tools/call result."""
    content = result.get("content", [])
    text_out: str | None = None
    image_b64: str | None = None
    mime: str | None = None
    for item in content:
        t = item.get("type")
        if t == "text" and text_out is None:
            text_out = item.get("text", "")
        elif t == "image" and image_b64 is None:
            image_b64 = item.get("data", "")
            mime = item.get("mimeType", "image/png")
        elif t == "resource":
            # Some tools wrap their response in a resource blob
            res = item.get("resource", {})
            if "text" in res and text_out is None:
                text_out = res["text"]
            elif "blob" in res and image_b64 is None:
                image_b64 = res["blob"]
                mime = res.get("mimeType", "application/octet-stream")
    return text_out, image_b64, mime


# ── JS helpers ─────────────────────────────────────────────────────────────────

# evaluate_script expects a function declaration, not a bare expression.
_FUNC_RE = re.compile(r"^\s*(async\s+)?(function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")

# CSS selector by default; XPath when the selector starts with "/" or "(".
_FIND_EL_JS = (
    "const findEl = (sel) => sel.startsWith('/') || sel.startsWith('(')\n"
    "    ? document.evaluate(sel, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue\n"
    "    : document.querySelector(sel);"
)


def as_function(expression: str) -> str:
    """Pass function declarations through; wrap bare expressions."""
    if _FUNC_RE.match(expression):
        return expression
    return f"() => {{ return ( {expression} ); }}"


def nav(client: MCPClient, url: str) -> dict:
    return client.call_tool("navigate_page", {"type": "url", "url": url})


# ── Subcommand implementations ─────────────────────────────────────────────────

def with_client(fn):
    """Decorator: open client, run fn, close client. Handles errors cleanly."""
    def wrapper(*args, **kwargs):
        check_chrome()
        ensure_mcp_installed()
        client = MCPClient(MCP_CMD, env=MCP_ENV, client_name="use-chrome",
                           process_label="chrome-devtools-mcp", call_timeout=MCP_CALL_TIMEOUT)
        try:
            client.initialize(MCP_STARTUP_TIMEOUT)
            return fn(client, *args, **kwargs)
        except TimeoutError as e:
            sys.exit(f"Timeout: {e}")
        except RuntimeError as e:
            sys.exit(f"MCP error: {e}")
        finally:
            client.close()
    return wrapper


@with_client
def cmd_screenshot(client: MCPClient, args) -> None:
    if args.url:
        nav(client, args.url)
    if args.width or args.height:
        if not (args.width and args.height):
            sys.exit("Provide both --width and --height to resize the page before screenshotting.")
        client.call_tool("resize_page", {"width": args.width, "height": args.height})
    ensure_out_dir()
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path = OUT_DIR / f"{ts()}-screenshot.png"
    tool_args: dict = {"filePath": str(path)}
    if args.full_page:
        tool_args["fullPage"] = True
    result = client.call_tool("take_screenshot", tool_args)
    text, image_b64, mime = extract_content(result)
    if image_b64:
        # Fallback: some versions attach the image instead of honoring filePath
        path = save_image("screenshot", image_b64, str(path))
    if path.exists():
        print(f"Screenshot saved to: {path}")
        print("# Read the file above with the Read tool to view the image inline.")
    else:
        sys.exit(f"screenshot returned unexpected result: {text or result}")


@with_client
def cmd_navigate(client: MCPClient, args) -> None:
    result = nav(client, args.url)
    text, _, _ = extract_content(result)
    if text:
        emit_text("navigate", text)
    else:
        emit_json("navigate", result)


@with_client
def cmd_evaluate(client: MCPClient, args) -> None:
    if args.url:
        nav(client, args.url)
    result = client.call_tool("evaluate_script", {"function": as_function(args.expression)})
    text, _, _ = extract_content(result)
    if text is not None:
        emit_text("evaluate", text)
    else:
        emit_json("evaluate", result)


@with_client
def cmd_source(client: MCPClient, args) -> None:
    if args.url:
        nav(client, args.url)
    result = client.call_tool(
        "evaluate_script", {"function": "() => document.documentElement.outerHTML"}
    )
    text, _, _ = extract_content(result)
    if text:
        emit_text("source", text)
    else:
        emit_json("source", result)


def cmd_pdf(args) -> None:
    sys.exit(
        "pdf: not supported — chrome-devtools-mcp no longer exposes a PDF tool.\n"
        "Workaround: use `screenshot --full-page`, or print via Chrome on the host."
    )


@with_client
def cmd_click(client: MCPClient, args) -> None:
    if args.url:
        nav(client, args.url)
    # The native click tool takes a11y-snapshot uids, not selectors — use JS instead.
    fn = (
        "() => {\n"
        f"  {_FIND_EL_JS}\n"
        f"  const sel = {json.dumps(args.selector)};\n"
        "  const el = findEl(sel);\n"
        "  if (!el) throw new Error('no element matches: ' + sel);\n"
        "  el.click();\n"
        "  return 'clicked: ' + sel;\n"
        "}"
    )
    result = client.call_tool("evaluate_script", {"function": fn})
    text, _, _ = extract_content(result)
    print(text if text else "click succeeded")


@with_client
def cmd_fill(client: MCPClient, args) -> None:
    if args.url:
        nav(client, args.url)
    fn = (
        "() => {\n"
        f"  {_FIND_EL_JS}\n"
        f"  const sel = {json.dumps(args.selector)};\n"
        "  const el = findEl(sel);\n"
        "  if (!el) throw new Error('no element matches: ' + sel);\n"
        "  el.focus();\n"
        f"  el.value = {json.dumps(args.value)};\n"
        "  el.dispatchEvent(new Event('input', {bubbles: true}));\n"
        "  el.dispatchEvent(new Event('change', {bubbles: true}));\n"
        "  return 'filled: ' + sel;\n"
        "}"
    )
    result = client.call_tool("evaluate_script", {"function": fn})
    text, _, _ = extract_content(result)
    print(text if text else "fill succeeded")


@with_client
def cmd_cookies(client: MCPClient, args) -> None:
    if args.url:
        nav(client, args.url)
    # No cookie tool in chrome-devtools-mcp — document.cookie misses HttpOnly cookies.
    result = client.call_tool("evaluate_script", {"function": "() => document.cookie"})
    text, _, _ = extract_content(result)
    if text:
        emit_text("cookies", text)
        print("# Note: document.cookie only — HttpOnly cookies are not visible.")
    else:
        emit_json("cookies", result)


@with_client
def cmd_raw(client: MCPClient, args) -> None:
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        sys.exit(f"--args must be valid JSON: {e}")
    result = client.call_tool(args.tool, tool_args if tool_args else None)
    text, image_b64, mime = extract_content(result)
    if image_b64:
        ext = "png" if "image" in (mime or "") else "bin"
        path = save_binary(args.tool, image_b64, ext)
        print(f"Binary result saved to: {path}")
    elif text:
        emit_text(f"raw-{args.tool}", text)
    else:
        emit_json(f"raw-{args.tool}", result)


# ── Argument parsing ───────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="use-chrome",
        description="Control a running Chrome browser via chrome-devtools-mcp (stdio subprocess).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("screenshot", help="Take a screenshot of the current tab (or a URL)")
    sp.add_argument("--url", help="Navigate to this URL before screenshotting")
    sp.add_argument("--output", help="Save path for the PNG (default: /tmp/chrome-cm-<uid>/)")
    sp.add_argument("--full-page", action="store_true", dest="full_page",
                    help="Capture the full scrollable page")
    sp.add_argument("--width", type=int, help="Viewport width in px")
    sp.add_argument("--height", type=int, help="Viewport height in px")
    sp.set_defaults(func=cmd_screenshot)

    sp = sub.add_parser("navigate", help="Navigate to a URL and return the page title + URL")
    sp.add_argument("url", help="URL to navigate to")
    sp.set_defaults(func=cmd_navigate)

    sp = sub.add_parser("evaluate", help="Evaluate a JavaScript expression in the current tab")
    sp.add_argument("expression", help="JS expression (e.g. 'document.title')")
    sp.add_argument("--url", help="Navigate to this URL first")
    sp.set_defaults(func=cmd_evaluate)

    sp = sub.add_parser("source", help="Get the page's HTML source")
    sp.add_argument("--url", help="Navigate to this URL first")
    sp.set_defaults(func=cmd_source)

    sp = sub.add_parser("pdf", help="Print the page to PDF")
    sp.add_argument("--url", help="Navigate to this URL first")
    sp.add_argument("--output", help="Save path for the PDF (default: /tmp/chrome-cm-<uid>/)")
    sp.add_argument("--format", choices=["A4", "Letter", "Legal"], help="Page format")
    sp.set_defaults(func=cmd_pdf)

    sp = sub.add_parser("click", help="Click a DOM element by CSS selector or XPath")
    sp.add_argument("selector", help="CSS selector or XPath (e.g. '#submit' or '//button')")
    sp.add_argument("--url", help="Navigate to this URL first")
    sp.set_defaults(func=cmd_click)

    sp = sub.add_parser("fill", help="Fill a form field with a value")
    sp.add_argument("selector", help="CSS selector (e.g. 'input[name=email]')")
    sp.add_argument("value", help="Text value to enter")
    sp.add_argument("--url", help="Navigate to this URL first")
    sp.set_defaults(func=cmd_fill)

    sp = sub.add_parser("cookies", help="Get cookies for the current tab")
    sp.add_argument("--url", help="Navigate to this URL first")
    sp.set_defaults(func=cmd_cookies)

    sp = sub.add_parser("raw", help="Call any chrome-devtools-mcp tool with raw JSON args")
    sp.add_argument("tool", help="Tool name (e.g. scroll, hover, wait_for_element, set_cookies)")
    sp.add_argument("--args", default="{}", help="JSON-encoded arguments object")
    sp.set_defaults(func=cmd_raw)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
