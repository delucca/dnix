#!/usr/bin/env python3
"""Send one FigCraft control request and print its JSON result."""

import argparse
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from craft_control import ControlError, request


REQUEST_LIMIT = 32 * 1024 * 1024


def port_number(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be from 1 to 65535")
    return number


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("window and depth must be nonnegative")
    return number


def positive_timeout(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return number


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=port_number, default=7980, help="FigCraft control port (default: 7980)")
    p.add_argument("--timeout", type=positive_timeout, default=70.0, help="request deadline in seconds")
    p.add_argument("--window", type=nonnegative, help="window ID from status; default: last frontmost")
    commands = p.add_subparsers(dest="action", required=True)
    commands.add_parser("status", help="list windows and active tabs")
    inspect = commands.add_parser("inspect", help="inspect the active document")
    inspect.add_argument("--depth", type=nonnegative, default=1)
    inspect.add_argument("--all-pages", action="store_true")
    listing = commands.add_parser("commands", help="discover live command IDs and schemas")
    listing.add_argument("query", nargs="?", help="filter by ID or label; exact ID shows full schema")
    run = commands.add_parser("run", help="execute a FigCraft engine command")
    run.add_argument("command")
    call = commands.add_parser("call", help="call any native control method")
    call.add_argument("method")
    render = commands.add_parser("render", help="render document layers to PNG")
    render.add_argument("path")
    save = commands.add_parser("save", help="save the native document or export a .fig copy")
    save.add_argument("path")
    export = commands.add_parser("export", help="export the selection or current page")
    export.add_argument("path")
    for command in (run, call, render, export):
        command.add_argument("--args", default="{}", metavar="JSON|-", help="JSON object or - for stdin")
    return p


def object_args(value):
    if value == "-":
        value = sys.stdin.read()
    try:
        obj = json.loads(value, parse_constant=lambda word: (_ for _ in ()).throw(ValueError(f"{word} is not finite")))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"invalid --args JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("--args must be a JSON object")

    def check(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("--args numbers must be finite")
        if isinstance(item, dict):
            for child in item.values():
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)

    check(obj)
    return obj


def absolute_path(value):
    return os.path.abspath(os.path.expanduser(value))


def path_args(value, args):
    path = absolute_path(value)
    if "path" in args and args["path"] != path:
        raise ValueError("--args path conflicts with the positional path")
    return {**args, "path": path}


def operation(options):
    action = options.action
    if action == "status":
        return "window.list", {}
    if action == "inspect":
        return "document.inspect", {"depth": options.depth, "allPages": options.all_pages}
    if action == "commands":
        return "engine.commands", {}
    if action == "run":
        return "engine.execute", {"command": options.command, "params": object_args(options.args)}
    if action == "call":
        return options.method, object_args(options.args)
    if action == "render":
        return "ui.render", path_args(options.path, object_args(options.args))
    if action == "save":
        return "engine.execute", {"command": "file.save", "params": {"path": absolute_path(options.path)}}
    if action == "export":
        return "engine.execute", {"command": "file.export", "params": path_args(options.path, object_args(options.args))}
    raise ValueError(f"unknown action {action}")


def main(argv=None):
    options = parser().parse_args(argv)
    try:
        method, params = operation(options)
        if options.window is not None:
            if "window" in params and (type(params["window"]) is not int or params["window"] != options.window):
                raise ValueError("--args window conflicts with --window")
            params["window"] = options.window
        result = request(options.port, method, params, request_limit=REQUEST_LIMIT, timeout=options.timeout)
        if options.action == "commands" and options.query:
            if not isinstance(result, list):
                raise ControlError("engine.commands returned an unexpected result")
            query = options.query.casefold()
            exact = next((item for item in result if isinstance(item, dict) and str(item.get("id", "")).casefold() == query), None)
            result = exact if exact is not None else [
                item for item in result
                if isinstance(item, dict) and query in " ".join(str(item.get(key, "")) for key in ("id", "label", "params")).casefold()
            ]
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ControlError, ValueError, OSError) as exc:
        print(f"figcraft: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
