#!/usr/bin/env python3
"""CLI for the running VectorCraft desktop app's native control port."""

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from craft_control import ControlError, request


LIMIT = 4 * 1024 * 1024


def positive_timeout(value):
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number")
    return number


def json_object(raw):
    if raw == "-":
        raw = sys.stdin.read()
    try:
        value = json.loads(raw, parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(f"{constant} is not finite")))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ControlError(f"--args must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ControlError("--args must be a JSON object")
    return value


def path_params(path, args):
    absolute = str(Path(path).expanduser().resolve())
    if "path" in args:
        if not isinstance(args["path"], str) or str(Path(args["path"]).expanduser().resolve()) != absolute:
            raise ControlError("--args path conflicts with the positional path")
    return {**args, "path": absolute}


def parser():
    cli = argparse.ArgumentParser(description="Control a running VectorCraft desktop app")
    cli.add_argument("--port", type=int, default=7979, help="native control port (default: 7979)")
    cli.add_argument("--timeout", type=positive_timeout, default=70.0, help="total request deadline in seconds")
    commands = cli.add_subparsers(dest="action", required=True)
    commands.add_parser("status", help="inspect UI and connection")
    inspect = commands.add_parser("inspect", help="inspect document")
    inspect.add_argument("--args", default='{"depth":1,"childLimit":20}')
    catalog = commands.add_parser("commands", help="list or find live command IDs")
    catalog.add_argument("query", nargs="?")
    for action, name in (("run", "command"), ("call", "method"), ("render", "path"), ("save", "path"), ("export", "path")):
        sub = commands.add_parser(action)
        sub.add_argument(name)
        sub.add_argument("--args", default="{}")
    return cli


def main(argv=None):
    cli = parser()
    options = cli.parse_args(argv)
    if not 1 <= options.port <= 65535:
        cli.error("--port must be from 1 to 65535")
    try:
        if options.action == "status":
            result = request(options.port, "ui.inspect", {}, request_limit=LIMIT, timeout=options.timeout)
        elif options.action == "commands":
            catalog = request(options.port, "engine.commands", {}, request_limit=LIMIT, timeout=options.timeout)
            if not isinstance(catalog, list):
                raise ControlError("engine.commands returned a non-list catalog")
            query = options.query
            exact = next((item for item in catalog if isinstance(item, dict) and item.get("id") == query), None) if query else None
            if exact is not None:
                result = exact
            else:
                matches = (item for item in catalog if isinstance(item, dict) and (
                    not query or query.casefold() in str(item.get("id", "")).casefold() or query.casefold() in str(item.get("label", "")).casefold()
                ))
                result = [{key: item[key] for key in ("id", "label", "enabled") if key in item} for item in matches]
        else:
            args = json_object(options.args)
            if options.action == "inspect":
                method, params = "document.inspect", args
            elif options.action == "run":
                method, params = "engine.execute", {"command": options.command, "params": args}
            elif options.action == "call":
                method, params = options.method, args
            else:
                method = {"render": "ui.render", "save": "app.save", "export": "app.export"}[options.action]
                params = path_params(options.path, args)
            result = request(options.port, method, params, request_limit=LIMIT, timeout=options.timeout)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ControlError, ValueError, UnicodeError) as exc:
        print(f"vectorcraft: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
