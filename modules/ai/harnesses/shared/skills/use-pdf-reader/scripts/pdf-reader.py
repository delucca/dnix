#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
pdf-reader.py — Read PDFs via @sylphx/pdf-reader-mcp (stdio MCP client).

Spawns pdf-reader-mcp as a short-lived subprocess, sends JSON-RPC 2.0 messages
over its stdin/stdout, and terminates it after the call. No persistent state.

Usage: pdf-reader.py read <path_or_url> [--pages "1-5"] [--metadata] [--images] [--page-count]
       pdf-reader.py raw <tool_name> --args '{...}'
       pdf-reader.py --help
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# -- Constants ----------------------------------------------------------------

NPX_REGISTRY = "--registry=https://registry.npmjs.org/"
MCP_PACKAGE = "@sylphx/pdf-reader-mcp@2.1.0"

OUT_DIR = Path.home() / ".cache" / "pdf-cm"
INLINE_LIMIT = 4000  # bytes; above this spill to disk and print path

MCP_STARTUP_TIMEOUT = 30  # seconds to wait for the initialize response
MCP_CALL_TIMEOUT = 120    # seconds per tool call (PDFs can be large)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from mcp_stdio import MCPClient  # noqa: E402


# -- Server resolution -----------------------------------------------------------

def find_server() -> list[str]:
    """The packaged pdf-reader-mcp on PATH (dnix builds it), else npx on the pinned package."""
    packaged = shutil.which("pdf-reader-mcp")
    if packaged:
        return [packaged]
    npx = shutil.which("npx")
    if npx is None:
        print(
            "Neither pdf-reader-mcp nor npx found on PATH.\n"
            "\n"
            "On a nix machine, enable dnix's ai module; elsewhere install Node.js for npx.\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return [npx, NPX_REGISTRY, "-y", MCP_PACKAGE]


# -- Output helpers ------------------------------------------------------------

def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def emit_text(label: str, text: str) -> None:
    """Print short text inline; spill large text to ~/.cache/pdf-cm/."""
    if len(text.encode()) <= INLINE_LIMIT:
        print(text)
        return
    ensure_out_dir()
    path = OUT_DIR / f"{ts()}-{label}.json"
    path.write_text(text)
    print(f"# {label}: {len(text)} chars, saved to {path}")
    print(f"# first 1500 chars:\n{text[:1500]}")


def emit_json(label: str, data: dict | list) -> None:
    emit_text(label, json.dumps(data, indent=2, ensure_ascii=False))


def extract_text_content(result: dict) -> str:
    """Extract all text items from a tools/call result, concatenated."""
    content = result.get("content", [])
    parts: list[str] = []
    for item in content:
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "\n".join(parts)


# -- Source detection ----------------------------------------------------------

def is_url(value: str) -> bool:
    """Check if a string looks like a URL."""
    return value.startswith("http://") or value.startswith("https://")


def parse_pages(pages_str: str) -> list[int | str]:
    """Parse a pages argument like '1-5' or '1,3,7' into a list for the MCP tool.

    The MCP tool accepts an array where each element is either an int (single page)
    or a string range like '1-5'.
    """
    result: list[int | str] = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            result.append(part)
        else:
            try:
                result.append(int(part))
            except ValueError:
                result.append(part)
    return result


# -- Subcommand implementations -----------------------------------------------

def with_client(fn):
    """Decorator: open client, run fn, close client. Handles errors cleanly."""
    def wrapper(*args, **kwargs):
        cmd = find_server()
        client = MCPClient(cmd, client_name="use-pdf-reader",
                           process_label="pdf-reader-mcp", call_timeout=MCP_CALL_TIMEOUT)
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
def cmd_read(client: MCPClient, args) -> None:
    source: dict = {}
    if is_url(args.path_or_url):
        source["url"] = args.path_or_url
    else:
        source["path"] = str(Path(args.path_or_url).expanduser().resolve())

    if args.pages:
        source["pages"] = parse_pages(args.pages)

    tool_args: dict = {"sources": [source]}

    # Full text is almost always what the caller wants, so always request it;
    # --metadata/--images/--page-count add their sections on top of the text.
    tool_args["include_full_text"] = True

    if args.metadata:
        tool_args["include_metadata"] = True
    if args.images:
        tool_args["include_images"] = True
    if args.page_count:
        tool_args["include_page_count"] = True

    result = client.call_tool("read_pdf", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("read", text)
    else:
        emit_json("read", result)


@with_client
def cmd_raw(client: MCPClient, args) -> None:
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        sys.exit(f"--args must be valid JSON: {e}")
    result = client.call_tool(args.tool, tool_args if tool_args else None)
    text = extract_text_content(result)
    if text:
        emit_text(f"raw-{args.tool}", text)
    else:
        emit_json(f"raw-{args.tool}", result)


# -- Argument parsing ----------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        prog="pdf-reader",
        description="Read PDFs via @sylphx/pdf-reader-mcp (stdio subprocess).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("read", help="Read a PDF (local path or URL)")
    sp.add_argument("path_or_url", help="Local file path or URL to a PDF")
    sp.add_argument("--pages", help="Page range (e.g. '1-5', '1,3,7', '3')")
    sp.add_argument("--metadata", action="store_true", help="Include PDF metadata")
    sp.add_argument("--images", action="store_true", help="Extract embedded images as base64")
    sp.add_argument("--page-count", action="store_true", dest="page_count",
                    help="Include total page count")
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("raw", help="Call any pdf-reader-mcp tool with raw JSON args")
    sp.add_argument("tool", help="Tool name (e.g. read_pdf)")
    sp.add_argument("--args", default="{}", help="JSON-encoded arguments object")
    sp.set_defaults(func=cmd_raw)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
