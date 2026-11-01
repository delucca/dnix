#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==1.27.2", "httpx==0.28.1"]
# ///
"""One-shot client for the running Glyphs MCP sidecar."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import math
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from emit import emit_to, secure_cache_dir  # noqa: E402


DEFAULT_URL = "http://127.0.0.1:9680/mcp/"
OUT_DIR = None


def json_object(value: str) -> dict:
    if value == "-":
        value = sys.stdin.read()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--args must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--args must be a JSON object")
    try:
        json.dumps(parsed, allow_nan=False)
    except ValueError as exc:
        raise ValueError(f"--args must contain finite JSON numbers: {exc}") from exc
    return parsed


def local_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port is None
        or parsed.path != "/mcp/"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("--url must be a loopback HTTP URL ending in /mcp/")
    return value


def positive_timeout(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--timeout must be a positive number") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("--timeout must be a positive finite number")
    return seconds


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Call the running Glyphs 4 MCP sidecar")
    command.add_argument("--url", type=local_url, default=DEFAULT_URL)
    command.add_argument("--timeout", type=positive_timeout, default=120.0)
    sub = command.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Read component status and capabilities")
    sub.add_parser("documents", help="List open font documents")
    tools = sub.add_parser("tools", help="List advertised tools")
    tools.add_argument("query", nargs="?", help="Filter by tool name or description")
    describe = sub.add_parser("describe", help="Read one tool's complete live schema")
    describe.add_argument("tool")
    call = sub.add_parser("call", help="Call an advertised tool with its JSON arguments")
    call.add_argument("tool")
    call.add_argument("--args", default="{}", metavar="JSON|-", help="JSON object or - for stdin")
    return command


@asynccontextmanager
async def open_session(url: str, timeout: float):
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout) as client:
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def as_json(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=False)
    return value


def inner_error(payload: dict) -> bool:
    if payload.get("isError") is True:
        return True
    structured = payload.get("structuredContent")
    if isinstance(structured, dict) and structured.get("ok") is False:
        return True
    for block in payload.get("content", []):
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        try:
            text_payload = json.loads(block.get("text", ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(text_payload, dict) and text_payload.get("ok") is False:
            return True
    return False


async def list_all_tools(session) -> list:
    found = []
    cursor = None
    seen = set()
    while True:
        page = await session.list_tools(cursor=cursor)
        found.extend(page.tools)
        cursor = getattr(page, "nextCursor", None)
        if not cursor:
            return found
        if cursor in seen:
            raise RuntimeError("Tool pagination repeated a cursor")
        seen.add(cursor)


async def perform(args, state: dict) -> tuple[str, object, bool]:
    if args.command == "call":
        params = json_object(args.args)
    else:
        params = {}

    async with asyncio.timeout(args.timeout):
        async with open_session(args.url, args.timeout) as session:
            if args.command in {"status", "documents", "call"}:
                tool = {"status": "get_status", "documents": "list_documents"}.get(args.command, getattr(args, "tool", None))
                state["call_started"] = True
                result = await session.call_tool(tool, params)
                payload = as_json(result)
                return tool, payload, inner_error(payload)

            catalog = await list_all_tools(session)
            if args.command == "tools":
                query = (args.query or "").casefold()
                compact = [
                    {"name": item.name, "description": item.description}
                    for item in catalog
                    if query in item.name.casefold() or query in (item.description or "").casefold()
                ]
                return "tools", compact, False

            match = next((item for item in catalog if item.name == args.tool), None)
            if match is None:
                raise ValueError(f"Tool {args.tool!r} is not advertised by Glyphs MCP")
            return f"describe-{args.tool}", as_json(match), False


def error_details(exc: BaseException) -> str:
    def leaves(current):
        if isinstance(current, BaseExceptionGroup):
            for child in current.exceptions:
                yield from leaves(child)
        else:
            yield current

    parts = [f"{type(item).__name__}: {str(item)[:240]}" for item in leaves(exc)]
    return "; ".join(parts[:3]) + ("; …" if len(parts) > 3 else "")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    state = {"call_started": False}
    try:
        label, result, failed = asyncio.run(perform(args, state))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    except TimeoutError:
        message = "Glyphs MCP timed out"
        if args.command == "call" and state["call_started"]:
            message += "; the tool may have run. Inspect its document or workflow before retrying"
        print(message + ".", file=sys.stderr)
        return 1
    except Exception as exc:
        message = f"Glyphs MCP failed: {error_details(exc)}"
        if args.command == "call" and state["call_started"]:
            message += ". The tool may have run; inspect before retrying"
        print(message + ".", file=sys.stderr)
        return 1
    emit_to(OUT_DIR or secure_cache_dir("glyphs"), label, result)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
