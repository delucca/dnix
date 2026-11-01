#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
bright-data.py -- Scrape pages and search the web via Bright Data MCP (stdio subprocess).

Spawns @brightdata/mcp as a short-lived subprocess, sends JSON-RPC 2.0 messages
over its stdin/stdout, and terminates it after each skill call. The API token is
read at use time through the configured secret reader.

Usage: bright-data.py <subcommand> [args]
       bright-data.py --help
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
MCP_PACKAGE = "@brightdata/mcp@2.11.0"

OUT_DIR = Path.home() / ".cache" / "bright-data-cm"
INLINE_LIMIT = 4000  # bytes; above this spill to disk and print path

MCP_STARTUP_TIMEOUT = 30   # seconds to wait for the initialize response
MCP_CALL_TIMEOUT = 120     # seconds per tool call (anti-bot proxying is slow)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import credential  # noqa: E402
from mcp_stdio import MCPClient  # noqa: E402


# -- Auth & environment -------------------------------------------------------

def get_api_token() -> str:
    return credential.read("use-bright-data", "apiToken", label="Bright Data API token")


def find_server() -> list[str]:
    """The packaged brightdata-mcp on PATH, else npx on the pinned package."""
    packaged = shutil.which("brightdata-mcp")
    if packaged:
        return [packaged]
    npx = shutil.which("npx")
    if not npx:
        sys.exit(
            "Neither brightdata-mcp nor npx found on PATH.\n"
            "Enable the skill through dnix's ai module, which installs brightdata-mcp, or install Node.js for npx."
        )
    return [npx, NPX_REGISTRY, "-y", MCP_PACKAGE]


# -- Output helpers ------------------------------------------------------------

def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def emit_text(label: str, text: str) -> None:
    """Print short text inline; spill large text to ~/.cache/bright-data-cm/."""
    ensure_out_dir()
    if len(text.encode()) <= INLINE_LIMIT:
        print(text)
        return
    ext = "md" if not text.strip().startswith("<") else "html"
    path = OUT_DIR / f"{ts()}-{label}.{ext}"
    path.write_text(text)
    print(f"# {label}: {len(text)} chars, saved to {path}")
    print(f"# first 1500 chars:\n{text[:1500]}")


def emit_json(label: str, data: dict | list) -> None:
    emit_text(label, json.dumps(data, indent=2, ensure_ascii=False))


def extract_text(result: dict) -> str | None:
    """Extract text content from a tools/call result."""
    content = result.get("content", [])
    for item in content:
        if item.get("type") == "text":
            return item.get("text", "")
        if item.get("type") == "resource":
            res = item.get("resource", {})
            if "text" in res:
                return res["text"]
    return None


# -- Client lifecycle decorator ------------------------------------------------

def with_client(fn):
    """Decorator: fetch token, open client, run fn, close client."""
    def wrapper(*args, **kwargs):
        token = get_api_token()
        cmd = find_server()
        client = MCPClient(cmd, env={"API_TOKEN": token}, client_name="use-bright-data",
                           process_label="MCP", call_timeout=MCP_CALL_TIMEOUT)
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


# -- Subcommand implementations ------------------------------------------------

@with_client
def cmd_scrape(client: MCPClient, args) -> None:
    result = client.call_tool("scrape_as_markdown", {"url": args.url})
    text = extract_text(result)
    if text:
        emit_text("scrape", text)
    else:
        emit_json("scrape", result)


@with_client
def cmd_batch_scrape(client: MCPClient, args) -> None:
    if len(args.urls) > 5:
        sys.exit("batch-scrape supports a maximum of 5 URLs per call.")
    result = client.call_tool("scrape_batch", {"urls": args.urls})
    text = extract_text(result)
    if text:
        emit_text("batch-scrape", text)
    else:
        emit_json("batch-scrape", result)


@with_client
def cmd_search(client: MCPClient, args) -> None:
    tool_args: dict = {"query": args.query}
    if args.engine:
        tool_args["engine"] = args.engine
    if args.geo:
        tool_args["geo_location"] = args.geo
    result = client.call_tool("search_engine", tool_args)
    text = extract_text(result)
    if text:
        emit_text("search", text)
    else:
        emit_json("search", result)


@with_client
def cmd_batch_search(client: MCPClient, args) -> None:
    if len(args.queries) > 5:
        sys.exit("batch-search supports a maximum of 5 queries per call.")
    queries = []
    for q in args.queries:
        entry: dict = {"query": q}
        if args.engine:
            entry["engine"] = args.engine
        if args.geo:
            entry["geo_location"] = args.geo
        queries.append(entry)
    result = client.call_tool("search_engine_batch", {"queries": queries})
    text = extract_text(result)
    if text:
        emit_text("batch-search", text)
    else:
        emit_json("batch-search", result)


@with_client
def cmd_discover(client: MCPClient, args) -> None:
    tool_args: dict = {"query": args.query}
    if args.intent:
        tool_args["intent"] = args.intent
    if args.num:
        tool_args["num_results"] = args.num
    if args.country:
        tool_args["country"] = args.country
    if args.language:
        tool_args["language"] = args.language
    if args.start_date:
        tool_args["start_date"] = args.start_date
    if args.end_date:
        tool_args["end_date"] = args.end_date
    result = client.call_tool("discover", tool_args)
    text = extract_text(result)
    if text:
        emit_text("discover", text)
    else:
        emit_json("discover", result)


@with_client
def cmd_raw(client: MCPClient, args) -> None:
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        sys.exit(f"--args must be valid JSON: {e}")
    result = client.call_tool(args.tool, tool_args if tool_args else None)
    text = extract_text(result)
    if text:
        emit_text(f"raw-{args.tool}", text)
    else:
        emit_json(f"raw-{args.tool}", result)


# -- Argument parsing ----------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        prog="bright-data",
        description="Scrape pages and search the web via Bright Data MCP (stdio subprocess).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # scrape
    sp = sub.add_parser("scrape", help="Scrape a single URL as markdown")
    sp.add_argument("url", help="URL to scrape")
    sp.set_defaults(func=cmd_scrape)

    # batch-scrape
    sp = sub.add_parser("batch-scrape", help="Scrape multiple URLs as markdown (max 5)")
    sp.add_argument("urls", nargs="+", help="URLs to scrape (1-5)")
    sp.set_defaults(func=cmd_batch_scrape)

    # search
    sp = sub.add_parser("search", help="Search via Google/Bing/Yandex")
    sp.add_argument("query", help="Search query")
    sp.add_argument("--engine", choices=["google", "bing", "yandex"],
                    default=None, help="Search engine (default: google)")
    sp.add_argument("--geo", default=None,
                    help="2-letter country code for geo-targeted results")
    sp.set_defaults(func=cmd_search)

    # batch-search
    sp = sub.add_parser("batch-search", help="Multiple search queries at once (max 5)")
    sp.add_argument("queries", nargs="+", help="Search queries (1-5)")
    sp.add_argument("--engine", choices=["google", "bing", "yandex"],
                    default=None, help="Search engine (default: google)")
    sp.add_argument("--geo", default=None,
                    help="2-letter country code for geo-targeted results")
    sp.set_defaults(func=cmd_batch_search)

    # discover
    sp = sub.add_parser("discover", help="AI-ranked web search")
    sp.add_argument("query", help="Search query")
    sp.add_argument("--intent", default=None,
                    help="Goal of the search for AI relevance ranking")
    sp.add_argument("--num", type=int, default=None,
                    help="Number of results to return")
    sp.add_argument("--country", default=None,
                    help="2-letter ISO country code")
    sp.add_argument("--language", default=None, help="Language filter")
    sp.add_argument("--start-date", default=None, dest="start_date",
                    help="Start date filter (YYYY-MM-DD)")
    sp.add_argument("--end-date", default=None, dest="end_date",
                    help="End date filter (YYYY-MM-DD)")
    sp.set_defaults(func=cmd_discover)

    # raw
    sp = sub.add_parser("raw", help="Call any Bright Data MCP tool with raw JSON args")
    sp.add_argument("tool", help="Tool name (e.g. discover, scrape_as_markdown)")
    sp.add_argument("--args", default="{}", help="JSON-encoded arguments object")
    sp.set_defaults(func=cmd_raw)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
