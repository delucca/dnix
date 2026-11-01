#!/usr/bin/env python3
"""Test credential.read against a fake reader in a throwaway ~/.config/ai."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

LIB = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.argv = sys.argv[:1]
sys.path.insert(0, str(LIB))
import credential  # noqa: E402

READER = """#!/bin/sh
case "$1" in
  ok) echo " s3cret " ;;
  empty) echo "" ;;
  *) echo "no such item: $1" >&2; exit 3 ;;
esac
"""


class ReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.reader = root / "reader"
        self.reader.write_text(READER)
        self.reader.chmod(0o755)
        credential.AI_DIR = root / "ai"
        (credential.AI_DIR / "settings").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def configure(self, command, secrets):
        if command is not None:
            (credential.AI_DIR / "secrets.json").write_text(json.dumps({"readCommand": command}))
        (credential.AI_DIR / "settings" / "skill.json").write_text(json.dumps({"secrets": secrets, "url": "u"}))

    def exit_message(self, key="token"):
        with self.assertRaises(SystemExit) as e:
            credential.read("skill", key)
        return str(e.exception.code)

    def test_reads_and_strips(self):
        self.configure([str(self.reader)], {"token": "ok"})
        self.assertEqual(credential.read("skill", "token"), "s3cret")

    def test_no_reader(self):
        self.configure(None, {"token": "ok"})
        self.assertIn("dnix.ai.secrets.readCommand", self.exit_message())

    def test_missing_key(self):
        self.configure([str(self.reader)], {})
        self.assertIn("dnix.ai.skills.skill.settings.secrets.token", self.exit_message())

    def test_reader_fails(self):
        self.configure([str(self.reader)], {"token": "gone"})
        message = self.exit_message()
        self.assertIn("exit 3", message)
        self.assertIn("no such item: gone", message)

    def test_empty_value(self):
        self.configure([str(self.reader)], {"token": "empty"})
        self.assertIn("returned an empty", self.exit_message())

    def test_reader_not_found(self):
        self.configure([os.path.join(self.tmp.name, "absent")], {"token": "ok"})
        self.assertIn("is not on PATH", self.exit_message())

    def test_settings(self):
        self.configure([str(self.reader)], {})
        self.assertEqual(credential.settings("skill")["url"], "u")
        self.assertEqual(credential.settings("other"), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
