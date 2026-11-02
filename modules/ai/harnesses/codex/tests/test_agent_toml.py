import pathlib
import subprocess
import sys
import tempfile
import tomllib
import unittest

PROGRAM = sys.argv.pop(1)


def agent(name="a", body="\nBody.\n\nMore.\n", extra=""):
    return f"---\nname: {name}\ndescription: Does a thing.\ntools: Read, Bash(git *)\nmodel: opus\n{extra}---\n{body}"


class RenderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)
        self.out = self.dir / "out"
        self.out.mkdir()

    def src(self, fname, text):
        path = self.dir / fname
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_program(self, *srcs):
        return subprocess.run([PROGRAM, str(self.out), *srcs], capture_output=True, text=True, cwd=self.dir)

    def doc(self, name):
        return tomllib.loads((self.out / f"{name}.toml").read_text(encoding="utf-8"))

    def assert_skipped(self, proc, fragment):
        self.assertEqual(proc.returncode, 1)
        lines = proc.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, proc.stderr)
        self.assertTrue(lines[0].startswith("codex-agent-toml: "), lines[0])
        self.assertIn(fragment, lines[0])

    def test_renders_name_description_and_the_body_only(self):
        proc = self.run_program(self.src("a.md", agent()))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.doc("a"), {"name": "a", "description": "Does a thing.", "developer_instructions": "Body.\n\nMore."})

    def test_header_names_the_source_as_given(self):
        self.src("a.md", agent())
        self.assertEqual(self.run_program("a.md").returncode, 0)
        first = (self.out / "a.toml").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first, "# Rendered for Codex from a.md; edit that file.")

    def test_file_is_named_by_the_frontmatter_name(self):
        self.assertEqual(self.run_program(self.src("file.md", agent("other"))).returncode, 0)
        self.assertEqual([p.name for p in self.out.iterdir()], ["other.toml"])

    def test_a_bad_source_is_skipped_and_the_rest_still_render(self):
        bad = self.src("bad.md", "just text\n")
        good = self.src("good.md", agent("good"))
        proc = self.run_program(bad, good)
        self.assert_skipped(proc, f"codex-agent-toml: {bad}: no ---fenced YAML frontmatter")
        self.assertEqual([p.name for p in self.out.iterdir()], ["good.toml"])

    def test_invalid_frontmatter_is_reported(self):
        cases = {
            "---\n- a\n---\n\nb\n": "not a mapping",
            "---\nname: [\n---\n\nb\n": "not valid YAML",
            "---\nname: a\n---\n\nb\n": "missing name or description",
            agent("../evil"): "plain file name",
        }
        for text, fragment in cases.items():
            with self.subTest(fragment=fragment):
                self.assert_skipped(self.run_program(self.src("a.md", text)), fragment)

    def test_duplicate_name_keeps_the_first(self):
        first = self.src("one.md", agent("same", body="first"))
        second = self.src("two.md", agent("same", body="second"))
        self.assert_skipped(self.run_program(first, second), f"name same already rendered from {first}")
        self.assertEqual(self.doc("same")["developer_instructions"], "first")

    def test_non_utf8_source_is_skipped(self):
        path = self.dir / "a.md"
        path.write_bytes(agent(body="café\n").encode("latin-1"))
        self.assert_skipped(self.run_program(str(path)), str(path))


if __name__ == "__main__":
    unittest.main()
