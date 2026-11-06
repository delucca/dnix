#!/usr/bin/env python3
"""Test the Safari CLI contract with osascript, defaults and screencapture stubbed out."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


COMMON = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
SCRIPT = COMMON / "skills/use-safari/scripts/safari.py"
sys.argv = sys.argv[:1]
spec = importlib.util.spec_from_file_location("safari_cli", SCRIPT)
safari = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safari)
safari.POLL = 0
safari.RAISE_DELAY = 0


class Done:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


class Fake:
    """Answers subprocess.run for osascript (one scripted reply per request), defaults and screencapture."""

    def __init__(self, replies, apple_events_js="1", capture_rc=0):
        self.replies = list(replies)
        self.requests = []
        self.argvs = []
        self.apple_events_js = apple_events_js
        self.capture_rc = capture_rc

    def __call__(self, cmd, input=None, **kwargs):
        self.argvs.append(cmd)
        if cmd[0] == "defaults":
            return Done(self.apple_events_js + "\n")
        if cmd[0] == "screencapture":
            if self.capture_rc == 0:
                Path(cmd[-1]).write_bytes(b"png")
            return Done(returncode=self.capture_rc, stderr="could not create image from window")
        request = json.loads(input)
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return Done(json.dumps(reply(request) if callable(reply) else reply))


def page(value, tab="7:2"):
    return {"ok": True, "tab": tab, "result": json.dumps({"ok": True, "v": value})}


def run(fake, *argv):
    out, err = io.StringIO(), io.StringIO()
    with patch.object(safari.subprocess, "run", fake), redirect_stdout(out), redirect_stderr(err):
        code = safari.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class SafariCliTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HOME": self.home.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.home.cleanup()

    def test_wraps_bare_expressions_and_passes_functions_through(self):
        self.assertEqual(safari.as_function("document.title"), "() => (document.title\n)")
        for code in ("() => 1", "async () => 1", "x => x", "function () { return 1 }", "async function f() {}"):
            self.assertEqual(safari.as_function(code), code)

    def test_request_travels_on_stdin_not_argv(self):
        fake = Fake([page("t")])
        run(fake, "evaluate", "document.title")
        self.assertEqual(fake.argvs[0], ["osascript", "-l", "JavaScript", str(safari.RUNNER)])
        self.assertIn("document.title", fake.requests[0]["code"])

    def test_evaluate_prints_strings_raw_and_objects_as_json(self):
        self.assertEqual(run(Fake([page("Title")]), "evaluate", "document.title")[1], "Title\n")
        code, out, _ = run(Fake([page({"n": 2})]), "evaluate", "({n: 2})")
        self.assertEqual((code, json.loads(out)), (0, {"n": 2}))

    def test_evaluate_awaits_a_promise_on_the_resolved_tab(self):
        pending = {"ok": True, "tab": "7:2", "result": json.dumps({"pending": "p1"})}
        still = {"ok": True, "tab": "7:2", "result": json.dumps({"pending": "p1"})}
        fake = Fake([pending, still, page({"async": True})])
        code, out, _ = run(fake, "evaluate", "--tab", "example", "fetch('/x')")
        self.assertEqual((code, json.loads(out)), (0, {"async": True}))
        self.assertEqual([r["tab"] for r in fake.requests], ["example", "7:2", "7:2"])
        self.assertIn('"p1"', fake.requests[1]["code"])

    def test_page_exception_fails(self):
        reply = {"ok": True, "tab": "7:2", "result": json.dumps({"ok": False, "error": "Can't find variable: nope"})}
        code, _, err = run(Fake([reply]), "evaluate", "nope")
        self.assertEqual(code, 1)
        self.assertIn("page error: Can't find variable: nope", err)

    def test_automation_denial_names_the_privacy_setting(self):
        reply = {"ok": False, "error": "Not authorized to send Apple events to Safari.", "code": -1743, "appleEvent": True}
        code, _, err = run(Fake([reply]), "evaluate", "1")
        self.assertEqual(code, 1)
        self.assertIn("Privacy & Security > Automation", err)

    def test_disabled_apple_events_javascript_prints_the_setup(self):
        reply = {"ok": False, "error": "localized refusal", "code": 8, "appleEvent": True}
        code, _, err = run(Fake([reply], apple_events_js="0"), "evaluate", "1")
        self.assertEqual(code, 1)
        self.assertIn("Allow JavaScript from Apple Events", err)

    def test_refusals_skip_the_setup_hint(self):
        reply = {"ok": False, "error": 'no tab matches "x"; run tabs', "code": None, "appleEvent": False}
        _, _, err = run(Fake([reply], apple_events_js="0"), "evaluate", "--tab", "x", "1")
        self.assertNotIn("Allow JavaScript", err)

    def test_a_hung_safari_points_at_page_dialogs(self):
        hang = subprocess.TimeoutExpired(cmd="osascript", timeout=30)
        code, _, err = run(Fake([hang]), "evaluate", "1")
        self.assertEqual(code, 1)
        self.assertIn("page dialog", err)

    def test_wait_retries_empty_replies_until_ready(self):
        empty = {"ok": True, "tab": "7:2", "result": None}
        code, out, _ = run(Fake([empty, page(False), page(True)]), "wait", "--tab", "7:2", "--selector", "#late")
        self.assertEqual(code, 0)
        self.assertIn("ready: selector '#late'", out)

    def test_wait_stops_on_a_page_error(self):
        bad = {"ok": True, "tab": "7:2", "result": json.dumps({"ok": False, "error": "'##' is not a valid selector."})}
        fake = Fake([bad])
        code, _, err = run(fake, "wait", "--tab", "7:2", "--selector", "##", "--timeout", "5")
        self.assertEqual((code, len(fake.requests)), (1, 1))
        self.assertIn("not a valid selector", err)

    def test_click_refuses_an_ambiguous_match_and_lists_candidates(self):
        value = {"error": "2 elements match; pass --nth", "candidates": ['button "Delete"', 'button "Delete"']}
        code, _, err = run(Fake([page(value)]), "click", "--text", "Delete")
        self.assertEqual(code, 1)
        self.assertIn('2. button "Delete"', err)

    def test_click_needs_a_target(self):
        self.assertEqual(run(Fake([]), "click")[0], 1)

    def test_copy_leaves_the_value_to_the_runner(self):
        reply = {"ok": True, "from": "7:1", "to": "7:2", "length": 56, "prefix": "key_", "filled": 56}
        fake = Fake([reply])
        code, out, _ = run(fake, "copy", "--from", "issuer", "--to", "settings", "--selector", "code", "--field", "#key")
        request = fake.requests[0]
        self.assertEqual(code, 0)
        self.assertEqual(request["fillTemplate"].count(request["placeholder"]), 1)
        self.assertNotIn(request["placeholder"], request["readCode"])
        self.assertEqual((request["from"], request["to"]), ("issuer", "settings"))
        self.assertIn("copied key_… (56 chars)", out)

    def test_tabs_hide_query_strings_unless_full(self):
        reply = {"ok": True, "windows": [{"id": 7, "tabs": [
            {"index": 1, "title": "Callback", "url": "https://x.test/cb?code=secret#frag", "current": True},
        ]}]}
        out = run(Fake([reply]), "tabs")[1]
        self.assertIn("7:1  * Callback  https://x.test/cb\n", out)
        self.assertNotIn("secret", out)
        self.assertIn("code=secret", run(Fake([reply]), "tabs", "--full")[1])

    def test_screenshot_gives_focus_back_even_when_capture_fails(self):
        front = {"ok": True, "tab": "7:2", "windowId": 7, "prev": "org.gnu.Emacs"}
        fake = Fake([front, {"ok": True}], capture_rc=1)
        code, _, err = run(fake, "screenshot")
        self.assertEqual(code, 1)
        self.assertEqual(fake.requests[1], {"op": "activate", "bundle": "org.gnu.Emacs"})
        self.assertIn("Screen Recording", err)

    def test_screenshot_saves_under_the_private_cache(self):
        front = {"ok": True, "tab": "7:2", "windowId": 7, "prev": "com.apple.Safari"}
        fake = Fake([front])
        code, out, _ = run(fake, "screenshot")
        self.assertEqual(code, 0)
        self.assertEqual(len(fake.requests), 1)
        self.assertIn(str(Path(self.home.name) / ".cache/safari-cm"), out)
        self.assertIn("-l7", fake.argvs[-1])

    def test_navigate_marks_the_old_page_before_loading_in_place(self):
        fake = Fake([page(True, tab="7:3"), {"ok": True, "tab": "7:3"}, page(True, tab="7:3"),
                     {"ok": True, "tab": "7:3", "title": "Example", "url": "https://example.com/"}])
        code, out, _ = run(fake, "navigate", "--tab", "old", "example.com")
        self.assertEqual(code, 0)
        self.assertIn("__useSafariNav = true", fake.requests[0]["code"])
        self.assertEqual(fake.requests[1], {"op": "navigate", "tab": "7:3", "url": "https://example.com"})
        self.assertEqual(out, "7:3  Example  https://example.com/\n")


if __name__ == "__main__":
    unittest.main(verbosity=1)
