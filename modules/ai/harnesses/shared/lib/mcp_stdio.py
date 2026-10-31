"""Shared JSON-RPC 2.0 stdio MCP client for ~/.config/ai skill scripts.

Five skills (use-chrome, use-pdf-reader and three others) each embedded a ~100-150-line ``MCPClient`` that spawns an MCP
server as a subprocess and speaks newline-delimited JSON-RPC over its stdio.
The copies drifted -- notably the stdout read loop: the fixed reader-thread
variant shipped in nia/bright-data/google_workspace, while use-pdf-reader still
did the deadlock-prone ``select`` + ``read(1)`` on a BufferedReader and
use-chrome had its own ``select`` + ``os.read`` variant. This is the single
copy, using the reader-thread design as canonical.

A background thread drains stdout line by line into a queue (each line is one
JSON-RPC frame), decoupling arrival from consumption -- selecting on the fd then
``read(1)`` on the BufferedReader deadlocks, because the first read buffers the
rest of the line inside Python where ``select`` can no longer see it. A second
thread drains stderr into a bounded tail so a chatty server can't block on a
full pipe, and so the tail can be surfaced when the child crashes (nia's
stderr-on-crash reporting, kept canonical). ``stderr_to_terminal=True`` instead
lets stderr stream straight to the user's terminal -- used by google_workspace's
one-time ``auth`` bootstrap to show the server's progress. Pass
``stderr_line_filter`` to stream it line by line through a rewrite first, which
is how that bootstrap keeps the log while suppressing the raw OAuth URL.

Each script binds ``cmd``/``env``/``client_name`` and its own timeouts, then
drives ``initialize`` -> ``call_tool`` -> ``close``; the per-skill CLIs and
output helpers stay in the scripts.

Renders to ``~/.config/ai/common/lib/mcp_stdio.py``; imported through a ``sys.path`` shim
each script computes from its own location. Pure stdlib so it imports under both
the uv PEP-723 scripts and use-chrome's plain ``python3``.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable

DEFAULT_CALL_TIMEOUT = 120
PROTOCOL_VERSION = "2024-11-05"
_STDERR_TAIL_CHUNKS = 64
_STDERR_CHUNK = 4096


class MCPClient:
    """Minimal JSON-RPC 2.0 stdio client. One instance per skill invocation.

    ``process_label`` names the server in the "exited unexpectedly" message.
    ``call_timeout`` is the default per-call timeout. ``stderr_to_terminal``
    forwards the child's stderr to this process's stderr instead of capturing it.
    ``stderr_line_filter`` takes each stderr line and returns what to show (or
    None/"" to drop it); giving one implies forwarding, through the filter.
    Call :meth:`close` when done.
    """

    def __init__(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        *,
        client_name: str = "mcp-client",
        process_label: str = "MCP process",
        call_timeout: int = DEFAULT_CALL_TIMEOUT,
        stderr_to_terminal: bool = False,
        stderr_line_filter: Callable[[str], str | None] | None = None,
    ):
        self._id = 0
        self._client_name = client_name
        self._process_label = process_label
        self._call_timeout = call_timeout
        self._stderr_filter = stderr_line_filter
        # A filter can only rewrite what we read ourselves, so it forces a pipe.
        self._stderr_piped = stderr_line_filter is not None or not stderr_to_terminal
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE if self._stderr_piped else None,
                text=False,
                env=merged_env,
            )
        except FileNotFoundError:
            sys.exit(f"Failed to spawn MCP process: {cmd[0]!r} not found.")
        self._messages: queue.Queue = queue.Queue()
        self._stderr_tail: list[bytes] = []
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        if self._stderr_piped:
            self._errthread = threading.Thread(target=self._read_stderr, daemon=True)
            self._errthread.start()

    def _read_stdout(self) -> None:
        assert self._proc.stdout is not None
        try:
            for line in self._proc.stdout:  # iterates on b"\n" boundaries
                line = line.strip()
                if not line:
                    continue
                try:
                    self._messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue  # ignore non-JSON noise on stdout
        except Exception:
            pass

    def _read_stderr(self) -> None:
        assert self._proc.stderr is not None
        budget = _STDERR_TAIL_CHUNKS * _STDERR_CHUNK
        held = 0
        # Line at a time, not fixed chunks: a filter needs whole lines, and a
        # chunk read holds the log back until 4 KB has accumulated.
        for line in iter(self._proc.stderr.readline, b""):
            if self._stderr_filter is not None:
                shown = self._stderr_filter(line.decode(errors="replace"))
                if shown:
                    sys.stderr.write(shown)
                    sys.stderr.flush()
            self._stderr_tail.append(line)
            held += len(line)
            while held > budget:  # keep a bounded tail
                held -= len(self._stderr_tail.pop(0))

    def _drain_stderr(self) -> str:
        # A filter has already streamed every line; don't print them twice.
        if not self._stderr_piped or self._stderr_filter is not None:
            return ""
        data = b"".join(self._stderr_tail)
        return "stderr: " + data.decode(errors="replace") if data else ""

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, msg: dict) -> None:
        """Send a JSON-RPC message on stdin as a newline-delimited JSON string."""
        line = json.dumps(msg) + "\n"
        assert self._proc.stdin is not None
        self._proc.stdin.write(line.encode())
        self._proc.stdin.flush()

    def _recv(self, timeout: float) -> dict:
        """Pop the next JSON-RPC message the reader thread has queued."""
        try:
            return self._messages.get(timeout=max(timeout, 0.0))
        except queue.Empty:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"{self._process_label} process exited unexpectedly.\n"
                    + self._drain_stderr()
                )
            raise TimeoutError(f"MCP response timed out after {timeout}s")

    def _request(self, method: str, params: dict | None = None,
                 timeout: float | None = None) -> dict:
        """Send a request and return the result dict (raises on error)."""
        if timeout is None:
            timeout = self._call_timeout
        req_id = self._next_id()
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"MCP response timed out after {timeout}s")
            resp = self._recv(remaining)
            if "id" not in resp:          # skip notifications
                continue
            if resp.get("id") != req_id:  # skip responses to other ids
                continue
            if "error" in resp:
                err = resp["error"]
                raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
            return resp.get("result", {})

    def _notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def initialize(self, startup_timeout: float | None = None) -> None:
        """Perform the MCP handshake."""
        self._request(
            "initialize",
            params={
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self._client_name, "version": "1.0"},
            },
            timeout=startup_timeout,
        )
        self._notify("notifications/initialized")

    def list_tools(self, timeout: float | None = None) -> list[dict]:
        return self._request("tools/list", timeout=timeout).get("tools", [])

    def call_tool(self, name: str, arguments: dict | None = None,
                  timeout: float | None = None) -> dict:
        """Call a tool and return the raw result."""
        # Always an object: servers that require one (chrome-devtools-mcp's
        # take_snapshot) reject a call whose arguments key is absent.
        params: dict = {"name": name, "arguments": arguments or {}}
        return self._request("tools/call", params=params, timeout=timeout)

    def close(self) -> None:
        """Terminate the subprocess cleanly."""
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()
