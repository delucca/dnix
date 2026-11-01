#!/usr/bin/env python3
"""Fake native control server tests; never connects to the desktop app."""

from contextlib import contextmanager
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import unittest


COMMON = (Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]).resolve()
SCRIPT = COMMON / "skills/use-vectorcraft/scripts/vectorcraft.py"
sys.path.insert(0, str(COMMON / "lib"))
from craft_control import ControlError, request


@contextmanager
def server(reply=None, handler=None):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    port = listener.getsockname()[1]
    seen = []
    errors = []

    def run():
        try:
            with listener:
                conn, _ = listener.accept()
                with conn:
                    received = bytearray()
                    while b"\n" not in received:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        received.extend(chunk)
                    seen.append(bytes(received))
                    if handler:
                        handler(conn)
                    elif reply is not None:
                        conn.sendall(reply)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield port, seen
    finally:
        thread.join(3)
        if errors:
            raise errors[0]


def response(value=None, *, ok=True, error=None, id=1):
    body = {"id": id, "ok": ok}
    if ok:
        body["result"] = value
    else:
        body["error"] = error
    return json.dumps(body, ensure_ascii=False).encode() + b"\n"


def cli(port, *args, input=None, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), "--port", str(port), *args], input=input,
                          text=True, capture_output=True, cwd=cwd, timeout=4)


class TransportTests(unittest.TestCase):
    def test_unicode_escaping_and_fragmented_reply(self):
        reply = response({"text": "café\n🌿", "nested": [True, None]})

        def fragment(conn):
            for part in (reply[:9], reply[9:21], reply[21:]):
                conn.sendall(part)

        with server(handler=fragment) as (port, seen):
            result = request(port, "écho", {"message": "line\n雪"}, request_limit=1024)
        self.assertEqual(result, {"text": "café\n🌿", "nested": [True, None]})
        self.assertEqual(json.loads(seen[0]), {"id": 1, "method": "écho", "params": {"message": "line\n雪"}})
        self.assertEqual(seen[0].count(b"\n"), 1)

    def test_success_null_and_backend_error_preserved(self):
        with server(response(None)) as (port, _):
            self.assertIsNone(request(port, "test", {}, request_limit=1024))
        with server(response(ok=False, error="still running: check document")) as (port, _):
            with self.assertRaisesRegex(ControlError, "^still running: check document$"):
                request(port, "test", {}, request_limit=1024)

    def test_malformed_replies_require_correlation_and_shape(self):
        bad = (b"{bad}\n", b"[]\n", response({}, id=True), response({}, id=2),
               b'{"id":1,"ok":1,"result":null}\n', b'{"id":1,"ok":true}\n',
               b'{"id":1,"ok":false}\n', b'{"id":1,"ok":true,"result":NaN}\n',
               b'{"id":1,"ok":true,"result":"\xff"}\n', b"")
        for body in bad:
            with self.subTest(body=body[:50]), server(body) as (port, _):
                with self.assertRaisesRegex(ControlError, "may have run"):
                    request(port, "test", {}, request_limit=1024)

    def test_limits_and_deadline(self):
        with self.assertRaisesRegex(ControlError, "exceeds"):
            request(7979, "test", {"text": "x" * 200}, request_limit=30)
        with server(b"x" * (32 * 1024 * 1024 + 1)) as (port, _):
            with self.assertRaisesRegex(ControlError, "32 MiB"):
                request(port, "test", {}, request_limit=1024)

        def trickle(conn):
            for _ in range(4):
                try:
                    conn.sendall(b" ")
                except OSError:
                    break
                time.sleep(0.09)

        with server(handler=trickle) as (port, _):
            start = time.monotonic()
            with self.assertRaisesRegex(ControlError, "may have run"):
                request(port, "test", {}, request_limit=1024, timeout=0.16)
            self.assertLess(time.monotonic() - start, 0.3)

    def test_disconnect_is_uncertain_and_never_retried(self):
        with server(b"") as (port, seen):
            with self.assertRaisesRegex(ControlError, "Inspect the app before retrying"):
                request(port, "engine.execute", {"command": "object.delete", "params": {}}, request_limit=1024)
        self.assertEqual(len(seen), 1)
        self.assertEqual(json.loads(seen[0])["method"], "engine.execute")

    def test_refused_connection_says_nothing_sent(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_:
            socket_.bind(("127.0.0.1", 0))
            port = socket_.getsockname()[1]
        with self.assertRaisesRegex(ControlError, "nothing was sent"):
            request(port, "test", {}, request_limit=1024)


class CommandTests(unittest.TestCase):
    def test_status_and_inspect_use_distinct_methods(self):
        with server(response({"window": "open"})) as (port, seen):
            run = cli(port, "status")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(seen[0]), {"id": 1, "method": "ui.inspect", "params": {}})
        with server(response({"nodes": []})) as (port, seen):
            run = cli(port, "inspect")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(seen[0])["params"], {"depth": 1, "childLimit": 20})

    def test_live_catalog_exact_id_and_label_search(self):
        items = [{"id": "shape.rect", "label": "Rectangle", "enabled": True,
                  "params": {"width": "number"}, "ui": False},
                 {"id": "shape.line", "label": "Line", "enabled": False}]
        for query, expected in (("shape.rect", items[0]), ("rect", [{"id": "shape.rect", "label": "Rectangle", "enabled": True}])):
            with server(response(items)) as (port, seen):
                run = cli(port, "commands", query)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), expected)
            self.assertEqual(json.loads(seen[0])["method"], "engine.commands")

    def test_run_and_call_preserve_json(self):
        params = {"path": "relative/input.svg", "data": [1, False, None], "nested": {"x": "雪"}}
        for args, method, expected in ((('run', 'shape.rect'), 'engine.execute', {"command": "shape.rect", "params": params}),
                                       (('call', 'document.open'), 'document.open', params)):
            with server(response({"pending": "confirm"})) as (port, seen):
                run = cli(port, *args, "--args", "-", input=json.dumps(params))
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), {"pending": "confirm"})
            self.assertEqual(json.loads(seen[0]), {"id": 1, "method": method, "params": expected})

        with server(response("cancelled")) as (port, _):
            run = cli(port, "call", "ui.dialog.cancel")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), "cancelled")

    def test_paths_and_background_result(self):
        with tempfile.TemporaryDirectory() as directory:
            for action, method in (("render", "ui.render"), ("save", "app.save"), ("export", "app.export")):
                with self.subTest(action=action), server(response({"path": "out.svg", "background": True, "status": "Exporting"})) as (port, seen):
                    run = cli(port, action, "./out.svg", "--args", '{"scale":2,"path":"out.svg"}', cwd=directory)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout)["background"], True)
                self.assertEqual(json.loads(seen[0])["method"], method)
                self.assertEqual(json.loads(seen[0])["params"], {"scale": 2, "path": str((Path(directory) / "out.svg").resolve())})

    def test_invalid_args_and_conflicting_path_do_not_connect(self):
        for args in (("run", "x", "--args", "[]"), ("call", "x", "--args", '{"x":NaN}'),
                     ("call", "x", "--args", '{"x":1e999}'),
                     ("save", "a.svg", "--args", '{"path":"b.svg"}')):
            with self.subTest(args=args):
                run = cli(1, *args)
                self.assertNotEqual(run.returncode, 0)
                self.assertNotIn("cannot connect", run.stderr)

    def test_help_and_invalid_timeout(self):
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True).returncode, 0)
        run = subprocess.run([sys.executable, str(SCRIPT), "--timeout", "NaN", "status"], capture_output=True)
        self.assertNotEqual(run.returncode, 0)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
