#!/usr/bin/env python3
"""Exercise the FigCraft CLI against a one-request local control server."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest


COMMON = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
SCRIPT = COMMON / "skills/use-figcraft/scripts/figcraft.py"
sys.argv = sys.argv[:1]


class FakeControl:
    def __init__(self, reply=None, delay=0):
        self.reply = reply if reply is not None else {"id": 1, "ok": True, "result": {"accepted": True}}
        self.delay = delay
        self.received = None
        self.connected = False
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(2)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def serve(self):
        try:
            conn, _ = self.listener.accept()
        except socket.timeout:
            return
        except OSError:
            return
        self.connected = True
        with conn:
            data = bytearray()
            while not data.endswith(b"\n"):
                piece = conn.recv(65536)
                if not piece:
                    return
                data.extend(piece)
            self.received = json.loads(data)
            if self.delay:
                time.sleep(self.delay)
            try:
                conn.sendall(json.dumps(self.reply).encode() + b"\n")
            except OSError:
                pass

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.thread.join(1)
        self.listener.close()


def invoke(*args, reply=None, input_data=None, delay=0):
    with FakeControl(reply, delay) as server:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--port", str(server.port), *args],
            input=input_data, text=True, capture_output=True, timeout=5,
        )
    return result, server


class FigCraftCliTests(unittest.TestCase):
    def test_status_and_inspect_window_mapping(self):
        windows = [{"id": 0, "title": "Draft", "active": "Draft", "files": ["Draft"], "focused": True}]
        result, server = invoke("status", reply={"id": 1, "ok": True, "result": windows})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), windows)
        self.assertEqual((server.received["method"], server.received["params"]), ("window.list", {}))

        result, server = invoke("--window", "0", "inspect", "--depth", "3", "--all-pages")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(server.received["method"], "document.inspect")
        self.assertEqual(server.received["params"], {"window": 0, "depth": 3, "allPages": True})

    def test_command_discovery_preserves_full_schema(self):
        catalog = [
            {"id": "shape.rectangle", "label": "Rectangle", "params": "{x,y,width,height}", "menu": None, "shortcut": "R", "undoable": True},
            {"id": "file.save", "label": "Save", "params": "{path?}", "menu": "File", "shortcut": "Cmd+S", "undoable": False},
        ]
        reply = {"id": 1, "ok": True, "result": catalog}
        result, server = invoke("commands", "SHAPE.RECTANGLE", reply=reply)
        self.assertEqual(server.received["method"], "engine.commands")
        self.assertEqual(json.loads(result.stdout), catalog[0])
        result, _ = invoke("commands", "path", reply=reply)
        self.assertEqual(json.loads(result.stdout), [catalog[1]])
        result, _ = invoke("commands", reply=reply)
        self.assertEqual(json.loads(result.stdout), catalog)

    def test_run_stdin_and_arbitrary_call_are_passed_through(self):
        nested = {"ids": [2], "props": {"path": "nested/unchanged.figcraft", "fill": "#f00"}}
        result, server = invoke("--window", "4", "run", "node.set", "--args", "-", input_data=json.dumps(nested))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(server.received["params"], {"window": 4, "command": "node.set", "params": nested})

        native = {"id": 2, "depth": 3, "window": 4}
        result, server = invoke("--window", "4", "call", "node.get", "--args", json.dumps(native))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(server.received["method"], "node.get")
        self.assertEqual(server.received["params"], native)

    def test_render_save_export_paths_and_warnings(self):
        relative = "output folder/preview image.png"
        result, server = invoke("render", relative, "--args", '{"ids":[2],"scale":2}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(server.received["method"], "ui.render")
        self.assertEqual(server.received["params"], {"path": str(Path(relative).absolute()), "ids": [2], "scale": 2})

        save_path = str(Path("native.figcraft").absolute())
        result, server = invoke("save", "native.figcraft")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(server.received["params"], {"command": "file.save", "params": {"path": save_path}})

        fig_path = str(Path("copy.fig").absolute())
        warning = {"path": fig_path, "bytes": 100, "warnings": ["unsupported effect"]}
        result, server = invoke("save", "copy.fig", reply={"id": 1, "ok": True, "result": warning})
        self.assertEqual(server.received["params"]["params"]["path"], fig_path)
        self.assertEqual(json.loads(result.stdout), warning)

        export_path = str(Path("out image.svg").absolute())
        result, server = invoke("export", "out image.svg", "--args", '{"ids":[2],"format":"svg"}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(server.received["params"], {"command": "file.export", "params": {"path": export_path, "ids": [2], "format": "svg"}})

    def test_backend_errors_and_timeout_uncertainty(self):
        result, _ = invoke("run", "shape.rectangle", reply={"id": 1, "ok": False, "error": "document is locked"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("document is locked", result.stderr)
        self.assertEqual(result.stdout, "")

        result, server = invoke("--timeout", "0.05", "run", "shape.rectangle", delay=0.2)
        self.assertTrue(server.connected)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("may have run", result.stderr)

    def test_invalid_arguments_never_connect(self):
        cases = [
            ("run", "node.set", "--args", "not-json"),
            ("run", "node.set", "--args", "[]"),
            ("run", "node.set", "--args", '{"scale":1e999}'),
            ("render", "out.png", "--args", '{"path":"other.png"}'),
            ("--window", "0", "call", "node.get", "--args", '{"window":1,"id":2}'),
            ("--window", "0", "call", "node.get", "--args", '{"window":false,"id":2}'),
        ]
        for args in cases:
            with self.subTest(args=args):
                result, server = invoke(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(server.connected)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
