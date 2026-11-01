#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
nia.py -- Index and search external code/docs via nia-mcp-server (stdio MCP client).

Spawns nia-mcp-server as a short-lived subprocess via uvx, sends JSON-RPC 2.0
messages over its stdin/stdout, and terminates it after the call. No persistent state.

Usage: nia.py <subcommand> [args]
       nia.py --help
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# -- Constants ----------------------------------------------------------------

NIA_API_URL = "https://apigcp.trynia.ai/"

# Pinned so `uvx` does not float nia-mcp-server to whatever is newest on PyPI.
NIA_MCP_VERSION = "1.1.2"

OUT_DIR = Path.home() / ".cache" / "nia-cm"
INLINE_LIMIT = 4000  # bytes; above this spill to disk and print path

MCP_STARTUP_TIMEOUT = 60   # seconds to wait for initialize (uvx may install)
MCP_CALL_TIMEOUT = 180     # seconds per tool call (research/indexing are slow)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import credential  # noqa: E402
from mcp_stdio import MCPClient  # noqa: E402


# -- Preflight checks --------------------------------------------------------

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


def fetch_api_key() -> str:
    return credential.read("use-nia", "apiKey", label="Nia API key")


# -- Output helpers -----------------------------------------------------------

def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def emit_text(label: str, text: str) -> None:
    """Print short text inline; spill large text to ~/.cache/nia-cm/."""
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


# -- Client lifecycle decorator -----------------------------------------------

def with_client(fn):
    """Decorator: open client, run fn, close client. Handles errors cleanly."""
    def wrapper(*args, **kwargs):
        uvx = find_uvx()
        api_key = fetch_api_key()
        cmd = [uvx, f"nia-mcp-server@{NIA_MCP_VERSION}"]
        env = {
            "NIA_API_KEY": api_key,
            "NIA_API_URL": NIA_API_URL,
        }
        client = MCPClient(cmd, env=env, client_name="use-nia",
                           process_label="nia-mcp-server", call_timeout=MCP_CALL_TIMEOUT)
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


# -- Helper: parse comma-separated lists --------------------------------------

def parse_csv(value: str | None) -> list[str] | None:
    """Split a comma-separated string into a list, or return None."""
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


# -- Subcommand implementations -----------------------------------------------

@with_client
def cmd_index(client: MCPClient, args) -> None:
    tool_args: dict = {"url": args.url}
    if args.type:
        tool_args["resource_type"] = args.type
    if args.branch:
        tool_args["branch"] = args.branch
    result = client.call_tool("index", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("index", text)
    else:
        emit_json("index", result)


@with_client
def cmd_search(client: MCPClient, args) -> None:
    tool_args: dict = {"query": args.query}
    repos = parse_csv(args.repos)
    if repos:
        tool_args["repositories"] = repos
    sources = parse_csv(args.sources)
    if sources:
        tool_args["data_sources"] = sources
    if args.mode:
        tool_args["search_mode"] = args.mode
    result = client.call_tool("search", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("search", text)
    else:
        emit_json("search", result)


@with_client
def cmd_manage(client: MCPClient, args) -> None:
    tool_args: dict = {"action": args.action}
    if args.query:
        tool_args["query"] = args.query
    if args.id:
        tool_args["identifier"] = args.id
    if args.type:
        tool_args["resource_type"] = args.type
    if args.limit:
        tool_args["limit"] = args.limit
    result = client.call_tool("manage_resource", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("manage", text)
    else:
        emit_json("manage", result)


@with_client
def cmd_read(client: MCPClient, args) -> None:
    tool_args: dict = {"source_type": args.type}
    # source_identifier is owner/repo:path format
    tool_args["source_identifier"] = args.source_identifier
    if args.start:
        tool_args["start_line"] = args.start
    if args.end:
        tool_args["end_line"] = args.end
    result = client.call_tool("nia_read", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("read", text)
    else:
        emit_json("read", result)


@with_client
def cmd_grep(client: MCPClient, args) -> None:
    tool_args: dict = {
        "source_type": args.type,
        "pattern": args.pattern,
    }
    if args.repo:
        tool_args["repository"] = args.repo
    if args.path:
        tool_args["path"] = args.path
    if args.exhaustive:
        tool_args["exhaustive"] = True
    if args.case_sensitive:
        tool_args["case_sensitive"] = True
    result = client.call_tool("nia_grep", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("grep", text)
    else:
        emit_json("grep", result)


@with_client
def cmd_explore(client: MCPClient, args) -> None:
    tool_args: dict = {}
    if args.type:
        tool_args["source_type"] = args.type
    if args.action:
        tool_args["action"] = args.action
    if args.repo:
        tool_args["repository"] = args.repo
    if args.path:
        tool_args["path"] = args.path
    result = client.call_tool("nia_explore", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("explore", text)
    else:
        emit_json("explore", result)


@with_client
def cmd_research(client: MCPClient, args) -> None:
    tool_args: dict = {"query": args.query}
    if args.mode:
        tool_args["mode"] = args.mode
    if args.num:
        tool_args["num_results"] = args.num
    repos = parse_csv(args.repos)
    if repos:
        tool_args["repositories"] = repos
    sources = parse_csv(args.sources)
    if sources:
        tool_args["data_sources"] = sources
    result = client.call_tool("nia_research", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("research", text)
    else:
        emit_json("research", result)


@with_client
def cmd_context(client: MCPClient, args) -> None:
    tool_args: dict = {"action": args.action}
    if args.query:
        tool_args["query"] = args.query
    if args.content:
        tool_args["content"] = args.content
    if args.title:
        tool_args["title"] = args.title
    if args.id:
        tool_args["id"] = args.id
    tags = parse_csv(args.tags)
    if tags:
        tool_args["tags"] = tags
    result = client.call_tool("context", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("context", text)
    else:
        emit_json("context", result)


@with_client
def cmd_advisor(client: MCPClient, args) -> None:
    tool_args: dict = {"query": args.query}
    try:
        tool_args["codebase"] = json.loads(args.codebase)
    except json.JSONDecodeError as e:
        sys.exit(f"--codebase must be valid JSON: {e}")
    if args.format:
        tool_args["output_format"] = args.format
    result = client.call_tool("nia_advisor", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("advisor", text)
    else:
        emit_json("advisor", result)


@with_client
def cmd_tracer(client: MCPClient, args) -> None:
    tool_args: dict = {"query": args.query}
    if args.mode:
        tool_args["mode"] = args.mode
    if args.repo:
        tool_args["repository"] = args.repo
    repos = parse_csv(args.repos)
    if repos:
        tool_args["repositories"] = repos
    result = client.call_tool("tracer", tool_args)
    text = extract_text_content(result)
    if text:
        emit_text("tracer", text)
    else:
        emit_json("tracer", result)


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


# -- Argument parsing ---------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        prog="nia",
        description="Index and search external code/docs via nia-mcp-server (stdio subprocess).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # index
    sp = sub.add_parser("index", help="Index a repo, docs site, or paper")
    sp.add_argument("url", help="URL to index (GitHub repo, docs site, arXiv paper)")
    sp.add_argument("--type", choices=["repo", "docs", "paper"],
                    help="Resource type (auto-detected from URL if omitted)")
    sp.add_argument("--branch", help="Branch to index (default: main)")
    sp.set_defaults(func=cmd_index)

    # search
    sp = sub.add_parser("search", help="Semantic search across indexed sources")
    sp.add_argument("query", help="Search query")
    sp.add_argument("--repos", help="Comma-separated owner/repo list to scope search")
    sp.add_argument("--sources", help="Comma-separated data source IDs")
    sp.add_argument("--mode", choices=["unified", "repositories", "sources"],
                    help="Search mode (default: unified)")
    sp.set_defaults(func=cmd_search)

    # manage
    sp = sub.add_parser("manage", help="Manage indexed resources")
    sp.add_argument("action", choices=["list", "status", "rename", "delete", "subscribe"],
                    help="Action to perform")
    sp.add_argument("--query", help="Filter query")
    sp.add_argument("--id", help="Resource identifier")
    sp.add_argument("--type", help="Resource type filter (repo, docs, etc.)")
    sp.add_argument("--limit", type=int, help="Max results to return")
    sp.set_defaults(func=cmd_manage)

    # read
    sp = sub.add_parser("read", help="Read file content from indexed sources")
    sp.add_argument("source_identifier",
                    help="Source identifier (e.g. vercel/ai-sdk:src/index.ts)")
    sp.add_argument("--type", required=True,
                    choices=["repository", "docs", "package", "local_folder"],
                    help="Source type (required)")
    sp.add_argument("--start", type=int, help="Start line number")
    sp.add_argument("--end", type=int, help="End line number")
    sp.set_defaults(func=cmd_read)

    # grep
    sp = sub.add_parser("grep", help="Regex search in indexed code")
    sp.add_argument("pattern", help="Regex pattern to search for")
    sp.add_argument("--type", required=True, dest="type",
                    help="Source type (e.g. repository)")
    sp.add_argument("--repo", help="Repository to search (owner/repo)")
    sp.add_argument("--path", help="Path prefix to scope search")
    sp.add_argument("--exhaustive", action="store_true",
                    help="Full exhaustive scan (slower)")
    sp.add_argument("--case-sensitive", action="store_true", dest="case_sensitive",
                    help="Case-sensitive matching")
    sp.set_defaults(func=cmd_grep)

    # explore
    sp = sub.add_parser("explore", help="Browse file structure of indexed sources")
    sp.add_argument("path", nargs="?", default=None, help="Path to explore (default: root)")
    sp.add_argument("--type", help="Source type (e.g. repository)")
    sp.add_argument("--repo", help="Repository (owner/repo)")
    sp.add_argument("--action", choices=["tree", "ls"], default="tree",
                    help="tree (full tree) or ls (directory listing)")
    sp.set_defaults(func=cmd_explore)

    # research
    sp = sub.add_parser("research", help="AI-powered research")
    sp.add_argument("query", help="Research query")
    sp.add_argument("--mode", choices=["quick", "deep", "oracle"],
                    help="Research depth (default: quick)")
    sp.add_argument("--num", type=int, help="Number of results")
    sp.add_argument("--repos", help="Comma-separated owner/repo list")
    sp.add_argument("--sources", help="Comma-separated data source IDs")
    sp.set_defaults(func=cmd_research)

    # context
    sp = sub.add_parser("context", help="Cross-agent context sharing")
    sp.add_argument("action", choices=["save", "list", "retrieve", "search", "update", "delete"],
                    help="Action to perform")
    sp.add_argument("--query", help="Search/filter query")
    sp.add_argument("--content", help="Content to save/update")
    sp.add_argument("--title", help="Title for saved context")
    sp.add_argument("--id", help="Context entry ID")
    sp.add_argument("--tags", help="Comma-separated tags")
    sp.set_defaults(func=cmd_context)

    # advisor
    sp = sub.add_parser("advisor", help="Analyze code against docs")
    sp.add_argument("query", help="Analysis query")
    sp.add_argument("--codebase", required=True,
                    help='JSON codebase object: {"files": {"path": "content"}}')
    sp.add_argument("--format", choices=["markdown", "json"],
                    help="Output format")
    sp.set_defaults(func=cmd_advisor)

    # tracer
    sp = sub.add_parser("tracer", help="Live GitHub search")
    sp.add_argument("query", help="Search query")
    sp.add_argument("--mode", choices=["agent", "search", "list", "read", "glob"],
                    help="Tracer mode")
    sp.add_argument("--repo", help="Single repository (owner/repo)")
    sp.add_argument("--repos", help="Comma-separated repositories")
    sp.set_defaults(func=cmd_tracer)

    # raw
    sp = sub.add_parser("raw", help="Call any nia-mcp-server tool with raw JSON args")
    sp.add_argument("tool", help="Tool name (e.g. index, search, nia_read, nia_grep, ...)")
    sp.add_argument("--args", default="{}", help="JSON-encoded arguments object")
    sp.set_defaults(func=cmd_raw)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
