#!/usr/bin/env python3
"""Test the Glyphs CLI contract without contacting an installed font editor."""

import asyncio
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


COMMON = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
SCRIPT = COMMON / "skills/use-glyphs/scripts/glyphs.py"
sys.argv = sys.argv[:1]
spec = importlib.util.spec_from_file_location("glyphs_cli", SCRIPT)
glyphs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glyphs)


class Result:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, **kwargs):
        return self.payload


class Session:
    def __init__(self, pages=None, reply=None, error=None, pre_error=None, page_delay=0, call_delay=0, cleanup_delay=0):
        self.pages = pages or []
        self.reply = reply or {"content": [{"type": "text", "text": '{"ok":true,"data":{}}'}], "isError": False}
        self.error = error
        self.pre_error = pre_error
        self.page_delay = page_delay
        self.call_delay = call_delay
        self.cleanup_delay = cleanup_delay
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.call_delay:
            await asyncio.sleep(self.call_delay)
        if self.error:
            raise self.error
        return Result(self.reply)

    async def list_tools(self, cursor=None):
        self.calls.append(("list_tools", cursor))
        if self.page_delay:
            await asyncio.sleep(self.page_delay)
        return self.pages.pop(0)


def tool(name, description=""):
    payload = {"name": name, "description": description, "inputSchema": {"type": "object"}, "_meta": {"origin": "live"}}
    return SimpleNamespace(name=name, description=description, model_dump=lambda **_: payload)


def invoke(session, *argv, input_text=None):
    @asynccontextmanager
    async def fake_session(url, timeout):
        session.calls.append(("connect", url, timeout))
        if session.pre_error:
            raise session.pre_error
        try:
            yield session
        finally:
            if session.cleanup_delay:
                await asyncio.sleep(session.cleanup_delay)

    stdout, stderr = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as directory, patch.object(glyphs, "OUT_DIR", glyphs.OUT_DIR or Path(directory)), patch.object(glyphs, "open_session", fake_session), patch.object(sys, "stdin", io.StringIO(input_text or "")):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = glyphs.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


class GlyphsCliTests(unittest.TestCase):
    def test_aliases_and_exact_nested_parameters(self):
        session = Session()
        for command, expected in (("status", "get_status"), ("documents", "list_documents")):
            code, output, error = invoke(session, command)
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(json.loads(output), session.reply)
            self.assertEqual(session.calls[-1], (expected, {}))

        params = {"document_id": "font-1", "options": {"targets": [{"glyph": "b", "layers": [1, 2]}]}, "path": "/tmp/a b.glyphs"}
        code, output, _ = invoke(session, "call", "start_edit_workflow", "--args", "-", input_text=json.dumps(params))
        self.assertEqual(code, 0)
        self.assertEqual(session.calls[-1], ("start_edit_workflow", params))
        self.assertEqual(json.loads(output), session.reply)

    def test_invalid_args_stop_before_connection(self):
        for value in ("{broken", "[]", "null", "1", '{"x":NaN}', '{"x":1e999}'):
            with self.subTest(value=value):
                session = Session()
                code, output, error = invoke(session, "call", "save_document", "--args", value)
                self.assertEqual(code, 2)
                self.assertEqual(output, "")
                self.assertIn("--args", error)
                self.assertEqual(session.calls, [])

    def test_tool_pagination_filter_and_exact_schema(self):
        pages = [
            SimpleNamespace(tools=[tool("get_status", "Read state")], nextCursor="next"),
            SimpleNamespace(tools=[tool("save_document", "Persist native source")], nextCursor=None),
        ]
        session = Session(pages=pages)
        code, output, _ = invoke(session, "tools", "native")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), [{"name": "save_document", "description": "Persist native source"}])
        self.assertEqual(session.calls[-2:], [("list_tools", None), ("list_tools", "next")])

        session = Session(pages=[SimpleNamespace(tools=[tool("save_document", "Persist native source")], nextCursor=None)])
        code, output, _ = invoke(session, "describe", "save_document")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["_meta"], {"origin": "live"})
        session = Session(pages=[SimpleNamespace(tools=[], nextCursor=None)])
        code, output, error = invoke(session, "describe", "missing")
        self.assertEqual((code, output), (2, ""))
        self.assertIn("not advertised", error)

    def test_result_retains_content_metadata_and_detects_errors(self):
        reply = {
            "content": [{"type": "text", "text": '{"ok":false,"error":{"code":"blocked"}}'}, {"type": "image", "mimeType": "image/png", "data": "QUJD"}],
            "structuredContent": {}, "isError": False, "_meta": {"trace": "one"},
        }
        session = Session(reply=reply)
        code, output, _ = invoke(session, "call", "start_job")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output), reply)

        reply["content"][0]["text"] = "ordinary text"
        reply["structuredContent"] = {"ok": False, "error": "stale"}
        code, output, _ = invoke(session, "call", "get_job")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output), reply)

        reply["structuredContent"] = {}
        reply["isError"] = True
        code, output, _ = invoke(session, "call", "get_job")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output), reply)

    def test_timeout_does_not_replay_and_large_result_spills(self):
        session = Session(error=TimeoutError())
        code, output, error = invoke(session, "call", "start_edit_workflow")
        self.assertEqual((code, output), (1, ""))
        self.assertIn("tool may have run", error)
        self.assertEqual(session.calls[-1], ("start_edit_workflow", {}))
        self.assertEqual(len([call for call in session.calls if call[0] == "start_edit_workflow"]), 1)

        session = Session(error=ConnectionResetError("connection closed"))
        code, output, error = invoke(session, "call", "save_document")
        self.assertEqual((code, output), (1, ""))
        self.assertIn("tool may have run", error)
        self.assertEqual(session.calls[-1], ("save_document", {}))

        session = Session(pre_error=ExceptionGroup("transport", [ConnectionRefusedError("connection refused")]))
        code, output, error = invoke(session, "call", "save_document")
        self.assertEqual((code, output), (1, ""))
        self.assertIn("ConnectionRefusedError: connection refused", error)
        self.assertNotIn("may have run", error)
        self.assertEqual(len(session.calls), 1)

        session = Session(reply={"content": [{"type": "text", "text": "x" * 5000}], "structuredContent": {}, "isError": False})
        with tempfile.TemporaryDirectory() as directory, patch.object(glyphs, "OUT_DIR", Path(directory)):
            code, output, error = invoke(session, "call", "read_entities")
            self.assertEqual((code, error), (0, ""))
            files = list(Path(directory).iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text()), session.reply)
            self.assertIn(str(files[0]), output)

    def test_deadline_covers_all_pages_call_and_cleanup(self):
        pages = [SimpleNamespace(tools=[], nextCursor=str(i)) for i in range(1, 4)]
        session = Session(pages=pages, page_delay=0.04)
        code, output, error = invoke(session, "--timeout", "0.06", "tools")
        self.assertEqual((code, output), (1, ""))
        self.assertIn("timed out", error)
        self.assertLess(len([call for call in session.calls if call[0] == "list_tools"]), 3)

        session = Session(call_delay=0.1)
        code, output, error = invoke(session, "--timeout", "0.02", "call", "start_job")
        self.assertEqual((code, output), (1, ""))
        self.assertIn("tool may have run", error)
        self.assertEqual(len([call for call in session.calls if call[0] == "start_job"]), 1)

        session = Session(cleanup_delay=0.1)
        code, output, error = invoke(session, "--timeout", "0.02", "documents")
        self.assertEqual((code, output), (1, ""))
        self.assertIn("timed out", error)


if __name__ == "__main__":
    unittest.main()
