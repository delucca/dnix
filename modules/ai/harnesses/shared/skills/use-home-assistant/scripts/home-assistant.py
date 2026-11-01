#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx==0.28.1"]
# ///
"""
home-assistant.py -- On-demand CLI for Home Assistant via SSE MCP transport.

Connects to the HA MCP SSE endpoint, discovers the POST URL, sends JSON-RPC 2.0
tool calls, and receives responses over the SSE stream. The instance URL comes
from the skill's settings; the auth token is read at use time through the
configured secret reader.

Short results (<=4 KB) print to stdout. Larger results spill to ~/.cache/ha-cm/
with a pointer and the first 1500 chars printed inline.
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONNECT_TIMEOUT = 15       # seconds to wait for SSE endpoint event
TOOL_TIMEOUT = 15          # seconds per tool call
INLINE_LIMIT = 4096        # bytes; above this we spill to OUT_DIR
OUT_DIR = Path.home() / ".cache" / "ha-cm"
OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)  # per-user 0700; spills may hold sensitive data

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import credential  # noqa: E402

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _get_url() -> str:
    url = credential.settings("use-home-assistant").get("url")
    if not url:
        sys.exit("Home Assistant URL unset: set dnix.ai.skills.use-home-assistant.settings.url.")
    return url.rstrip("/") + "/"


def _get_token() -> str:
    return credential.read("use-home-assistant", "token", label="Home Assistant token")


# ---------------------------------------------------------------------------
# MCP SSE client
# ---------------------------------------------------------------------------


class HomeAssistantClient:
    """JSON-RPC 2.0 client over MCP SSE transport.

    1. Connect to the SSE endpoint (GET) in a background thread.
    2. Receive an `endpoint` event containing the URL to POST messages to.
    3. Send JSON-RPC requests by POSTing to that URL.
    4. Receive responses as SSE `message` events on the original connection.
    """

    def __init__(self, url: str, token: str):
        self._sse_url = urljoin(url, "mcp_server/sse")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._id = 0
        self._message_url: str | None = None
        self._responses: queue.Queue[dict] = queue.Queue()
        self._connected = threading.Event()
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def connect(self) -> None:
        """Connect to the SSE endpoint and discover the POST message URL."""
        self._thread = threading.Thread(target=self._sse_listener, daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout=CONNECT_TIMEOUT):
            if self._error:
                raise RuntimeError(f"SSE connection failed: {self._error}")
            raise RuntimeError(
                f"Failed to connect to Home Assistant SSE endpoint within {CONNECT_TIMEOUT}s.\n"
                f"URL: {self._sse_url}"
            )

    def _sse_listener(self) -> None:
        """Background thread: consume SSE events from the HA MCP server."""
        import httpx

        try:
            with httpx.Client(timeout=None) as client:
                with client.stream("GET", self._sse_url, headers=self._headers) as resp:
                    resp.raise_for_status()
                    event_type: str | None = None
                    data_buf: list[str] = []
                    for line in resp.iter_lines():
                        if line.startswith("event: "):
                            event_type = line[7:].strip()
                        elif line.startswith("data: "):
                            data_buf.append(line[6:])
                        elif line == "":
                            if event_type and data_buf:
                                data = "\n".join(data_buf)
                                if event_type == "endpoint":
                                    self._message_url = urljoin(self._sse_url, data)
                                    self._connected.set()
                                elif event_type == "message":
                                    try:
                                        self._responses.put(json.loads(data))
                                    except json.JSONDecodeError:
                                        pass
                            event_type = None
                            data_buf = []
        except Exception as exc:
            self._error = str(exc)
            self._connected.set()  # unblock the main thread so it can read the error

    def request(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = TOOL_TIMEOUT,
    ) -> dict:
        """Send a JSON-RPC 2.0 request and wait for the response."""
        import httpx

        if not self._message_url:
            raise RuntimeError("Not connected -- call connect() first")

        req_id = self._next_id()
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params

        with httpx.Client(timeout=10) as client:
            resp = client.post(self._message_url, json=msg, headers=self._headers)
            resp.raise_for_status()

        # Wait for the matching response on the SSE channel
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Response timed out after {timeout}s")
            try:
                data = self._responses.get(timeout=min(remaining, 1.0))
                if data.get("id") == req_id:
                    if "error" in data:
                        err = data["error"]
                        raise RuntimeError(
                            f"MCP error {err.get('code')}: {err.get('message')}"
                        )
                    return data.get("result", {})
                # Not our response -- discard (sequential requests only)
            except queue.Empty:
                continue

    def initialize(self) -> None:
        """Perform the MCP protocol handshake."""
        import httpx

        self.request(
            "initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "use-home-assistant", "version": "1.0"},
            },
        )
        # Send initialized notification (no id, no response expected)
        if self._message_url:
            notification: dict = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            with httpx.Client(timeout=10) as client:
                client.post(self._message_url, json=notification, headers=self._headers)

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Call a Home Assistant MCP tool and return the raw result."""
        params: dict = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return self.request("tools/call", params=params)

    def close(self) -> None:
        """Clean up. The daemon thread exits when the process does."""
        pass


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
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        if parts:
            return "\n".join(parts)
    return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Argument builder helpers
# ---------------------------------------------------------------------------


def _device_args(args, extra: dict | None = None) -> dict:
    """Build common device targeting arguments (name, area, floor)."""
    result: dict = {}
    if hasattr(args, "name") and args.name:
        result["name"] = args.name
    if hasattr(args, "area") and args.area:
        result["area"] = args.area
    if hasattr(args, "floor") and args.floor:
        result["floor"] = args.floor
    if extra:
        result.update(extra)
    return result


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_on(client: HomeAssistantClient, args) -> None:
    """Turn on / open / press a device."""
    tool_args = _device_args(args)
    result = client.call_tool("HassTurnOn", tool_args)
    emit("on", extract_text(result))


def cmd_off(client: HomeAssistantClient, args) -> None:
    """Turn off / close a device."""
    tool_args = _device_args(args)
    result = client.call_tool("HassTurnOff", tool_args)
    emit("off", extract_text(result))


def cmd_light(client: HomeAssistantClient, args) -> None:
    """Set light brightness, color, or temperature."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    if args.brightness is not None:
        tool_args["brightness"] = args.brightness
    if args.color:
        tool_args["color"] = args.color
    if args.temperature is not None:
        tool_args["temperature"] = args.temperature
    result = client.call_tool("HassLightSet", tool_args)
    emit("light", extract_text(result))


def cmd_climate(client: HomeAssistantClient, args) -> None:
    """Set thermostat temperature."""
    tool_args: dict = {"temperature": args.temperature}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassClimateSetTemperature", tool_args)
    emit("climate", extract_text(result))


def cmd_play(client: HomeAssistantClient, args) -> None:
    """Search and play media."""
    tool_args: dict = {"search_query": args.query}
    if args.device:
        tool_args["name"] = args.device
    if args.area:
        tool_args["area"] = args.area
    if args.type:
        tool_args["media_class"] = args.type
    result = client.call_tool("HassMediaSearchAndPlay", tool_args)
    emit("play", extract_text(result))


def cmd_pause(client: HomeAssistantClient, args) -> None:
    """Pause media playback."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassMediaPause", tool_args)
    emit("pause", extract_text(result))


def cmd_resume(client: HomeAssistantClient, args) -> None:
    """Resume media playback."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassMediaUnpause", tool_args)
    emit("resume", extract_text(result))


def cmd_next(client: HomeAssistantClient, args) -> None:
    """Skip to next track."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassMediaNext", tool_args)
    emit("next", extract_text(result))


def cmd_prev(client: HomeAssistantClient, args) -> None:
    """Skip to previous track."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassMediaPrevious", tool_args)
    emit("prev", extract_text(result))


def cmd_volume(client: HomeAssistantClient, args) -> None:
    """Set volume level (0-100)."""
    tool_args: dict = {"volume_level": args.level}
    if args.device:
        tool_args["name"] = args.device
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassSetVolume", tool_args)
    emit("volume", extract_text(result))


def cmd_volume_up(client: HomeAssistantClient, args) -> None:
    """Increase volume."""
    tool_args: dict = {"volume_step": "up"}
    if args.name:
        tool_args["name"] = args.name
    result = client.call_tool("HassSetVolumeRelative", tool_args)
    emit("volume-up", extract_text(result))


def cmd_volume_down(client: HomeAssistantClient, args) -> None:
    """Decrease volume."""
    tool_args: dict = {"volume_step": "down"}
    if args.name:
        tool_args["name"] = args.name
    result = client.call_tool("HassSetVolumeRelative", tool_args)
    emit("volume-down", extract_text(result))


def cmd_mute(client: HomeAssistantClient, args) -> None:
    """Mute a media player."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassMediaPlayerMute", tool_args)
    emit("mute", extract_text(result))


def cmd_unmute(client: HomeAssistantClient, args) -> None:
    """Unmute a media player."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    result = client.call_tool("HassMediaPlayerUnmute", tool_args)
    emit("unmute", extract_text(result))


def cmd_vacuum(client: HomeAssistantClient, args) -> None:
    """Control a vacuum: start, clean area, or return to base."""
    action = args.action
    if action == "start":
        tool_args: dict = {}
        if args.name:
            tool_args["name"] = args.name
        if args.area:
            tool_args["area"] = args.area
        result = client.call_tool("HassVacuumStart", tool_args)
    elif action == "clean":
        tool_args = {}
        if args.name:
            tool_args["name"] = args.name
        if not args.area:
            sys.exit("vacuum clean requires --area (e.g. --area kitchen)")
        tool_args["area"] = args.area
        result = client.call_tool("HassVacuumCleanArea", tool_args)
    elif action == "return":
        tool_args = {}
        if args.name:
            tool_args["name"] = args.name
        result = client.call_tool("HassVacuumReturnToBase", tool_args)
    else:
        sys.exit(f"Unknown vacuum action: {action}. Use: start, clean, return")
    emit("vacuum", extract_text(result))


def cmd_broadcast(client: HomeAssistantClient, args) -> None:
    """Broadcast a message through the home."""
    result = client.call_tool("HassBroadcast", {"message": args.message})
    emit("broadcast", extract_text(result))


def cmd_list_add(client: HomeAssistantClient, args) -> None:
    """Add an item to a todo list."""
    result = client.call_tool("HassListAddItem", {
        "name": args.list_name,
        "item": args.item,
    })
    emit("list-add", extract_text(result))


def cmd_list_done(client: HomeAssistantClient, args) -> None:
    """Complete an item on a todo list."""
    result = client.call_tool("HassListCompleteItem", {
        "name": args.list_name,
        "item": args.item,
    })
    emit("list-done", extract_text(result))


def cmd_list_remove(client: HomeAssistantClient, args) -> None:
    """Remove an item from a todo list."""
    result = client.call_tool("HassListRemoveItem", {
        "name": args.list_name,
        "item": args.item,
    })
    emit("list-remove", extract_text(result))


def cmd_list_get(client: HomeAssistantClient, args) -> None:
    """Get items from a todo list."""
    tool_args: dict = {"todo_list": args.list_name}
    if args.status:
        tool_args["status"] = args.status
    result = client.call_tool("todo_get_items", tool_args)
    emit("list-get", extract_text(result))


def cmd_status(client: HomeAssistantClient, args) -> None:
    """Get live context (device/sensor status)."""
    tool_args: dict = {}
    if args.name:
        tool_args["name"] = args.name
    if args.area:
        tool_args["area"] = args.area
    if args.domain:
        tool_args["domain"] = args.domain
    result = client.call_tool("GetLiveContext", tool_args)
    emit("status", extract_text(result))


def cmd_raw(client: HomeAssistantClient, args) -> None:
    """Call any HA MCP tool with raw JSON arguments."""
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


def _add_area_floor(sp: argparse.ArgumentParser) -> None:
    """Add --area and --floor options to a subparser."""
    sp.add_argument("--area", help="Target area (e.g. 'kitchen', 'bedroom')")
    sp.add_argument("--floor", help="Target floor (e.g. 'upstairs', 'ground floor')")


def _add_name_area(sp: argparse.ArgumentParser) -> None:
    """Add optional name positional and --area option to a subparser."""
    sp.add_argument("name", nargs="?", default=None, help="Device or player name")
    sp.add_argument("--area", help="Target area")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="home-assistant",
        description="Home Assistant smart home CLI -- on-demand SSE MCP wrapper.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # -- Device control --

    sp = sub.add_parser("on", help="Turn on / open / press a device")
    sp.add_argument("name", help="Device name")
    _add_area_floor(sp)
    sp.set_defaults(handler=cmd_on)

    sp = sub.add_parser("off", help="Turn off / close a device")
    sp.add_argument("name", help="Device name")
    _add_area_floor(sp)
    sp.set_defaults(handler=cmd_off)

    # -- Lights --

    sp = sub.add_parser("light", help="Set light brightness/color/temperature")
    sp.add_argument("name", nargs="?", default=None, help="Light name")
    sp.add_argument("--area", help="Target area")
    sp.add_argument("--brightness", type=int, help="Brightness 0-100")
    sp.add_argument("--color", help="Color name (e.g. 'red', 'blue')")
    sp.add_argument("--temperature", type=int, help="Color temperature in Kelvin")
    sp.set_defaults(handler=cmd_light)

    # -- Climate --

    sp = sub.add_parser("climate", help="Set thermostat temperature")
    sp.add_argument("name", nargs="?", default=None, help="Thermostat name")
    sp.add_argument("temperature", type=float, help="Target temperature")
    sp.add_argument("--area", help="Target area")
    sp.set_defaults(handler=cmd_climate)

    # -- Media --

    sp = sub.add_parser("play", help="Search and play media")
    sp.add_argument("query", help="Search query (song, artist, album, etc.)")
    sp.add_argument("--device", help="Speaker or player name")
    sp.add_argument("--area", help="Target area")
    sp.add_argument(
        "--type",
        choices=[
            "track", "album", "artist", "playlist", "genre",
            "movie", "tvshow", "channel", "episode",
        ],
        help="Media class",
    )
    sp.set_defaults(handler=cmd_play)

    sp = sub.add_parser("pause", help="Pause media playback")
    _add_name_area(sp)
    sp.set_defaults(handler=cmd_pause)

    sp = sub.add_parser("resume", help="Resume media playback")
    _add_name_area(sp)
    sp.set_defaults(handler=cmd_resume)

    sp = sub.add_parser("next", help="Skip to next track")
    _add_name_area(sp)
    sp.set_defaults(handler=cmd_next)

    sp = sub.add_parser("prev", help="Skip to previous track")
    _add_name_area(sp)
    sp.set_defaults(handler=cmd_prev)

    sp = sub.add_parser("volume", help="Set volume level (0-100)")
    sp.add_argument("level", type=int, help="Volume level 0-100")
    sp.add_argument("--device", help="Speaker or player name")
    sp.add_argument("--area", help="Target area")
    sp.set_defaults(handler=cmd_volume)

    sp = sub.add_parser("volume-up", help="Increase volume")
    sp.add_argument("name", nargs="?", default=None, help="Player name")
    sp.set_defaults(handler=cmd_volume_up)

    sp = sub.add_parser("volume-down", help="Decrease volume")
    sp.add_argument("name", nargs="?", default=None, help="Player name")
    sp.set_defaults(handler=cmd_volume_down)

    sp = sub.add_parser("mute", help="Mute a media player")
    _add_name_area(sp)
    sp.set_defaults(handler=cmd_mute)

    sp = sub.add_parser("unmute", help="Unmute a media player")
    _add_name_area(sp)
    sp.set_defaults(handler=cmd_unmute)

    # -- Vacuum --

    sp = sub.add_parser("vacuum", help="Control a vacuum (start/clean/return)")
    sp.add_argument("action", choices=["start", "clean", "return"], help="Vacuum action")
    sp.add_argument("name", nargs="?", default=None, help="Vacuum name")
    sp.add_argument("--area", help="Area to clean (required for 'clean')")
    sp.set_defaults(handler=cmd_vacuum)

    # -- Broadcast --

    sp = sub.add_parser("broadcast", help="Announce a message through the home")
    sp.add_argument("message", help="Message to broadcast")
    sp.set_defaults(handler=cmd_broadcast)

    # -- Lists / Todos --

    sp = sub.add_parser("list-add", help="Add an item to a todo list")
    sp.add_argument("list_name", help="Todo list name (e.g. 'Shopping List')")
    sp.add_argument("item", help="Item to add")
    sp.set_defaults(handler=cmd_list_add)

    sp = sub.add_parser("list-done", help="Complete an item on a todo list")
    sp.add_argument("list_name", help="Todo list name")
    sp.add_argument("item", help="Item to complete")
    sp.set_defaults(handler=cmd_list_done)

    sp = sub.add_parser("list-remove", help="Remove an item from a todo list")
    sp.add_argument("list_name", help="Todo list name")
    sp.add_argument("item", help="Item to remove")
    sp.set_defaults(handler=cmd_list_remove)

    sp = sub.add_parser("list-get", help="Get items from a todo list")
    sp.add_argument("list_name", help="Todo list name")
    sp.add_argument(
        "--status",
        choices=["needs_action", "completed", "all"],
        default="needs_action",
        help="Filter by status (default: needs_action)",
    )
    sp.set_defaults(handler=cmd_list_get)

    # -- Status --

    sp = sub.add_parser("status", help="Get live device/sensor status")
    sp.add_argument("--name", help="Specific device name")
    sp.add_argument("--area", help="Filter by area")
    sp.add_argument("--domain", help="Filter by domain (e.g. light, sensor, climate)")
    sp.set_defaults(handler=cmd_status)

    # -- Raw --

    sp = sub.add_parser("raw", help="Call any HA MCP tool with raw JSON args")
    sp.add_argument("tool", help="Tool name (e.g. HassTurnOn, GetLiveContext)")
    sp.add_argument("--args", default="{}", help="JSON-encoded arguments object")
    sp.set_defaults(handler=cmd_raw)

    args = p.parse_args()

    # -- Bootstrap: get token and connect --
    client = HomeAssistantClient(_get_url(), _get_token())
    try:
        client.connect()
        client.initialize()
    except Exception as e:
        sys.exit(f"Failed to connect to Home Assistant: {e}")

    # -- Dispatch --
    try:
        args.handler(client, args)
    except RuntimeError as e:
        sys.exit(f"Home Assistant error: {e}")
    except TimeoutError as e:
        sys.exit(f"Timeout: {e}")
    except Exception as e:
        sys.exit(f"Unexpected error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
