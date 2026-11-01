#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==1.27.2"]
# ///
"""
figma.py -- read-only client for the Figma desktop app's MCP server.

Talks to the Dev Mode MCP server the desktop app serves on localhost, runs one
read, prints the result, and exits. Only the tools in READ_TOOLS can be called:
the server also exposes Code Connect writes, and this skill is read-only.

Subcommands:
  status                           is the desktop server up, and what does it serve
  tools                            the readable tools (name + summary)
  describe <tool>                  one tool's input schema
  get <tool|alias> [url] [--args JSON]   run a read; a Figma URL fills nodeId/fileKey

Aliases: board=get_figjam context=get_design_context outline=get_metadata
         shot=get_screenshot vars=get_variable_defs motion=get_motion_context
         code-connect=get_code_connect_map
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
import urllib.parse
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

ENDPOINT = os.environ.get("FIGMA_MCP_URL", "http://127.0.0.1:3845/mcp")
TIMEOUT = 120.0

READ_TOOLS = {
    "get_design_context",
    "get_metadata",
    "get_screenshot",
    "get_variable_defs",
    "get_motion_context",
    "get_figjam",
    "get_code_connect_map",
    "list_shaders",
    "get_shader",
}
ALIASES = {
    "board": "get_figjam",
    "context": "get_design_context",
    "outline": "get_metadata",
    "shot": "get_screenshot",
    "vars": "get_variable_defs",
    "motion": "get_motion_context",
    "code-connect": "get_code_connect_map",
}

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from emit import make_emit, secure_cache_dir  # noqa: E402

OUT_DIR = secure_cache_dir("figma")
emit = make_emit(OUT_DIR)


def parse_url(url: str) -> dict:
    """Pull fileKey and nodeId out of a figma.com design/board/file URL.

    URLs carry node-id as 12-34 (sometimes 12%3A34); the server wants 12:34.
    """
    u = urllib.parse.urlparse(url)
    if not u.netloc.endswith("figma.com"):
        sys.exit(f"Not a Figma URL: {url}")
    out = {}
    m = re.match(r"/(?:design|board|file|proto|make|slides)/([A-Za-z0-9]+)", u.path)
    if m:
        out["fileKey"] = m.group(1)
    node = urllib.parse.parse_qs(u.query).get("node-id", [None])[0]
    if node:
        out["nodeId"] = node.replace("-", ":")
    return out


@asynccontextmanager
async def open_session():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with AsyncExitStack() as stack:
        read, write, _ = await stack.enter_async_context(streamable_http_client(ENDPOINT))
        session = await stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=TIMEOUT)
        yield session


async def list_tools(session):
    res = await asyncio.wait_for(session.list_tools(), timeout=TIMEOUT)
    return res.tools


def render(result, label: str) -> str:
    """Flatten a tool result to text; images are written to disk for Read."""
    parts: list[str] = []
    for i, block in enumerate(getattr(result, "content", None) or []):
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(block.text)
        elif btype == "image":
            ext = (block.mimeType or "image/png").split("/")[-1]
            path = OUT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}-{i}.{ext}"
            path.write_bytes(base64.b64decode(block.data))
            parts.append(f"[image saved to {path}]")
        elif btype == "resource_link":
            parts.append(f"[resource {block.uri}]")
        else:
            parts.append(json.dumps(block.model_dump(mode="json", exclude_none=True), indent=2))
    text = "\n".join(p for p in parts if p)
    if getattr(result, "isError", False):
        text = "[tool returned isError=true]\n" + text
    return text or "(no content)"


def resolve_tool(name: str) -> str:
    tool = ALIASES.get(name, name)
    if tool not in READ_TOOLS:
        sys.exit(f"{name!r} is not a read tool here. Readable: {', '.join(sorted(READ_TOOLS))}")
    return tool


async def cmd_status() -> None:
    async with open_session() as session:
        tools = await list_tools(session)
    names = sorted(t.name for t in tools)
    readable = [n for n in names if n in READ_TOOLS]
    blocked = [n for n in names if n not in READ_TOOLS]
    print(f"desktop server up at {ENDPOINT}")
    print(f"readable: {', '.join(readable) or '(none)'}")
    if blocked:
        print(f"not exposed by this skill: {', '.join(blocked)}")


async def cmd_tools() -> None:
    async with open_session() as session:
        tools = await list_tools(session)
    lines = []
    for t in tools:
        if t.name in READ_TOOLS:
            summary = (t.description or "").strip().splitlines()
            lines.append(f"{t.name}\t{summary[0] if summary else ''}")
    emit("tools", "\n".join(lines) or "(no readable tools)")


async def cmd_describe(name: str) -> None:
    tool = resolve_tool(name)
    async with open_session() as session:
        tools = await list_tools(session)
    match = next((t for t in tools if t.name == tool), None)
    if match is None:
        sys.exit(f"The desktop server does not serve {tool!r}.")
    emit(f"describe-{tool}", {"name": match.name, "description": match.description,
                              "inputSchema": match.inputSchema})


async def cmd_get(name: str, url: str | None, args_json: str) -> None:
    tool = resolve_tool(name)
    try:
        arguments = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        sys.exit(f"--args must be valid JSON: {e}")
    if not isinstance(arguments, dict):
        sys.exit("--args must be a JSON object")
    async with open_session() as session:
        tools = await list_tools(session)
        match = next((t for t in tools if t.name == tool), None)
        if match is None:
            sys.exit(f"The desktop server does not serve {tool!r}.")
        if url:
            props = (match.inputSchema or {}).get("properties", {})
            for key, value in parse_url(url).items():
                if key in props:
                    arguments.setdefault(key, value)
        result = await asyncio.wait_for(session.call_tool(tool, arguments), timeout=TIMEOUT)
    emit(f"get-{tool}", render(result, tool))


def _connect_refused(e: BaseException) -> bool:
    # The SDK's task group wraps httpx.ConnectError in an ExceptionGroup.
    import httpx

    if isinstance(e, httpx.ConnectError):
        return True
    return isinstance(e, BaseExceptionGroup) and any(_connect_refused(x) for x in e.exceptions)


def _leaves(e: BaseException) -> list[BaseException]:
    if isinstance(e, BaseExceptionGroup):
        return [leaf for x in e.exceptions for leaf in _leaves(x)]
    return [e]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="figma", description="Read-only Figma desktop MCP client.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Check the desktop server and list what it serves")
    sub.add_parser("tools", help="List the readable tools")
    sp = sub.add_parser("describe", help="Show one tool's input schema")
    sp.add_argument("tool")
    sp = sub.add_parser("get", help="Run a read tool")
    sp.add_argument("tool", help="Tool name or alias")
    sp.add_argument("url", nargs="?", help="Figma URL; fills nodeId/fileKey when the tool takes them")
    sp.add_argument("--args", default="{}", help="JSON object of extra tool arguments")
    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.cmd == "status":
            asyncio.run(cmd_status())
        elif args.cmd == "tools":
            asyncio.run(cmd_tools())
        elif args.cmd == "describe":
            asyncio.run(cmd_describe(args.tool))
        elif args.cmd == "get":
            asyncio.run(cmd_get(args.tool, args.url, args.args))
    except asyncio.TimeoutError:
        sys.exit(f"Figma MCP timed out after {TIMEOUT:.0f}s")
    except Exception as e:
        if _connect_refused(e):
            sys.exit(
                f"Cannot reach the Figma desktop MCP server at {ENDPOINT}. Open the Figma app, "
                "open a Design file, press Cmd+/ and run 'Enable desktop MCP server'."
            )
        sys.exit("MCP error: " + "; ".join(f"{type(x).__name__}: {x}" for x in _leaves(e)))


if __name__ == "__main__":
    main()
