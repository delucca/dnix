#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx==0.28.1"]
# ///
"""
context7.py -- On-demand CLI for Context7 library documentation via HTTP MCP.

Speaks JSON-RPC 2.0 over streamable-http to https://mcp.context7.com/mcp.
The API key is read at use time through the configured secret reader.

Short results (<=4 KB) print to stdout. Larger results spill to ~/.cache/context7-cm/
with a pointer and the first 1500 chars printed inline.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCP_URL = "https://mcp.context7.com/mcp"
MCP_TIMEOUT = 120          # seconds for tool calls
INLINE_LIMIT = 4096        # bytes; above this we spill to OUT_DIR
OUT_DIR = Path.home() / ".cache" / "context7-cm"
OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)  # per-user 0700; spills may hold sensitive data

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import credential  # noqa: E402

# ---------------------------------------------------------------------------
# API key retrieval
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    return credential.read("use-context7", "apiKey", label="Context7 API key")


# ---------------------------------------------------------------------------
# MCP HTTP client (streamable-http transport)
# ---------------------------------------------------------------------------


class Context7Client:
    """Minimal JSON-RPC 2.0 client for Context7 over streamable-http."""

    def __init__(self, api_key: str):
        self._url = MCP_URL
        self._headers = {
            "CONTEXT7_API_KEY": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._id = 0
        self._session_id: str | None = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def request(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = MCP_TIMEOUT,
    ) -> dict:
        """Send a JSON-RPC 2.0 request and return the result (unwrapped)."""
        import httpx

        req_id = self._next_id()
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params

        headers = dict(self._headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self._url, json=msg, headers=headers)
            resp.raise_for_status()

            # Track session ID from response
            if "mcp-session-id" in resp.headers:
                self._session_id = resp.headers["mcp-session-id"]

            ct = resp.headers.get("content-type", "")
            if "text/event-stream" in ct:
                return self._parse_sse(resp.text, req_id)
            else:
                data = resp.json()
                if "error" in data:
                    err = data["error"]
                    raise RuntimeError(
                        f"MCP error {err.get('code')}: {err.get('message')}"
                    )
                return data.get("result", {})

    def _parse_sse(self, body: str, req_id: int) -> dict:
        """Parse an SSE response and extract the JSON-RPC result for req_id."""
        for line in body.splitlines():
            if not line.startswith("data:"):
                continue
            json_str = line[len("data:"):].strip()
            if not json_str:
                continue
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                continue
            if data.get("id") == req_id:
                if "error" in data:
                    err = data["error"]
                    raise RuntimeError(
                        f"MCP error {err.get('code')}: {err.get('message')}"
                    )
                if "result" in data:
                    return data["result"]
        raise RuntimeError(
            f"No result found in SSE response for request {req_id}.\n"
            f"Response body (first 500 chars): {body[:500]}"
        )

    def initialize(self) -> None:
        """Perform the MCP protocol handshake."""
        self.request(
            "initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "use-context7", "version": "1.0"},
            },
        )
        # Send initialized notification (no id, no response expected)
        import httpx

        notification: dict = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        headers = dict(self._headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        with httpx.Client(timeout=10) as client:
            client.post(self._url, json=notification, headers=headers)

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Call a Context7 MCP tool and return the raw result."""
        params: dict = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return self.request("tools/call", params=params)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


from emit import make_emit  # noqa: E402

emit = make_emit(OUT_DIR)


def extract_text(result: dict) -> str:
    """Extract text content from an MCP tools/call result."""
    content = result.get("content", [])
    if isinstance(content, list):
        parts = [
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
        ]
        if parts:
            return "\n".join(parts)
    # Fallback: stringify the whole result
    return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_resolve(client: Context7Client, args) -> None:
    """Resolve a library name to Context7 IDs."""
    tool_args: dict = {"libraryName": args.library_name}
    if args.query:
        tool_args["query"] = args.query
    else:
        tool_args["query"] = args.library_name
    result = client.call_tool("resolve-library-id", tool_args)
    text = extract_text(result)
    emit("resolve", text)


def cmd_query(client: Context7Client, args) -> None:
    """Query documentation for a known library ID."""
    tool_args: dict = {"libraryId": args.library_id, "query": args.query}
    result = client.call_tool("query-docs", tool_args)
    text = extract_text(result)
    emit("query", text)


def cmd_lookup(client: Context7Client, args) -> None:
    """Convenience: resolve library name, then query its docs."""
    # Step 1: Resolve
    resolve_args: dict = {"libraryName": args.library_name, "query": args.query}
    resolve_result = client.call_tool("resolve-library-id", resolve_args)
    resolve_text = extract_text(resolve_result)

    # Parse the resolve output to find the best library ID.
    # The resolve tool returns a text table. The first library ID is the best match.
    # Library IDs look like: /org/repo (start with /)
    library_id: str | None = None
    for line in resolve_text.splitlines():
        stripped = line.strip()
        # Look for lines that contain a Context7 library ID pattern
        # Common formats: "- /vercel/next.js ..." or "ID: /vercel/next.js" or just "/vercel/next.js"
        for token in stripped.split():
            if token.startswith("/") and "/" in token[1:] and len(token) > 3:
                library_id = token.rstrip(",;:)")
                break
        if library_id:
            break

    if not library_id:
        print("# resolve output (could not auto-extract library ID):")
        emit("resolve", resolve_text)
        sys.exit(
            "\nCould not auto-extract a library ID from the resolve output above.\n"
            "Copy the ID manually and run:\n"
            f'  context7.py query "<library_id>" "{args.query}"'
        )

    print(f"# resolved '{args.library_name}' -> {library_id}", file=sys.stderr)

    # Step 2: Query
    query_args: dict = {"libraryId": library_id, "query": args.query}
    query_result = client.call_tool("query-docs", query_args)
    text = extract_text(query_result)
    emit("query", text)


def cmd_raw(client: Context7Client, args) -> None:
    """Call any Context7 MCP tool with raw JSON arguments."""
    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        sys.exit(f"--args must be valid JSON: {e}")
    result = client.call_tool(args.tool, tool_args if tool_args else None)
    text = extract_text(result)
    emit(f"raw-{args.tool}", text)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(
        prog="context7",
        description="Context7 library documentation CLI -- on-demand HTTP MCP wrapper.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # resolve
    sp = sub.add_parser("resolve", help="Resolve a library name to its Context7 ID")
    sp.add_argument("library_name", help="Library or framework name (e.g. 'Next.js', 'React')")
    sp.add_argument(
        "--query", "-q",
        help="Context for ranking results (e.g. 'server components'). Defaults to library_name.",
    )
    sp.set_defaults(handler="resolve")

    # query
    sp = sub.add_parser("query", help="Query docs for a known library ID")
    sp.add_argument("library_id", help="Context7 library ID (e.g. '/vercel/next.js')")
    sp.add_argument("query", help="Question or task")
    sp.set_defaults(handler="query")

    # lookup
    sp = sub.add_parser("lookup", help="Resolve + query in one step (convenience)")
    sp.add_argument("library_name", help="Library or framework name (e.g. 'Prisma')")
    sp.add_argument("query", help="Question or task")
    sp.set_defaults(handler="lookup")

    # raw
    sp = sub.add_parser("raw", help="Call any Context7 MCP tool with raw JSON args")
    sp.add_argument("tool", help="Tool name (e.g. resolve-library-id, query-docs)")
    sp.add_argument("--args", default="{}", help="JSON-encoded arguments object")
    sp.set_defaults(handler="raw")

    args = p.parse_args()

    # -- Bootstrap: get API key and initialize MCP session --
    api_key = _get_api_key()
    client = Context7Client(api_key)
    try:
        client.initialize()
    except Exception as e:
        sys.exit(f"Failed to initialize Context7 MCP session: {e}")

    # -- Dispatch --
    handlers = {
        "resolve": cmd_resolve,
        "query": cmd_query,
        "lookup": cmd_lookup,
        "raw": cmd_raw,
    }
    handler = handlers[args.handler]
    try:
        handler(client, args)
    except RuntimeError as e:
        sys.exit(f"Context7 error: {e}")
    except Exception as e:
        sys.exit(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
