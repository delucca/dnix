import pathlib
import subprocess
import sys
import tempfile
import unittest

import yaml

PROGRAM = sys.argv.pop(1)
ALL_TOOLS = [
    "run_command", "view_file", "write_to_file", "replace_file_content", "grep_search",
    "find_by_name", "search_web", "read_url_content", "invoke_subagent", "ask_question",
    "send_message",
]


def agent(name="a", tools=None, model=None, body="\nBody.\n\nMore.\n"):
    lines = [f"name: {name}", "description: Does a thing."]
    if tools is not None:
        lines.append(f"tools: {tools}")
    if model is not None:
        lines.append(f"model: {model}")
    return "---\n" + "\n".join(lines) + "\n---\n" + body


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
        return subprocess.run(
            [PROGRAM, str(self.out), *srcs], capture_output=True, text=True, cwd=self.dir
        )

    def front(self, name):
        text = (self.out / f"{name}.md").read_text(encoding="utf-8")
        return yaml.safe_load(text.split("\n---\n", 1)[0][4:])

    def tools_of(self, claude_tools):
        proc = self.run_program(self.src("a.md", agent(tools=claude_tools)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return self.front("a")["tools"]

    def assert_skipped(self, proc, fragment):
        self.assertEqual(proc.returncode, 1)
        lines = proc.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, proc.stderr)
        self.assertTrue(lines[0].startswith("agy-agent-md: "), lines[0])
        self.assertIn(fragment, lines[0])

    def test_read_only_tools_stay_read_only(self):
        self.assertEqual(self.tools_of("Read, Grep, Glob"), ["view_file", "grep_search", "find_by_name"])

    def test_scoped_bash_is_the_whole_shell(self):
        self.assertEqual(self.tools_of("Bash(git *)"), ["run_command"])

    def test_no_tools_key_renders_every_tool_once(self):
        proc = self.run_program(self.src("a.md", agent()))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.front("a")["tools"], ALL_TOOLS)

    def test_comma_string_parses(self):
        self.assertEqual(self.tools_of("Read, Grep"), ["view_file", "grep_search"])

    def test_models_map_to_agy_tiers(self):
        cases = {
            "opus": "pro", "sonnet": "flash", "haiku": "flash",
            "inherit": None, "claude-fable-5-1": None,
        }
        for model, want in cases.items():
            with self.subTest(model=model):
                proc = self.run_program(self.src("a.md", agent(model=model)))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(self.front("a").get("model"), want)

    def test_unmapped_tool_skips_that_file_only(self):
        bad = self.src("bad.md", agent("bad", tools="Read, Nope"))
        good = self.src("good.md", agent("good"))
        proc = self.run_program(bad, good)
        self.assert_skipped(proc, "no agy tool for 'Nope'")
        self.assertIn(f"agy-agent-md: {bad}:", proc.stderr)
        self.assertTrue((self.out / "good.md").exists())
        self.assertFalse((self.out / "bad.md").exists())

    def test_missing_frontmatter(self):
        self.assert_skipped(self.run_program(self.src("a.md", "just text\n")), "frontmatter")

    def test_missing_name(self):
        text = "---\ndescription: x\n---\n\nbody\n"
        self.assert_skipped(self.run_program(self.src("a.md", text)), "name")

    def test_name_with_slash(self):
        proc = self.run_program(self.src("a.md", agent("../evil")))
        self.assert_skipped(proc, "plain file name")

    def test_duplicate_name(self):
        first = self.src("one.md", agent("same"))
        second = self.src("two.md", agent("same"))
        proc = self.run_program(first, second)
        self.assert_skipped(proc, f"name same already rendered from {first}")
        self.assertTrue((self.out / "same.md").exists())

    def test_header_names_the_source_as_given(self):
        self.src("a.md", agent())
        proc = subprocess.run(
            [PROGRAM, str(self.out), "a.md"], capture_output=True, text=True, cwd=self.dir
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (self.out / "a.md").read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[1], "# Rendered for agy from a.md; edit that file.")

    def test_body_is_copied_verbatim(self):
        bodies = [
            "\n# Title\n\nLine one.\n  indented\n\n- item\n",
            "    indented first line\n\n---\n\nafter a rule\n",
            "no blank line, no trailing newline",
            "\n\nextra trailing newlines\n\n\n",
        ]
        for body in bodies:
            with self.subTest(body=body):
                proc = self.run_program(self.src("a.md", agent(body=body)))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                text = (self.out / "a.md").read_text(encoding="utf-8")
                self.assertEqual(text.split("\n---\n", 1)[1], body)

    def test_frontmatter_not_a_mapping(self):
        proc = self.run_program(self.src("a.md", "---\n- a\n---\n\nb\n"))
        self.assert_skipped(proc, "not a mapping")

    def test_missing_description(self):
        proc = self.run_program(self.src("a.md", "---\nname: a\n---\n\nb\n"))
        self.assert_skipped(proc, "description")

    def assert_skipped_then_next_rendered(self, bad):
        good = self.src("z-good.md", agent("good"))
        proc = self.run_program(bad, good)
        self.assert_skipped(proc, f"agy-agent-md: {bad}:")
        self.assertTrue((self.out / "good.md").exists())

    def test_tools_not_a_list_or_string(self):
        for value in ("5", "true", "{Read: 1}"):
            with self.subTest(tools=value):
                self.assert_skipped_then_next_rendered(self.src("a.md", agent("a", tools=value)))

    def test_tools_with_a_non_string_item(self):
        for value in ("[Read, null]", "[Read, 3]"):
            with self.subTest(tools=value):
                self.assert_skipped_then_next_rendered(self.src("a.md", agent("a", tools=value)))

    def test_list_model_is_omitted_not_fatal(self):
        proc = self.run_program(self.src("a.md", agent(model="[opus]")))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("model", self.front("a"))

    def test_non_utf8_source(self):
        path = self.dir / "a.md"
        path.write_bytes(agent(body="caf\u00e9\n").encode("latin-1"))
        self.assert_skipped_then_next_rendered(str(path))


if __name__ == "__main__":
    unittest.main()
