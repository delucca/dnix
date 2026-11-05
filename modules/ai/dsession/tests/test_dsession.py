import contextlib
import errno
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest import mock

LAUNCHER = os.path.realpath(sys.argv[1]) if len(sys.argv) > 1 else None
ds = None

FAKE = """#!{python}
import json, os, sys
mask = os.umask(0)
os.umask(mask)
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({{"exe": os.path.realpath(__file__), "name": os.path.basename(sys.argv[0]), "argv": sys.argv[1:], "env": dict(os.environ), "umask": mask}}) + "\\n")
"""

RENDERER = """#!{python}
import os, sys, json
out = sys.argv[1]
with open(os.environ["FAKE_RENDER_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_RENDER_NONE"):
    sys.exit(1)
for src in sys.argv[2:]:
    with open(os.path.join(out, os.path.basename(src)), "w") as f:
        f.write("rendered from " + src + "\\n")
sys.exit(int(os.environ.get("FAKE_RENDER_EXIT", "0")))
"""


def load_launcher(path):
    spec = importlib.util.spec_from_file_location("dsession", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def write_json(path, value):
    return write(path, json.dumps(value))


def skill(root, name):
    write(os.path.join(root, name, "SKILL.md"), "---\nname: %s\n---\n" % name)
    return os.path.join(root, name)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


def current_umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


def hook_group(command):
    return {"hooks": [{"type": "command", "command": command}]}


class TTY(io.StringIO):
    def isatty(self):
        return True


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.base = os.path.join(self.home, ".codex")
        self.root = os.path.join(self.tmp, "root")
        self.bin = os.path.join(self.tmp, "bin")
        self.log = os.path.join(self.tmp, "fake.log")
        os.makedirs(self.base)
        os.makedirs(self.root)
        os.makedirs(self.bin)
        for name in ("codex", "claude", "agy"):
            path = write(os.path.join(self.bin, name), FAKE.format(python=sys.executable))
            os.chmod(path, 0o755)
        patcher = mock.patch.dict(os.environ, {
            "HOME": self.home,
            "DSESSION_ROOT": self.root,
            "PATH": self.bin,
            "FAKE_LOG": self.log,
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ("CODEX_HOME", "DSESSION_DIRS", "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", "CLAUDE_CODE_NO_FLICKER", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
            os.environ.pop(key, None)

    def mkdir(self, *parts):
        path = os.path.join(self.tmp, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def run_launcher(self, *args, env=None, cwd=None):
        full = dict(os.environ)
        full.update(env or {})
        return subprocess.run([sys.executable, LAUNCHER, *args], env=full, cwd=cwd or self.tmp, capture_output=True, text=True)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(line) for line in f if line.strip()]

    def only_call(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 1, calls)
        return calls[0]

    def expected_hash(self, dirs, base=None):
        base = os.path.realpath(base or self.base)
        return hashlib.sha256("\0".join([base] + list(dirs)).encode()).hexdigest()[:16]

    def expected_codex_home(self, dirs, base=None):
        return os.path.realpath(os.path.join(self.root, self.expected_hash(dirs, base), "codex"))

    def regenerate(self, dirs):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            home = ds.regenerate_codex(self.base, dirs)
        return home, err.getvalue()

    def lines(self, text):
        return [line for line in text.splitlines() if line.strip()]

    def state_file(self):
        return os.path.join(self.home, ".local", "state", "dsession", "claude-hooks.json")

    def trust(self, *dirs, answer="y\n"):
        out = io.StringIO()
        err = io.StringIO()
        with mock.patch.object(sys, "stdin", TTY(answer * len(dirs))), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ds.trust(list(dirs))
        return code, out.getvalue(), err.getvalue()

    def assert_one_line_exit(self, result, code, line):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(self.lines(result.stderr), [line])
        self.assertEqual(self.calls(), [])


class Grammar(Case):
    def assert_usage(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        lines = self.lines(result.stderr)
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertTrue(lines[0].startswith("dsession: "), lines[0])
        self.assertEqual(self.calls(), [])

    def test_usage_errors_exit_2_with_one_line(self):
        for args in ([], ["new", "codex"], ["new"], ["new", "--"], ["bogus", "--", "codex"], ["resume", "--", "codex"], ["resume"]):
            with self.subTest(args=args):
                self.assert_usage(self.run_launcher(*args))

    def test_malformed_dsession_dirs_is_a_usage_error(self):
        for value in ("nope", '{"a": 1}', "[1]", '"/tmp"'):
            with self.subTest(value=value):
                self.assert_usage(self.run_launcher("new", "--", "codex", env={"DSESSION_DIRS": value}))

    def test_explicit_dir_beats_dsession_dirs(self):
        a = self.mkdir("a")
        b = self.mkdir("b")
        call = self.only_call(self.run_launcher("new", "--dir", b, "--", "codex", env={"DSESSION_DIRS": json.dumps([a])}))
        self.assertEqual(call["argv"], ["--add-dir", b])

    def test_dsession_dirs_json_is_the_list(self):
        a = self.mkdir("a")
        b = self.mkdir("b")
        call = self.only_call(self.run_launcher("new", "--", "codex", "--x", env={"DSESSION_DIRS": json.dumps([a, b])}))
        self.assertEqual(call["argv"], ["--add-dir", a, "--add-dir", b, "--x"])

    def test_passthrough_is_verbatim_after_client(self):
        a = self.mkdir("a")
        call = self.only_call(self.run_launcher("new", "--dir", a, "--", "codex", "--dir", "x", "--", "resume"))
        self.assertEqual(call["argv"], ["--add-dir", a, "--dir", "x", "--", "resume"])


class Resolution(Case):
    def resolve(self, raw, cwd):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = ds.resolve_dirs(raw, cwd)
        return out, err.getvalue()

    def test_relative_tilde_and_duplicates_dedupe_in_first_seen_order(self):
        a = self.mkdir("a")
        b = self.mkdir("b")
        h = os.path.join(self.home, "proj")
        os.makedirs(h)
        link = os.path.join(self.tmp, "link-to-a")
        os.symlink(a, link)
        out, err = self.resolve(["b", "~/proj", a, a + "/", "./a/../a", link, b], self.tmp)
        self.assertEqual(out, [b, h, a])
        self.assertEqual(err, "")

    def test_missing_dir_is_skipped_with_the_exact_warning(self):
        a = self.mkdir("a")
        missing = os.path.join(self.tmp, "gone")
        afile = write(os.path.join(self.tmp, "plain-file"))
        out, err = self.resolve([missing, a, afile], self.tmp)
        self.assertEqual(out, [a])
        self.assertEqual(self.lines(err), [
            "dsession: skipping missing directory %s" % missing,
            "dsession: skipping missing directory %s" % afile,
        ])

    def test_missing_dir_warning_through_the_cli(self):
        missing = os.path.join(self.tmp, "gone")
        result = self.run_launcher("new", "--dir", missing, "--", "codex")
        call = self.only_call(result)
        self.assertEqual(call["argv"], [])
        self.assertNotIn("CODEX_HOME", call["env"])
        self.assertIn("dsession: skipping missing directory %s" % missing, result.stderr.splitlines())

    def test_env_list_resolves_relative_to_launch_cwd(self):
        a = self.mkdir("a")
        call = self.only_call(self.run_launcher("new", "--", "codex", env={"DSESSION_DIRS": json.dumps(["a"])}, cwd=self.tmp))
        self.assertEqual(call["argv"], ["--add-dir", a])


class Exec(Case):
    def test_zero_dirs_execs_codex_untouched(self):
        call = self.only_call(self.run_launcher("new", "--", "codex", "--foo", "bar"))
        self.assertEqual(call["argv"], ["--foo", "bar"])
        self.assertNotIn("CODEX_HOME", call["env"])
        self.assertNotIn("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", call["env"])
        self.assertEqual(os.listdir(self.root), [])

    def test_zero_dirs_execs_claude_untouched(self):
        call = self.only_call(self.run_launcher("new", "--", "claude", "-p", "hi"))
        self.assertEqual(call["argv"], ["-p", "hi"])
        self.assertNotIn("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", call["env"])
        self.assertEqual(os.listdir(self.root), [])

    def test_zero_dirs_codex_resume_form(self):
        call = self.only_call(self.run_launcher("resume", "abc", "--", "codex", "--foo"))
        self.assertEqual(call["argv"], ["resume", "abc", "--foo"])
        self.assertNotIn("CODEX_HOME", call["env"])

    def test_zero_dirs_claude_resume_form(self):
        call = self.only_call(self.run_launcher("resume", "abc", "--", "claude", "-p", "x"))
        self.assertEqual(call["argv"], ["--resume", "abc", "-p", "x"])

    def test_codex_new_with_dirs(self):
        d = self.mkdir("d")
        call = self.only_call(self.run_launcher("new", "--dir", d, "--", "codex", "--foo"))
        self.assertEqual(call["name"], "codex")
        self.assertEqual(call["argv"], ["--add-dir", d, "--foo"])
        self.assertEqual(call["env"]["CODEX_HOME"], self.expected_codex_home([d]))
        self.assertNotIn("CLAUDE_CODE_NO_FLICKER", call["env"])

    def test_codex_resume_with_dirs(self):
        d = self.mkdir("d")
        call = self.only_call(self.run_launcher("resume", "abc", "--dir", d, "--", "codex", "--foo"))
        self.assertEqual(call["argv"], ["resume", "abc", "--add-dir", d, "--foo"])
        self.assertEqual(call["env"]["CODEX_HOME"], self.expected_codex_home([d]))

    def test_claude_resume_with_dirs(self):
        d = self.mkdir("d")
        call = self.only_call(self.run_launcher("resume", "abc", "--dir", d, "--", "claude", "-p", "x"))
        self.assertEqual(call["argv"][:4], ["--resume", "abc", "--add-dir", d])
        self.assertEqual(call["argv"][-2:], ["-p", "x"])

    def test_missing_client_exits_127(self):
        os.remove(os.path.join(self.bin, "claude"))
        d = self.mkdir("d")
        for args, client in ((["new", "--", "claude"], "claude"), (["new", "--dir", d, "--", "claude"], "claude"), (["new", "--", "nosuch"], "nosuch")):
            with self.subTest(args=args):
                result = self.run_launcher(*args)
                self.assertEqual(result.returncode, 127, result.stderr)
                self.assertIn("dsession: %s not found on PATH" % client, result.stderr.splitlines())
        self.assertEqual(self.calls(), [])

    def test_hermetic_fakes_are_the_only_clients_run(self):
        d = self.mkdir("d")
        write(os.path.join(d, "AGENTS.md"), "d rules\n")
        self.only_call(self.run_launcher("new", "--dir", d, "--", "codex"))
        self.assertEqual(self.run_launcher("new", "--dir", d, "--", "claude").returncode, 0)
        calls = self.calls()
        self.assertEqual([c["exe"] for c in calls], [os.path.join(self.bin, "codex"), os.path.join(self.bin, "claude")])
        self.assertEqual(calls[0]["env"]["PATH"], self.bin)
        self.assertEqual(calls[0]["env"]["HOME"], self.home)
        codex_home = calls[0]["env"]["CODEX_HOME"]
        self.assertTrue(codex_home.startswith(self.root + os.sep), codex_home)
        for entry in os.listdir(codex_home):
            path = os.path.join(codex_home, entry)
            if entry == "skills":
                self.assertTrue(os.readlink(path).startswith("skills."), path)
            elif os.path.islink(path):
                self.assertTrue(os.readlink(path).startswith(self.tmp + os.sep), path)


class Overlay(Case):
    def fixture_base(self):
        write(os.path.join(self.base, "AGENTS.md"), "global rules\n")
        real_config = write(os.path.join(self.tmp, "store", "config.toml"), "model = 'x'\n")
        os.symlink(real_config, os.path.join(self.base, "config.toml"))
        write_json(os.path.join(self.base, "hooks.json"), {"hooks": {}})
        write(os.path.join(self.base, "x.sqlite"))
        write(os.path.join(self.base, ".hidden"))
        os.makedirs(os.path.join(self.base, "sessions"))
        skill(os.path.join(self.base, "skills"), "a")
        skill(os.path.join(self.base, "skills"), ".system")

    def test_hash_and_paths_follow_the_spec(self):
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        h = self.expected_hash([d1, d2])
        root, codex_home, claude_dir = ds.overlay_paths(self.base, [d1, d2])
        self.assertEqual(os.path.realpath(codex_home), os.path.join(self.root, h, "codex"))
        self.assertEqual(os.path.realpath(claude_dir), os.path.join(self.root, h, "claude"))

    def test_hash_is_stable_across_runs_and_differs_by_order(self):
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        self.run_launcher("new", "--dir", d1, "--dir", d2, "--", "codex")
        self.run_launcher("new", "--dir", d1, "--dir", d2, "--", "codex")
        self.run_launcher("new", "--dir", d2, "--dir", d1, "--", "codex")
        homes = [c["env"]["CODEX_HOME"] for c in self.calls()]
        self.assertEqual(homes[0], homes[1])
        self.assertNotEqual(homes[0], homes[2])
        self.assertEqual(homes[0], self.expected_codex_home([d1, d2]))
        self.assertEqual(homes[2], self.expected_codex_home([d2, d1]))
        with open(os.path.join(self.root, self.expected_hash([d1, d2]), "dirs")) as f:
            self.assertEqual(self.lines(f.read()), [d1, d2])
        self.assertTrue(os.path.exists(os.path.join(self.root, self.expected_hash([d1, d2]), "lock")))

    def test_codex_home_env_is_the_base_unless_inside_the_overlay_root(self):
        other = os.path.join(self.tmp, "other-codex")
        write(os.path.join(other, "marker"))
        d = self.mkdir("d")
        call = self.only_call(self.run_launcher("new", "--dir", d, "--", "codex", env={"CODEX_HOME": other}))
        self.assertEqual(call["env"]["CODEX_HOME"], self.expected_codex_home([d], other))
        self.assertEqual(os.readlink(os.path.join(call["env"]["CODEX_HOME"], "marker")), os.path.join(other, "marker"))
        os.remove(self.log)
        nested = self.expected_codex_home([d], other)
        call = self.only_call(self.run_launcher("new", "--dir", d, "--", "codex", env={"CODEX_HOME": nested}))
        self.assertEqual(call["env"]["CODEX_HOME"], self.expected_codex_home([d]))

    def test_layout_links_every_base_entry_and_generates_three(self):
        self.fixture_base()
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        self.assertEqual(os.path.realpath(home), self.expected_codex_home([d]))
        entries = set(os.listdir(home))
        generated = {"AGENTS.md", "hooks.json", "skills"}
        self.assertTrue(generated <= entries, entries)
        for name in ("AGENTS.md", "hooks.json"):
            self.assertFalse(os.path.islink(os.path.join(home, name)), name)
            self.assertTrue(os.path.isfile(os.path.join(home, name)), name)
        version = os.readlink(os.path.join(home, "skills"))
        self.assertRegex(version, r"^skills\.[^/]+$")
        self.assertTrue(os.path.isdir(os.path.join(home, version)))
        self.assertFalse(os.path.islink(os.path.join(home, version)))
        linked = entries - generated - {version}
        self.assertEqual(linked, set(os.listdir(self.base)) - generated)
        self.assertIn(".hidden", linked)
        for name in linked:
            self.assertEqual(os.readlink(os.path.join(home, name)), os.path.join(self.base, name), name)
        self.assertEqual(os.readlink(os.path.join(home, "skills", ".system")), os.path.join(self.base, "skills", ".system"))
        self.assertEqual(os.readlink(os.path.join(home, "skills", "a")), os.path.join(self.base, "skills", "a"))

    def test_no_system_link_without_base_system(self):
        skill(os.path.join(self.base, "skills"), "a")
        home, _ = self.regenerate([self.mkdir("d")])
        self.assertEqual(sorted(os.listdir(os.path.join(home, "skills"))), ["a"])

    def test_dangling_and_misdirected_symlinks_are_repaired(self):
        self.fixture_base()
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        os.symlink(os.path.join(self.tmp, "nowhere"), os.path.join(home, "ghost"))
        elsewhere = write(os.path.join(self.tmp, "elsewhere.sqlite"))
        os.remove(os.path.join(home, "x.sqlite"))
        os.symlink(elsewhere, os.path.join(home, "x.sqlite"))
        os.remove(os.path.join(self.base, ".hidden"))
        home, _ = self.regenerate([d])
        self.assertFalse(os.path.lexists(os.path.join(home, "ghost")))
        self.assertFalse(os.path.lexists(os.path.join(home, ".hidden")))
        self.assertEqual(os.readlink(os.path.join(home, "x.sqlite")), os.path.join(self.base, "x.sqlite"))

    def test_codex_home_bound_directories_stay_in_the_overlay(self):
        self.fixture_base()
        for name in ("app-server-control", "app-server-daemon", "secrets"):
            write(os.path.join(self.base, name, "daemon.pid"), "base")
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        for name in ("app-server-control", "app-server-daemon", "secrets"):
            self.assertFalse(os.path.lexists(os.path.join(home, name)), name)
        os.symlink(os.path.join(self.base, "app-server-daemon"), os.path.join(home, "app-server-daemon"))
        write(os.path.join(home, "app-server-control", "daemon.pid"), "overlay")
        home, err = self.regenerate([d])
        self.assertFalse(os.path.lexists(os.path.join(home, "app-server-daemon")))
        self.assertFalse(os.path.islink(os.path.join(home, "app-server-control")))
        with open(os.path.join(home, "app-server-control", "daemon.pid")) as f:
            self.assertEqual(f.read(), "overlay")
        with open(os.path.join(self.base, "app-server-control", "daemon.pid")) as f:
            self.assertEqual(f.read(), "base")
        self.assertNotIn("adopted", err)

    def test_stray_regular_file_is_adopted_into_base(self):
        self.fixture_base()
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        write(os.path.join(home, "future_9.sqlite"), "rows")
        home, err = self.regenerate([d])
        self.assertIn("dsession: adopted future_9.sqlite into %s" % self.base, self.lines(err))
        with open(os.path.join(self.base, "future_9.sqlite")) as f:
            self.assertEqual(f.read(), "rows")
        self.assertEqual(os.readlink(os.path.join(home, "future_9.sqlite")), os.path.join(self.base, "future_9.sqlite"))

    def test_stray_conflict_is_moved_aside_with_a_timestamp(self):
        self.fixture_base()
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        os.remove(os.path.join(home, "config.toml"))
        write(os.path.join(home, "config.toml"), "stray = true\n")
        home, err = self.regenerate([d])
        aside = [n for n in os.listdir(self.base) if n.startswith("config.toml.dsession-stray-")]
        self.assertEqual(len(aside), 1, os.listdir(self.base))
        self.assertRegex(aside[0], r"^config\.toml\.dsession-stray-\d{8}T\d{6}$")
        with open(os.path.join(self.base, aside[0])) as f:
            self.assertEqual(f.read(), "stray = true\n")
        prefix = "dsession: %s already exists; kept the overlay copy at " % os.path.join(self.base, "config.toml")
        warnings = [line for line in self.lines(err) if line.startswith(prefix)]
        self.assertEqual(len(warnings), 1, err)
        self.assertIn(aside[0], warnings[0])
        self.assertEqual(os.readlink(os.path.join(home, "config.toml")), os.path.join(self.base, "config.toml"))
        with open(os.path.join(self.tmp, "store", "config.toml")) as f:
            self.assertEqual(f.read(), "model = 'x'\n")

    def test_regenerate_keeps_the_inode_and_updates_agents_md(self):
        self.fixture_base()
        d = self.mkdir("d")
        write(os.path.join(d, "AGENTS.md"), "first\n")
        home, _ = self.regenerate([d])
        inode = os.stat(home).st_ino
        hash_inode = os.stat(os.path.dirname(home)).st_ino
        write(os.path.join(d, "AGENTS.md"), "second\n")
        again, _ = self.regenerate([d])
        self.assertEqual(os.path.realpath(again), os.path.realpath(home))
        self.assertEqual(os.stat(again).st_ino, inode)
        self.assertEqual(os.stat(os.path.dirname(again)).st_ino, hash_inode)
        with open(os.path.join(again, "AGENTS.md")) as f:
            text = f.read()
        self.assertIn("second", text)
        self.assertNotIn("first", text)


class Skills(Case):
    def test_global_skill_wins_and_duplicate_is_dropped_with_both_paths(self):
        g = skill(os.path.join(self.base, "skills"), "a")
        d = self.mkdir("d")
        dup = skill(os.path.join(d, ".agents", "skills"), "a")
        b = skill(os.path.join(d, ".agents", "skills"), "b")
        home, err = self.regenerate([d])
        self.assertEqual(self.lines(err).count("dsession: skill a from %s dropped: already provided by %s" % (dup, g)), 1, err)
        self.assertEqual(os.readlink(os.path.join(home, "skills", "a")), g)
        self.assertEqual(os.readlink(os.path.join(home, "skills", "b")), b)

    def test_order_is_dir_then_agents_then_claude(self):
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        first = skill(os.path.join(d1, ".claude", "skills"), "s")
        later = skill(os.path.join(d2, ".agents", "skills"), "s")
        agents = skill(os.path.join(d2, ".agents", "skills"), "t")
        claude = skill(os.path.join(d2, ".claude", "skills"), "t")
        home, err = self.regenerate([d1, d2])
        self.assertEqual(os.readlink(os.path.join(home, "skills", "s")), first)
        self.assertEqual(os.readlink(os.path.join(home, "skills", "t")), agents)
        lines = self.lines(err)
        self.assertIn("dsession: skill s from %s dropped: already provided by %s" % (later, first), lines)
        self.assertIn("dsession: skill t from %s dropped: already provided by %s" % (claude, agents), lines)

    def test_home_agents_skills_claim_names_without_links(self):
        g = skill(os.path.join(self.home, ".agents", "skills"), "g")
        d = self.mkdir("d")
        dup = skill(os.path.join(d, ".agents", "skills"), "g")
        home, err = self.regenerate([d])
        self.assertIn("dsession: skill g from %s dropped: already provided by %s" % (dup, g), self.lines(err))
        self.assertFalse(os.path.lexists(os.path.join(home, "skills", "g")))

    def test_symlinked_skill_keeps_the_unresolved_target_and_non_skills_are_ignored(self):
        store = skill(os.path.join(self.tmp, "store"), "linked")
        os.makedirs(os.path.join(self.base, "skills"))
        os.symlink(store, os.path.join(self.base, "skills", "linked"))
        d = self.mkdir("d")
        os.makedirs(os.path.join(d, ".agents", "skills", "not-a-skill"))
        home, _ = self.regenerate([d])
        self.assertEqual(os.readlink(os.path.join(home, "skills", "linked")), os.path.join(self.base, "skills", "linked"))
        self.assertFalse(os.path.lexists(os.path.join(home, "skills", "not-a-skill")))

    def test_same_realpath_duplicate_is_skipped_silently(self):
        d = self.mkdir("d")
        agents = skill(os.path.join(d, ".agents", "skills"), "a")
        os.makedirs(os.path.join(d, ".claude", "skills"))
        os.symlink(agents, os.path.join(d, ".claude", "skills", "a"))
        home, err = self.regenerate([d])
        self.assertNotIn("dropped", err)
        self.assertEqual(os.listdir(os.path.join(home, "skills")), ["a"])
        self.assertEqual(os.readlink(os.path.join(home, "skills", "a")), agents)

    def test_different_realpath_duplicate_warns_with_both_paths(self):
        d = self.mkdir("d")
        agents = skill(os.path.join(d, ".agents", "skills"), "a")
        claude = skill(os.path.join(d, ".claude", "skills"), "a")
        home, err = self.regenerate([d])
        self.assertEqual(self.lines(err), ["dsession: skill a from %s dropped: already provided by %s" % (claude, agents)])
        self.assertEqual(os.readlink(os.path.join(home, "skills", "a")), agents)

    def test_collect_skills_returns_first_seen(self):
        g = skill(os.path.join(self.base, "skills"), "a")
        d = self.mkdir("d")
        skill(os.path.join(d, ".agents", "skills"), "a")
        b = skill(os.path.join(d, ".claude", "skills"), "b")
        with contextlib.redirect_stderr(io.StringIO()):
            found = dict(ds.collect_skills(self.base, [d]))
        self.assertEqual(found["a"], g)
        self.assertEqual(found["b"], b)


class AgentsMd(Case):
    def test_order_headers_and_claude_fallback(self):
        write(os.path.join(self.base, "AGENTS.md"), "GLOBAL\n")
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        d3 = self.mkdir("d3")
        d4 = self.mkdir("d4")
        write(os.path.join(d1, "AGENTS.md"), "ONE-AGENTS\n")
        write(os.path.join(d1, "CLAUDE.md"), "ONE-CLAUDE\n")
        write(os.path.join(d2, "CLAUDE.md"), "TWO-CLAUDE\n@AGENTS.md\n")
        write(os.path.join(d4, "AGENTS.md"), "FOUR-AGENTS\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            text = ds.compose_agents_md(self.base, [d1, d2, d3, d4])
        self.assertTrue(text.startswith("GLOBAL\n"), text)
        h1 = "\n\n# Linked directory: %s/AGENTS.md\n\nONE-AGENTS\n" % d1
        h2 = "\n\n# Linked directory: %s/CLAUDE.md\n\nTWO-CLAUDE\n@AGENTS.md\n" % d2
        h4 = "\n\n# Linked directory: %s/AGENTS.md\n\nFOUR-AGENTS\n" % d4
        for block in (h1, h2, h4):
            self.assertIn(block, text)
        self.assertLess(text.index(h1), text.index(h2))
        self.assertLess(text.index(h2), text.index(h4))
        self.assertNotIn("ONE-CLAUDE", text)
        self.assertNotIn(d3, text)
        self.assertEqual(text.count("# Linked directory:"), 3)
        self.assertEqual(self.lines(err.getvalue()), ["dsession: %s/CLAUDE.md has @imports Codex will not expand" % d2])

    def test_at_warning_is_once_per_file_and_only_for_claude_fallback(self):
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        write(os.path.join(d1, "CLAUDE.md"), "@one\n@two\ntext @not\n")
        write(os.path.join(d2, "AGENTS.md"), "@three\n")
        home, err = self.regenerate([d1, d2])
        self.assertEqual(self.lines(err), ["dsession: %s/CLAUDE.md has @imports Codex will not expand" % d1])
        with open(os.path.join(home, "AGENTS.md")) as f:
            self.assertIn("@three", f.read())

    def test_large_composition_warns_with_the_size(self):
        d = self.mkdir("d")
        write(os.path.join(d, "AGENTS.md"), "x" * 40000 + "\n")
        home, err = self.regenerate([d])
        size = os.path.getsize(os.path.join(home, "AGENTS.md"))
        self.assertIn("dsession: composed AGENTS.md is %d bytes" % size, self.lines(err))

    def test_small_composition_does_not_warn(self):
        d = self.mkdir("d")
        write(os.path.join(d, "AGENTS.md"), "small\n")
        _, err = self.regenerate([d])
        self.assertEqual(err, "")


class Hooks(Case):
    def test_groups_append_in_source_order_unchanged(self):
        g0 = {"hooks": [{"type": "command", "command": "/global/start", "timeout": 5}]}
        a0 = {"matcher": "startup", "hooks": [{"type": "command", "command": "./rel.sh"}]}
        a1 = {"hooks": [{"type": "command", "command": "a-stop"}]}
        b0 = {"hooks": [{"type": "command", "command": "b0", "statusMessage": "hi"}]}
        b1 = {"matcher": "*", "hooks": [{"type": "command", "command": "b1"}]}
        write_json(os.path.join(self.base, "hooks.json"), {"hooks": {"SessionStart": [g0]}})
        write(os.path.join(self.base, "config.toml"))
        a = self.mkdir("a")
        b = self.mkdir("b")
        c = self.mkdir("c")
        write_json(os.path.join(a, ".codex", "hooks.json"), {"hooks": {"SessionStart": [a0], "Stop": [a1]}})
        write_json(os.path.join(b, ".codex", "hooks.json"), {"hooks": {"SessionStart": [b0, b1]}})
        home, err = self.regenerate([a, c, b])
        self.assertEqual(err, "")
        with open(os.path.join(home, "hooks.json")) as f:
            composed = json.load(f)
        self.assertEqual(composed["hooks"], {"SessionStart": [g0, a0, b0, b1], "Stop": [a1]})
        self.assertTrue(composed["description"].startswith("Generated by dsession from "), composed)
        self.assertEqual(list(composed.keys()), ["description", "hooks"])

    def test_unparseable_source_warns_and_is_skipped(self):
        a = self.mkdir("a")
        b = self.mkdir("b")
        bad = write(os.path.join(a, ".codex", "hooks.json"), "{not json")
        b0 = {"hooks": [{"type": "command", "command": "b0"}]}
        write_json(os.path.join(b, ".codex", "hooks.json"), {"hooks": {"Stop": [b0]}})
        home, err = self.regenerate([a, b])
        with open(os.path.join(home, "hooks.json")) as f:
            self.assertEqual(json.load(f)["hooks"], {"Stop": [b0]})
        lines = self.lines(err)
        self.assertEqual(len(lines), 1, err)
        self.assertTrue(lines[0].startswith("dsession: "), lines[0])
        self.assertIn(bad, lines[0])


class Claude(Case):
    def settings_of(self, argv):
        self.assertEqual(argv.count("--settings"), 1, argv)
        value = argv[argv.index("--settings") + 1]
        self.assertTrue(value.startswith(self.root + os.sep), value)
        with open(value) as f:
            return json.load(f)

    def test_argv_order_env_and_append_prompt(self):
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        h = {"hooks": [{"type": "command", "command": "d1-start"}]}
        write_json(os.path.join(d1, ".claude", "settings.json"), {"hooks": {"SessionStart": [h]}})
        write(os.path.join(d1, "AGENTS.md"), "D1-AGENTS\n")
        write(os.path.join(d2, "CLAUDE.md"), "D2-CLAUDE\n")
        self.trust(d1)
        call = self.only_call(self.run_launcher("new", "--dir", d1, "--dir", d2, "--", "claude", "-p", "hi"))
        argv = call["argv"]
        self.assertEqual(argv[:4], ["--add-dir", d1, "--add-dir", d2])
        self.assertEqual(argv[4], "--settings")
        self.assertEqual(argv[6], "--append-system-prompt")
        self.assertEqual(argv[8:], ["-p", "hi"])
        self.assertEqual(len(argv), 10)
        self.assertEqual(self.settings_of(argv)["hooks"], {"SessionStart": [h]})
        prompt = argv[7]
        self.assertIn("# Linked directory: %s/AGENTS.md\n\nD1-AGENTS" % d1, prompt)
        self.assertNotIn("D2-CLAUDE", prompt)
        self.assertEqual(call["env"]["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"], "1")
        self.assertEqual(call["env"]["CLAUDE_CODE_NO_FLICKER"], "1")
        self.assertNotIn("CODEX_HOME", call["env"])

    def test_no_settings_and_no_prompt_when_nothing_to_add(self):
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        write(os.path.join(d1, "CLAUDE.md"), "c\n")
        write(os.path.join(d2, "AGENTS.md"), "a\n")
        write(os.path.join(d2, "CLAUDE.md"), "c\n")
        call = self.only_call(self.run_launcher("new", "--dir", d1, "--dir", d2, "--", "claude"))
        self.assertEqual(call["argv"], ["--add-dir", d1, "--add-dir", d2])
        self.assertEqual(call["env"]["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"], "1")

    def test_passthrough_settings_file_is_merged_after_dir_hooks(self):
        d = self.mkdir("d")
        dh = {"hooks": [{"type": "command", "command": "dir-stop"}]}
        ph = {"hooks": [{"type": "command", "command": "tap-stop"}]}
        write_json(os.path.join(d, ".claude", "settings.json"), {"hooks": {"Stop": [dh]}})
        extra = write_json(os.path.join(self.tmp, "tap.json"), {"statusLine": {"type": "command", "command": "x"}, "hooks": {"Stop": [ph], "SessionStart": [ph]}})
        self.trust(d)
        call = self.only_call(self.run_launcher("new", "--dir", d, "--", "claude", "--settings", extra, "-p", "hi"))
        argv = call["argv"]
        self.assertNotIn(extra, argv)
        self.assertEqual(argv[-2:], ["-p", "hi"])
        settings = self.settings_of(argv)
        self.assertEqual(settings["hooks"], {"Stop": [dh, ph], "SessionStart": [ph]})
        self.assertEqual(settings["statusLine"], {"type": "command", "command": "x"})

    def test_passthrough_settings_json_string_is_merged(self):
        d = self.mkdir("d")
        raw = json.dumps({"statusLine": {"type": "command", "command": "x"}})
        call = self.only_call(self.run_launcher("new", "--dir", d, "--", "claude", "--settings", raw, "-p", "hi"))
        argv = call["argv"]
        self.assertNotIn(raw, argv)
        self.assertEqual(argv[:2], ["--add-dir", d])
        self.assertEqual(argv[-2:], ["-p", "hi"])
        self.assertEqual(self.settings_of(argv)["statusLine"], {"type": "command", "command": "x"})

    def test_unreadable_passthrough_settings_is_dropped_with_a_warning(self):
        d = self.mkdir("d")
        result = self.run_launcher("new", "--dir", d, "--", "claude", "--settings", "not-json", "-p", "hi")
        call = self.only_call(result)
        self.assertIn("dsession: ignoring unreadable --settings not-json", result.stderr.splitlines())
        self.assertEqual(call["argv"], ["--add-dir", d, "-p", "hi"])

    def test_duplicate_claude_skills_only_warn(self):
        d1 = self.mkdir("d1")
        d2 = self.mkdir("d2")
        first = skill(os.path.join(d1, ".claude", "skills"), "s")
        later = skill(os.path.join(d2, ".claude", "skills"), "s")
        result = self.run_launcher("new", "--dir", d1, "--dir", d2, "--", "claude")
        call = self.only_call(result)
        self.assertIn("dsession: skill s from %s dropped: already provided by %s" % (later, first), result.stderr.splitlines())
        self.assertEqual(call["argv"], ["--add-dir", d1, "--add-dir", d2])


class Context(Case):
    TEXT = 'task "q" \\b\nline\ttab\x7f é \U0001F600\n'

    def context(self, text=None, name="c.md"):
        return write(os.path.join(self.tmp, name), self.TEXT if text is None else text)

    def prompt_of(self, argv):
        self.assertEqual(argv.count("--append-system-prompt"), 1, argv)
        return argv[argv.index("--append-system-prompt") + 1]

    def test_grammar(self):
        with contextlib.redirect_stderr(io.StringIO()):
            spaced = ds.parse_args(["new", "--dir", "/a", "--context", "/c", "--", "claude", "-p", "x"])
            joined = ds.parse_args(["new", "--context=/c", "--dir", "/a", "--", "claude", "-p", "x"])
        self.assertEqual(spaced, joined)
        self.assertEqual(spaced.context, "/c")
        for args, line in (
            (["new", "--context", "a", "--context", "b", "--", "claude"], "--context given twice"),
            (["new", "--context"], "--context needs a path"),
            (["trust", "--context", "a"], "trust takes no context"),
        ):
            with self.subTest(args=args):
                self.assert_one_line_exit(self.run_launcher(*args), 2, "dsession: %s; %s" % (line, ds.USAGE))

    def test_claude_with_dirs_appends_the_context_after_the_agents_block(self):
        d = self.mkdir("d")
        write(os.path.join(d, "AGENTS.md"), "D-AGENTS\n")
        call = self.only_call(self.run_launcher("new", "--dir", d, "--context", self.context("TASK\n"), "--", "claude", "-p", "hi"))
        argv = call["argv"]
        self.assertEqual(self.prompt_of(argv), "# Linked directory: %s/AGENTS.md\n\nD-AGENTS\n\nTASK\n" % d)
        self.assertNotIn("--system-prompt-snapshot", argv)
        self.assertEqual(argv[-2:], ["-p", "hi"])
        self.assertEqual(call["env"]["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"], "1")

    def test_claude_zero_dirs_carries_only_the_context(self):
        call = self.only_call(self.run_launcher("new", "--context", self.context("TASK\n"), "--", "claude", "-p", "hi"))
        self.assertEqual(call["argv"], ["--append-system-prompt", "TASK\n", "-p", "hi"])
        self.assertNotIn("CODEX_HOME", call["env"])
        result = self.run_launcher("resume", "abc", "--context", self.context("TASK\n"), "--", "claude")
        self.assertEqual(self.calls()[-1]["argv"], ["--resume", "abc", "--append-system-prompt", "TASK\n"], result.stderr)

    def test_passthrough_prompts_are_merged_after_the_context(self):
        extra = write(os.path.join(self.tmp, "extra.md"), "FILE\n")
        call = self.only_call(self.run_launcher("new", "--context", self.context("TASK\n"), "--", "claude", "--append-system-prompt", "ARG", "--append-system-prompt-file=" + extra, "-p", "hi"))
        self.assertEqual(call["argv"], ["--append-system-prompt", "TASK\n\nARG\n\nFILE\n", "-p", "hi"])
        os.remove(self.log)
        missing = os.path.join(self.tmp, "gone.md")
        result = self.run_launcher("new", "--context", self.context("TASK\n"), "--", "claude", "--append-system-prompt-file", missing, "-p", "hi")
        call = self.only_call(result)
        self.assertEqual(self.lines(result.stderr), ["dsession: ignoring unreadable --append-system-prompt-file " + missing])
        self.assertEqual(call["argv"], ["--append-system-prompt", "TASK\n", "-p", "hi"])

    def test_codex_with_dirs_passes_developer_instructions_as_toml(self):
        d = self.mkdir("d")
        write(os.path.join(d, "AGENTS.md"), "D-AGENTS\n")
        call = self.only_call(self.run_launcher("resume", "abc", "--dir", d, "--context", self.context(), "--", "codex", "--x"))
        argv = call["argv"]
        value = "developer_instructions=" + ds.toml_string(self.TEXT)
        self.assertEqual(argv, ["resume", "abc", "--add-dir", d, "-c", value, "--x"])
        self.assertEqual(tomllib.loads("v = " + argv[5].split("=", 1)[1])["v"], self.TEXT)
        self.assertTrue(call["env"]["CODEX_HOME"].startswith(self.root + os.sep))
        with open(os.path.join(call["env"]["CODEX_HOME"], "AGENTS.md")) as f:
            self.assertNotIn("task", f.read())

    def test_codex_zero_dirs_builds_no_overlay(self):
        call = self.only_call(self.run_launcher("new", "--context", self.context("TASK\n"), "--", "codex", "--x"))
        self.assertEqual(call["argv"], ["-c", 'developer_instructions="TASK\\u000a"', "--x"])
        self.assertNotIn("CODEX_HOME", call["env"])
        self.assertEqual(os.listdir(self.root), [])

    def test_passthrough_developer_instructions_wins_with_a_warning(self):
        for spelling in (["-c", "developer_instructions='mine'"], ["--config= developer_instructions='mine'"], ["-c", "developer_instructions = 'mine'"]):
            with self.subTest(spelling=spelling):
                result = self.run_launcher("new", "--context", self.context("TASK\n"), "--", "codex", *spelling)
                call = self.only_call(result)
                self.assertEqual(call["argv"], ["-c", 'developer_instructions="TASK\\u000a"'] + spelling)
                self.assertEqual(self.lines(result.stderr), ["dsession: pass-through developer_instructions overrides --context"])
                os.remove(self.log)

    def test_unreadable_or_blank_context_launches_without_it(self):
        missing = os.path.join(self.tmp, "gone.md")
        result = self.run_launcher("new", "--context", missing, "--", "claude", "-p", "hi")
        call = self.only_call(result)
        self.assertEqual(self.lines(result.stderr), ["dsession: skipping unreadable context " + missing])
        self.assertEqual(call["argv"], ["-p", "hi"])
        os.remove(self.log)
        result = self.run_launcher("new", "--context", self.context(" \n\t\n"), "--", "claude", "-p", "hi")
        call = self.only_call(result)
        self.assertEqual(result.stderr, "")
        self.assertEqual(call["argv"], ["-p", "hi"])

    def test_large_context_is_truncated_on_a_line(self):
        marker = "\n\n[dsession: context truncated at 65536 bytes]\n"
        text = "".join("line %05d\n" % n for n in range(7200))
        self.assertGreater(len(text.encode()), 70 * 1024)
        path = self.context(text)
        result = self.run_launcher("new", "--context", path, "--", "claude")
        call = self.only_call(result)
        self.assertEqual(self.lines(result.stderr), ["dsession: context %s truncated to 65536 bytes" % path])
        prompt = self.prompt_of(call["argv"])
        self.assertTrue(prompt.endswith(marker), prompt[-80:])
        kept = prompt[:-len(marker)]
        self.assertLessEqual(len(kept.encode()), 65536)
        self.assertTrue(text.startswith(kept + "\n"))
        os.remove(self.log)
        exact = "x" * 65535 + "\n"
        result = self.run_launcher("new", "--context", self.context(exact), "--", "claude")
        call = self.only_call(result)
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.prompt_of(call["argv"]), exact)

    def test_hermetic_context_launch_runs_one_fake(self):
        call = self.only_call(self.run_launcher("new", "--context", self.context("TASK\n"), "--", "claude"))
        self.assertEqual(call["exe"], os.path.join(self.bin, "claude"))
        self.assertEqual(call["env"]["HOME"], self.home)

    def test_non_adapter_client_with_context_is_a_usage_error(self):
        path = write(os.path.join(self.bin, "other"), FAKE.format(python=sys.executable))
        os.chmod(path, 0o755)
        line = "dsession: --context needs codex, claude or agy; " + ds.USAGE
        self.assert_one_line_exit(self.run_launcher("new", "--context", self.context("TASK\n"), "--", "other"), 2, line)
        self.assert_one_line_exit(self.run_launcher("new", "--context", os.path.join(self.tmp, "gone.md"), "--", "other"), 2, line)


class Wrapped(Case):
    WRAP = ["wrap", "agent", "run", "claude"]

    def setUp(self):
        super().setUp()
        path = write(os.path.join(self.bin, "wrap"), FAKE.format(python=sys.executable))
        os.chmod(path, 0o755)
        self.config = write_json(os.path.join(self.home, ".config", "dsession", "config.json"), {"wrappers": [self.WRAP]})

    def test_unlisted_wrapper_is_not_an_adapter(self):
        os.remove(self.config)
        line = "dsession: --context needs codex, claude or agy; " + ds.USAGE
        self.assert_one_line_exit(self.run_launcher("new", "--context", write(os.path.join(self.tmp, "c.md"), "TASK\n"), "--", *self.WRAP), 2, line)

    def test_malformed_config_warns_and_lists_no_wrapper(self):
        for value in ("{", '{"wrappers": [["wrap", "codex-ish"]]}', '{"wrappers": [["claude"]]}', '{"wrappers": "wrap"}'):
            with self.subTest(value=value):
                write(self.config, value)
                result = self.run_launcher("new", "--", *self.WRAP, "-p", "x")
                self.assertIn("dsession: ignoring unreadable " + self.config, result.stderr)
                self.assertEqual(self.calls()[-1]["argv"], ["agent", "run", "claude", "-p", "x"])

    def test_config_path_honours_absolute_xdg_config_home_only(self):
        config = os.path.join(self.tmp, "config")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
            self.assertEqual(ds.config_path(), os.path.join(config, "dsession", "config.json"))
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative"}):
            self.assertEqual(ds.config_path(), self.config)

    def test_zero_dirs_runs_the_wrapper_with_the_native_argv(self):
        call = self.only_call(self.run_launcher("resume", "abc", "--", *self.WRAP, "-p", "x"))
        self.assertEqual(call["name"], "wrap")
        self.assertEqual(call["argv"], ["agent", "run", "claude", "--resume", "abc", "-p", "x"])

    def test_dirs_and_context_build_claudes_argv_behind_the_wrapper(self):
        d = self.mkdir("d")
        write(os.path.join(d, "AGENTS.md"), "D-AGENTS\n")
        context = write(os.path.join(self.tmp, "c.md"), "TASK\n")
        call = self.only_call(self.run_launcher("new", "--dir", d, "--context", context, "--", *self.WRAP, "--session-id", "u"))
        argv = call["argv"]
        self.assertEqual(call["exe"], os.path.join(self.bin, "wrap"))
        self.assertEqual(argv[:5], ["agent", "run", "claude", "--add-dir", d])
        self.assertEqual(argv[argv.index("--append-system-prompt") + 1], "# Linked directory: %s/AGENTS.md\n\nD-AGENTS\n\nTASK\n" % d)
        self.assertEqual(argv[-2:], ["--session-id", "u"])
        self.assertEqual(call["env"]["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"], "1")

    def test_resume_with_context_merges_passthrough_settings(self):
        context = write(os.path.join(self.tmp, "c.md"), "TASK\n")
        call = self.only_call(self.run_launcher("resume", "abc", "--context", context, "--", *self.WRAP, "--settings", '{"a": 1}'))
        argv = call["argv"]
        self.assertEqual(argv[:5], ["agent", "run", "claude", "--resume", "abc"])
        self.assertEqual(argv.count("--settings"), 1, argv)
        self.assertIn("--append-system-prompt", argv)

    def test_other_wrapper_argv_is_not_an_adapter(self):
        context = write(os.path.join(self.tmp, "c.md"), "TASK\n")
        line = "dsession: --context needs codex, claude or agy; " + ds.USAGE
        for args in (["wrap", "agent", "run", "codex"], ["wrap", "claude"]):
            with self.subTest(args=args):
                self.assert_one_line_exit(self.run_launcher("new", "--context", context, "--", *args), 2, line)

    def test_missing_wrapper_exits_127(self):
        os.remove(os.path.join(self.bin, "wrap"))
        result = self.run_launcher("new", "--", *self.WRAP)
        self.assert_one_line_exit(result, 127, "dsession: wrap not found on PATH")


class ExitCodes(Case):
    def test_base_that_is_not_a_directory_exits_1(self):
        d = self.mkdir("d")
        base = write(os.path.join(self.tmp, "codex-file"))
        result = self.run_launcher("new", "--dir", d, "--", "codex", env={"CODEX_HOME": base})
        self.assert_one_line_exit(result, 1, "dsession: %s is not a directory" % base)

    def test_overlay_oserror_exits_1_for_both_adapters(self):
        d = self.mkdir("d")
        root = os.path.join(write(os.path.join(self.tmp, "plain")), "root")
        for client in ("codex", "claude"):
            with self.subTest(client=client):
                result = self.run_launcher("new", "--dir", d, "--", client, env={"DSESSION_ROOT": root})
                self.assertEqual(result.returncode, 1, result.stderr)
                lines = self.lines(result.stderr)
                self.assertEqual(len(lines), 1, result.stderr)
                self.assertTrue(lines[0].startswith("dsession: overlay failed: "), lines[0])
                self.assertEqual(self.calls(), [])

    def test_non_adapter_client_usage_errors_in_main(self):
        path = write(os.path.join(self.bin, "other"), FAKE.format(python=sys.executable))
        os.chmod(path, 0o755)
        d = self.mkdir("d")
        cases = (
            (["resume", "abc", "--", "other"], "dsession: resume needs codex, claude or agy; " + ds.USAGE),
            (["new", "--dir", d, "--", "other"], "dsession: linked directories need codex, claude or agy; " + ds.USAGE),
        )
        for args, line in cases:
            with self.subTest(args=args):
                self.assert_one_line_exit(self.run_launcher(*args), 2, line)

    def test_trust_grammar_errors(self):
        for args in (["trust", "--", "claude"], ["trust", "x"], ["trust", "--dir"]):
            with self.subTest(args=args):
                result = self.run_launcher(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(len(self.lines(result.stderr)), 1, result.stderr)


class ClaudeSettingsSources(Case):
    def test_unreadable_or_non_dict_linked_settings_warn_and_are_skipped(self):
        cases = [("bad-json", "{not json"), ("non-dict", "[1]"), ("bad-hooks", '{"hooks": {"Stop": 1}}')]
        if os.getuid() != 0:
            cases.append(("no-permission", None))
        for name, text in cases:
            with self.subTest(case=name):
                d = self.mkdir(name)
                path = os.path.join(d, ".claude", "settings.json")
                if text is None:
                    write_json(path, {"hooks": {"Stop": [hook_group("x")]}})
                    os.chmod(path, 0)
                else:
                    write(path, text)
                result = self.run_launcher("new", "--dir", d, "--", "claude")
                call = self.only_call(result)
                self.assertEqual(self.lines(result.stderr), ["dsession: skipping unreadable " + path])
                self.assertEqual(call["argv"], ["--add-dir", d])
                os.remove(self.log)

    def test_settings_without_hooks_add_nothing_and_do_not_warn(self):
        d = self.mkdir("d")
        write_json(os.path.join(d, ".claude", "settings.json"), {"permissions": {"deny": ["Bash(rm:*)"]}})
        result = self.run_launcher("new", "--dir", d, "--", "claude")
        call = self.only_call(result)
        self.assertEqual(result.stderr, "")
        self.assertEqual(call["argv"], ["--add-dir", d])

    def test_claude_skill_warnings_see_the_global_claude_skills(self):
        d = self.mkdir("d")
        later = skill(os.path.join(d, ".claude", "skills"), "s")
        home_skill = skill(os.path.join(self.home, ".claude", "skills"), "s")
        config = self.mkdir("config")
        config_skill = skill(os.path.join(config, "skills"), "s")
        for env, owner in (({}, home_skill), ({"CLAUDE_CONFIG_DIR": config}, config_skill)):
            with self.subTest(env=env):
                result = self.run_launcher("new", "--dir", d, "--", "claude", env=env)
                self.only_call(result)
                self.assertEqual(self.lines(result.stderr), ["dsession: skill s from %s dropped: already provided by %s" % (later, owner)])
                os.remove(self.log)


class ClaudeTrust(Case):
    def linked(self, name="d", hooks=None):
        d = self.mkdir(name)
        hooks = hooks or {"SessionStart": [hook_group(name + "-start")]}
        write_json(os.path.join(d, ".claude", "settings.json"), {"hooks": hooks, "permissions": {}})
        return d, hooks

    def digest(self, hooks):
        return hashlib.sha256(json.dumps(hooks, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def untrusted_line(self, d):
        return "dsession: skipping untrusted Claude hooks in %s (run: dsession trust --dir %s)" % (d, d)

    def test_untrusted_hooks_are_skipped_and_the_launch_is_otherwise_unchanged(self):
        d, _ = self.linked()
        write(os.path.join(d, "AGENTS.md"), "D-AGENTS\n")
        result = self.run_launcher("new", "--dir", d, "--", "claude", "-p", "hi")
        call = self.only_call(result)
        self.assertEqual(self.lines(result.stderr), [self.untrusted_line(d)])
        argv = call["argv"]
        self.assertEqual(argv[:2], ["--add-dir", d])
        self.assertNotIn("--settings", argv)
        self.assertEqual(argv[2], "--append-system-prompt")
        self.assertEqual(argv[-2:], ["-p", "hi"])
        self.assertEqual(call["env"]["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"], "1")
        self.assertFalse(os.path.exists(self.state_file()))

    def test_trust_prompts_records_the_hash_and_the_hooks_are_included(self):
        d, hooks = self.linked()
        code, out, err = self.trust(d)
        self.assertEqual(code, 0)
        self.assertIn("Claude hooks in %s:\n%s\n" % (d, json.dumps(hooks, indent=2, sort_keys=True)), out)
        self.assertIn("Trust these hooks? [y/N] ", out)
        self.assertEqual(self.lines(err), ["dsession: trusted Claude hooks in " + d])
        with open(self.state_file()) as f:
            self.assertEqual(json.load(f), {d: self.digest(hooks)})
        self.assertEqual(mode(self.state_file()), 0o600)
        result = self.run_launcher("new", "--dir", d, "--", "claude")
        call = self.only_call(result)
        self.assertEqual(result.stderr, "")
        path = call["argv"][call["argv"].index("--settings") + 1]
        with open(path) as f:
            self.assertEqual(json.load(f), {"hooks": hooks})

    def test_changed_hooks_are_skipped_again_until_retrusted(self):
        d, _ = self.linked()
        self.trust(d)
        changed = {"SessionStart": [hook_group("evil")]}
        write_json(os.path.join(d, ".claude", "settings.json"), {"hooks": changed})
        result = self.run_launcher("new", "--dir", d, "--", "claude")
        call = self.only_call(result)
        self.assertEqual(self.lines(result.stderr), [self.untrusted_line(d)])
        self.assertNotIn("--settings", call["argv"])
        code, out, err = self.trust(d)
        self.assertIn("Trust these hooks? [y/N] ", out)
        with open(self.state_file()) as f:
            self.assertEqual(json.load(f), {d: self.digest(changed)})

    def test_trust_is_per_directory(self):
        a, ha = self.linked("a")
        b, _ = self.linked("b")
        self.trust(a)
        result = self.run_launcher("new", "--dir", a, "--dir", b, "--", "claude")
        call = self.only_call(result)
        self.assertEqual(self.lines(result.stderr), [self.untrusted_line(b)])
        with open(call["argv"][call["argv"].index("--settings") + 1]) as f:
            self.assertEqual(json.load(f)["hooks"], ha)

    def test_already_trusted_does_not_prompt(self):
        d, _ = self.linked()
        self.trust(d)
        code, out, err = self.trust(d)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(self.lines(err), ["dsession: Claude hooks in %s are already trusted" % d])

    def test_anything_but_y_declines(self):
        d, _ = self.linked()
        for answer in ("n\n", "\n", "yes\n", ""):
            with self.subTest(answer=answer):
                code, out, err = self.trust(d, answer=answer)
                self.assertEqual(code, 0)
                self.assertIn("dsession: left Claude hooks in %s untrusted" % d, self.lines(err))
                self.assertFalse(os.path.exists(self.state_file()))
        code, out, err = self.trust(d, answer="Y\n")
        self.assertTrue(os.path.exists(self.state_file()))

    def test_trust_declines_when_stdin_is_not_a_terminal(self):
        d, _ = self.linked()
        result = subprocess.run([sys.executable, LAUNCHER, "trust", "--dir", d], input="y\n", env=dict(os.environ), cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Trust these hooks? [y/N] ", result.stdout)
        self.assertEqual(self.lines(result.stderr), ["dsession: stdin is not a terminal; declining", "dsession: left Claude hooks in %s untrusted" % d])
        self.assertFalse(os.path.exists(self.state_file()))

    def test_trust_reads_dsession_dirs_and_skips_dirs_without_hooks(self):
        d, _ = self.linked()
        plain = self.mkdir("plain")
        write_json(os.path.join(plain, ".claude", "settings.json"), {"permissions": {}})
        result = subprocess.run([sys.executable, LAUNCHER, "trust"], input="", env=dict(os.environ, DSESSION_DIRS=json.dumps([plain, d])), cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Claude hooks in %s:" % d, result.stdout)
        self.assertNotIn(plain + ":", result.stdout)

    def test_state_path_honours_absolute_xdg_state_home_only(self):
        d, hooks = self.linked()
        state = os.path.join(self.tmp, "state")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": state}):
            self.assertEqual(ds.trust_path(), os.path.join(state, "dsession", "claude-hooks.json"))
            self.trust(d)
            self.assertTrue(os.path.isfile(os.path.join(state, "dsession", "claude-hooks.json")))
            self.assertEqual(mode(os.path.join(state, "dsession")), 0o700)
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "relative"}):
            self.assertEqual(ds.trust_path(), self.state_file())
        self.assertFalse(self.state_file().startswith(self.root + os.sep))

    def test_state_write_is_one_replace_in_the_same_directory_and_keeps_other_entries(self):
        d, hooks = self.linked()
        write_json(self.state_file(), {"/elsewhere": "abc"})
        real_replace = os.replace
        calls = []

        def spy(src, dst):
            calls.append((src, dst))
            real_replace(src, dst)

        with mock.patch.object(ds.os, "replace", spy):
            self.trust(d)
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(calls[0][1], self.state_file())
        self.assertEqual(os.path.dirname(calls[0][0]), os.path.dirname(self.state_file()))
        self.assertEqual(os.listdir(os.path.dirname(self.state_file())), ["claude-hooks.json"])
        with open(self.state_file()) as f:
            self.assertEqual(json.load(f), {"/elsewhere": "abc", d: self.digest(hooks)})

    def test_unreadable_state_trusts_nothing(self):
        d, _ = self.linked()
        write(self.state_file(), "{broken")
        result = self.run_launcher("new", "--dir", d, "--", "claude")
        call = self.only_call(result)
        self.assertEqual(self.lines(result.stderr), ["dsession: ignoring unreadable " + self.state_file(), self.untrusted_line(d)])
        self.assertNotIn("--settings", call["argv"])


class Hardening(Case):
    def refusal(self, path, label="overlay root"):
        return "dsession: refusing %s %s (symlink or not owned by you)" % (label, path)

    def test_symlinked_root_is_refused(self):
        d = self.mkdir("d")
        target = self.mkdir("target")
        link = os.path.join(self.tmp, "link-root")
        os.symlink(target, link)
        for client in ("codex", "claude"):
            with self.subTest(client=client):
                result = self.run_launcher("new", "--dir", d, "--", client, env={"DSESSION_ROOT": link})
                self.assert_one_line_exit(result, 1, self.refusal(link))
                self.assertEqual(os.listdir(target), [])

    def test_dangling_symlink_root_is_refused(self):
        d = self.mkdir("d")
        link = os.path.join(self.tmp, "dangling-root")
        os.symlink(os.path.join(self.tmp, "nowhere"), link)
        self.assert_one_line_exit(self.run_launcher("new", "--dir", d, "--", "codex", env={"DSESSION_ROOT": link}), 1, self.refusal(link))
        self.assertFalse(os.path.lexists(os.path.join(self.tmp, "nowhere")))

    def test_symlinked_list_and_codex_directories_are_refused(self):
        d = self.mkdir("d")
        target = self.mkdir("target")
        hashed = os.path.join(self.root, self.expected_hash([d]))
        os.symlink(target, hashed)
        self.assert_one_line_exit(self.run_launcher("new", "--dir", d, "--", "codex"), 1, self.refusal(hashed, "overlay directory"))
        os.unlink(hashed)
        os.makedirs(hashed)
        codex_home = os.path.join(hashed, "codex")
        os.symlink(target, codex_home)
        self.assert_one_line_exit(self.run_launcher("new", "--dir", d, "--", "codex"), 1, self.refusal(codex_home, "overlay directory"))
        self.assertEqual(os.listdir(target), [])

    def test_root_owned_by_someone_else_is_refused(self):
        d = self.mkdir("d")
        err = io.StringIO()
        with mock.patch.object(ds.os, "getuid", return_value=os.getuid() + 1), contextlib.redirect_stderr(err):
            code = ds.main(["new", "--dir", d, "--", "codex"])
        self.assertEqual(code, 1)
        self.assertEqual(self.lines(err.getvalue()), [self.refusal(self.root)])
        self.assertEqual(os.listdir(self.root), [])
        foreign = [p for p in ("/usr", "/bin", "/") if not os.path.islink(p) and os.lstat(p).st_uid != os.getuid()]
        if foreign:
            result = self.run_launcher("new", "--dir", d, "--", "codex", env={"DSESSION_ROOT": foreign[0]})
            self.assert_one_line_exit(result, 1, self.refusal(foreign[0]))

    def test_directories_are_0700_files_0600_and_the_client_umask_is_untouched(self):
        os.chmod(self.root, 0o755)
        d = self.mkdir("d")
        write_json(os.path.join(d, ".claude", "settings.json"), {"hooks": {"Stop": [hook_group("x")]}})
        skill(os.path.join(d, ".agents", "skills"), "s")
        self.trust(d)
        calls = [self.only_call(self.run_launcher("new", "--dir", d, "--", "codex"))]
        os.remove(self.log)
        calls.append(self.only_call(self.run_launcher("new", "--dir", d, "--", "claude")))
        hashed = os.path.join(self.root, self.expected_hash([d]))
        codex_home = os.path.join(hashed, "codex")
        skills = os.path.join(codex_home, os.readlink(os.path.join(codex_home, "skills")))
        for path in (self.root, hashed, codex_home, os.path.join(hashed, "claude"), skills):
            self.assertEqual(mode(path), 0o700, path)
        for path in (os.path.join(codex_home, "AGENTS.md"), os.path.join(codex_home, "hooks.json"), os.path.join(hashed, "dirs"), os.path.join(hashed, "lock"), os.path.join(hashed, "claude", "settings.json")):
            self.assertEqual(mode(path), 0o600, path)
        for call in calls:
            self.assertEqual(call["umask"], current_umask())

    def test_planted_tmp_symlink_is_not_followed(self):
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        victim = write(os.path.join(self.tmp, "victim"), "keep\n")
        hashed = os.path.dirname(home)
        for path in (os.path.join(home, "AGENTS.md.tmp"), os.path.join(hashed, "dirs.tmp")):
            os.symlink(victim, path)
        self.regenerate([d])
        with open(victim) as f:
            self.assertEqual(f.read(), "keep\n")


class Override(Case):
    def test_base_agents_override_is_never_linked_and_warns(self):
        write(os.path.join(self.base, "AGENTS.md"), "global\n")
        override = write(os.path.join(self.base, "AGENTS.override.md"), "override\n")
        d = self.mkdir("d")
        home, err = self.regenerate([d])
        self.assertFalse(os.path.lexists(os.path.join(home, "AGENTS.override.md")))
        self.assertEqual(self.lines(err), ["dsession: ignoring %s so the composed AGENTS.md applies" % override])
        os.symlink(override, os.path.join(home, "AGENTS.override.md"))
        home, _ = self.regenerate([d])
        self.assertFalse(os.path.lexists(os.path.join(home, "AGENTS.override.md")))
        self.assertTrue(os.path.isfile(override))


class SkillsSwap(Case):
    def versions(self, home):
        return sorted(n for n in os.listdir(home) if n.startswith("skills."))

    def test_skills_is_a_symlink_to_a_versioned_directory_and_old_versions_go(self):
        g = skill(os.path.join(self.base, "skills"), "g")
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        live = os.path.join(home, "skills")
        first = os.readlink(live)
        self.assertRegex(first, r"^skills\.[^/]+$")
        self.assertEqual(self.versions(home), [first])
        self.assertEqual(os.listdir(live), ["g"])
        home, _ = self.regenerate([d])
        second = os.readlink(live)
        self.assertNotEqual(first, second)
        self.assertEqual(self.versions(home), sorted([first, second]))
        home, _ = self.regenerate([d])
        third = os.readlink(live)
        self.assertFalse(os.path.lexists(os.path.join(home, first)))
        self.assertEqual(self.versions(home), sorted([second, third]))
        self.assertEqual(os.readlink(os.path.join(live, "g")), g)
        self.assertFalse(any(n.startswith("skills.") for n in os.listdir(self.base)))

    def test_old_layout_and_stale_scratch_are_migrated_quietly(self):
        d = self.mkdir("d")
        skill(os.path.join(d, ".agents", "skills"), "s")
        _, codex_home, _ = ds.overlay_paths(self.base, [d])
        os.makedirs(os.path.join(codex_home, "skills"))
        os.symlink("/nowhere", os.path.join(codex_home, "skills", "old"))
        os.makedirs(os.path.join(codex_home, "skills.tmp"))
        os.symlink("/nowhere", os.path.join(codex_home, "skills.old"))
        write(os.path.join(codex_home, "skills.crashed", "x"))
        home, err = self.regenerate([d])
        self.assertEqual(err, "")
        live = os.path.join(home, "skills")
        self.assertTrue(os.path.islink(live))
        self.assertEqual(os.listdir(live), ["s"])
        self.assertEqual(self.versions(home), [os.readlink(live)])

    def test_skills_stays_a_directory_while_regenerating(self):
        skill(os.path.join(self.base, "skills"), "g")
        d = self.mkdir("d")
        home, _ = self.regenerate([d])
        live = os.path.join(home, "skills")
        stop = threading.Event()
        misses = []

        def watch():
            while not stop.is_set():
                try:
                    if not os.listdir(live):
                        misses.append("empty")
                except OSError as exc:
                    if not (sys.platform == "darwin" and exc.errno == errno.EINVAL):
                        misses.append(exc.strerror)

        watcher = threading.Thread(target=watch)
        watcher.start()
        try:
            for _ in range(100):
                self.regenerate([d])
        finally:
            stop.set()
            watcher.join()
        self.assertEqual(misses, [])
        self.assertEqual(len(self.versions(home)), 2)


class CodexAgents(Case):
    def setUp(self):
        super().setUp()
        self.render_log = os.path.join(self.tmp, "render.log")
        os.environ["FAKE_RENDER_LOG"] = self.render_log
        self.addCleanup(os.environ.pop, "FAKE_RENDER_LOG", None)
        self.base_agents = os.path.join(self.base, "agents")
        self.global_agent = write(os.path.join(self.base_agents, "g.toml"), "global\n")

    def install_renderer(self):
        path = write(os.path.join(self.bin, "codex-agent-toml"), RENDERER.format(python=sys.executable))
        os.chmod(path, 0o755)

    def renders(self):
        if not os.path.exists(self.render_log):
            return []
        with open(self.render_log) as f:
            return [json.loads(line) for line in f if line.strip()]

    def project(self, name, *agents):
        d = self.mkdir(name)
        for agent in agents:
            write(os.path.join(d, ".claude", "agents", agent + ".md"), "---\nname: %s\n---\n" % agent)
        return d

    def versions(self, home):
        return sorted(n for n in os.listdir(home) if n.startswith("agents."))

    def test_without_linked_agents_it_links_the_base_folder(self):
        self.install_renderer()
        home, err = self.regenerate([self.mkdir("d")])
        self.assertEqual(err, "")
        self.assertEqual(os.readlink(os.path.join(home, "agents")), self.base_agents)
        self.assertEqual(self.versions(home), [])
        self.assertEqual(self.renders(), [])

    def test_without_a_base_folder_or_linked_agents_there_is_none(self):
        os.remove(self.global_agent)
        os.rmdir(self.base_agents)
        home, err = self.regenerate([self.mkdir("d")])
        self.assertEqual(err, "")
        self.assertFalse(os.path.lexists(os.path.join(home, "agents")))

    def test_linked_agents_render_beside_the_global_ones(self):
        self.install_renderer()
        d = self.project("d", "x")
        home, err = self.regenerate([d])
        self.assertEqual(err, "")
        live = os.path.join(home, "agents")
        self.assertRegex(os.readlink(live), r"^agents\.[^/]+$")
        self.assertEqual(sorted(os.listdir(live)), ["g.toml", "x.md"])
        self.assertEqual(os.readlink(os.path.join(live, "g.toml")), self.global_agent)
        self.assertFalse(os.path.islink(os.path.join(live, "x.md")))
        [render] = self.renders()
        self.assertEqual(render[1:], [os.path.join(d, ".claude", "agents", "x.md")])
        self.assertEqual(self.versions(home), [os.readlink(live)])
        self.assertEqual(os.listdir(self.base_agents), ["g.toml"])

    def test_a_linked_agents_folder_is_followed(self):
        self.install_renderer()
        d = self.mkdir("d")
        write(os.path.join(d, ".ai", "agents", "x.md"), "---\nname: x\n---\n")
        os.makedirs(os.path.join(d, ".claude"))
        os.symlink(os.path.join("..", ".ai", "agents"), os.path.join(d, ".claude", "agents"))
        home, _ = self.regenerate([d])
        self.assertEqual(sorted(os.listdir(os.path.join(home, "agents"))), ["g.toml", "x.md"])

    def test_global_agent_wins_and_the_linked_one_is_dropped(self):
        self.install_renderer()
        d = self.project("d", "g")
        home, err = self.regenerate([d])
        path = os.path.join(d, ".claude", "agents", "g.md")
        self.assertEqual(self.lines(err), ["dsession: agent g from %s dropped: already provided by %s" % (path, self.global_agent)])
        self.assertEqual(os.readlink(os.path.join(home, "agents")), self.base_agents)
        self.assertEqual(self.renders(), [])

    def test_first_linked_directory_wins(self):
        self.install_renderer()
        a = self.project("a", "x")
        b = self.project("b", "x")
        _, err = self.regenerate([a, b])
        first = os.path.join(a, ".claude", "agents", "x.md")
        second = os.path.join(b, ".claude", "agents", "x.md")
        self.assertEqual(self.lines(err), ["dsession: agent x from %s dropped: already provided by %s" % (second, first)])
        self.assertEqual([r[1:] for r in self.renders()], [[first]])

    def test_missing_renderer_warns_and_keeps_the_base_link(self):
        home, err = self.regenerate([self.project("d", "x")])
        self.assertEqual(self.lines(err), ["dsession: codex-agent-toml not on PATH; the linked directories' Claude agents are not loaded"])
        self.assertEqual(os.readlink(os.path.join(home, "agents")), self.base_agents)

    def test_renderer_failure_warns_and_publishes_what_rendered(self):
        self.install_renderer()
        home, err = self.regenerate_with({"FAKE_RENDER_EXIT": "1"}, [self.project("d", "x")])
        self.assertEqual(self.lines(err), ["dsession: some linked agents were not rendered for Codex"])
        self.assertEqual(sorted(os.listdir(os.path.join(home, "agents"))), ["g.toml", "x.md"])

    def test_a_rendered_name_clash_never_writes_through_a_link(self):
        self.install_renderer()
        clash = write(os.path.join(self.base_agents, "x.md"), "base\n")
        home, err = self.regenerate([self.project("d", "x")])
        self.assertEqual(self.lines(err), ["dsession: rendered agent x.md dropped: already provided by " + clash])
        self.assertEqual(read(clash), "base\n")
        self.assertEqual(os.readlink(os.path.join(home, "agents", "x.md")), clash)
        self.assertEqual(self.versions(home), [os.readlink(os.path.join(home, "agents"))])

    def test_switching_between_rendered_and_base_layouts(self):
        self.install_renderer()
        d = self.project("d", "x")
        home, _ = self.regenerate([d])
        rendered = os.readlink(os.path.join(home, "agents"))
        os.remove(os.path.join(d, ".claude", "agents", "x.md"))
        home, _ = self.regenerate([d])
        self.assertEqual(os.readlink(os.path.join(home, "agents")), self.base_agents)
        self.assertEqual(self.versions(home), [rendered])
        home, _ = self.regenerate([d])
        self.assertEqual(self.versions(home), [])
        write(os.path.join(d, ".claude", "agents", "y.md"), "---\nname: y\n---\n")
        home, _ = self.regenerate([d])
        self.assertEqual(sorted(os.listdir(os.path.join(home, "agents"))), ["g.toml", "y.md"])
        self.assertEqual(os.listdir(self.base_agents), ["g.toml"])

    def test_launch_hands_codex_the_rendered_agents(self):
        self.install_renderer()
        d = self.project("d", "x")
        call = self.only_call(self.run_launcher("new", "--dir", d, "--", "codex"))
        agents = os.path.join(call["env"]["CODEX_HOME"], "agents")
        self.assertEqual(sorted(os.listdir(agents)), ["g.toml", "x.md"])

    def regenerate_with(self, env, dirs):
        with mock.patch.dict(os.environ, env):
            return self.regenerate(dirs)


class HookTrustSeed(Case):
    G0 = {"hooks": [{"type": "command", "command": "/global/start"}]}
    G1 = {"matcher": "resume", "hooks": [{"type": "command", "command": "/global/a"}, {"type": "command", "command": "/global/b"}]}
    S0 = {"hooks": [{"type": "command", "command": "/global/stop"}]}
    PREFIX = "# mine\nmodel = 'x'   \n\n[hooks.state]\n"

    def fixture(self, entries, prefix=None):
        write_json(os.path.join(self.base, "hooks.json"), {"hooks": {"SessionStart": [self.G0, self.G1], "Stop": [self.S0]}})
        text = (self.PREFIX if prefix is None else prefix) + "".join("[hooks.state.%s]\ntrusted_hash = %s\n" % (json.dumps(k), json.dumps(v)) for k, v in entries.items())
        self.config = write(os.path.join(self.tmp, "store", "config.toml"), text)
        os.chmod(self.config, 0o640)
        os.symlink(self.config, os.path.join(self.base, "config.toml"))
        with open(self.config, "rb") as f:
            return f.read()

    def base_key(self, suffix):
        return os.path.join(os.path.realpath(self.base), "hooks.json") + ":" + suffix

    def config_bytes(self):
        with open(self.config, "rb") as f:
            return f.read()

    def state(self):
        return tomllib.loads(self.config_bytes().decode())["hooks"]["state"]

    def seeded_line(self, n, home):
        return "dsession: seeded trust for %d global hooks into %s" % (n, home)

    def test_trusted_global_hooks_are_seeded_under_the_overlay_key_with_the_same_hash(self):
        original = self.fixture({
            self.base_key("session_start:0:0"): "h-s00",
            self.base_key("session_start:1:1"): "h-s11",
            self.base_key("stop:0:0"): "h-st",
        })
        d = self.mkdir("d")
        write_json(os.path.join(d, ".codex", "hooks.json"), {"hooks": {"SessionStart": [hook_group("d-start")]}})
        result = self.run_launcher("new", "--dir", d, "--", "codex")
        home = self.expected_codex_home([d])
        self.assertEqual(self.lines(result.stderr), [self.seeded_line(3, home)])
        call = self.only_call(result)
        self.assertEqual(call["env"]["CODEX_HOME"], home)
        state = self.state()
        overlay = os.path.join(home, "hooks.json") + ":"
        self.assertEqual(state[overlay + "session_start:0:0"], {"trusted_hash": "h-s00"})
        self.assertEqual(state[overlay + "session_start:1:1"], {"trusted_hash": "h-s11"})
        self.assertEqual(state[overlay + "stop:0:0"], {"trusted_hash": "h-st"})
        self.assertEqual(len(state), 6)
        self.assertEqual(mode(self.config), 0o640)
        self.assertTrue(os.path.islink(os.path.join(self.base, "config.toml")))
        self.assertTrue(self.config_bytes().startswith(original))

    def test_a_hook_without_a_base_entry_is_not_seeded(self):
        self.fixture({self.base_key("session_start:1:1"): "h-s11"})
        d = self.mkdir("d")
        home, err = self.regenerate([d])
        self.assertEqual(self.lines(err), [self.seeded_line(1, home)])
        overlay = os.path.join(home, "hooks.json") + ":"
        self.assertEqual(sorted(k for k in self.state() if k.startswith(overlay)), [overlay + "session_start:1:1"])

    def test_linked_dir_hooks_are_never_seeded(self):
        d = self.mkdir("d")
        linked_hooks = os.path.join(d, ".codex", "hooks.json")
        write_json(linked_hooks, {"hooks": {"SessionStart": [hook_group("d-start")], "Stop": [hook_group("d-stop")]}})
        original = self.fixture({
            self.base_key("session_start:2:0"): "stale-base-group",
            self.base_key("stop:1:0"): "stale-base-stop",
            linked_hooks + ":session_start:0:0": "linked",
        })
        home, err = self.regenerate([d])
        self.assertEqual(err, "")
        self.assertEqual(self.config_bytes(), original)
        with open(os.path.join(home, "hooks.json")) as f:
            self.assertEqual(json.load(f)["hooks"]["SessionStart"][2], hook_group("d-start"))

    def test_a_second_regenerate_appends_nothing(self):
        self.fixture({self.base_key("session_start:0:0"): "h-s00", self.base_key("stop:0:0"): "h-st"})
        d = self.mkdir("d")
        home, err = self.regenerate([d])
        self.assertEqual(self.lines(err), [self.seeded_line(2, home)])
        once = self.config_bytes()
        home, err = self.regenerate([d])
        self.assertEqual(err, "")
        self.assertEqual(self.config_bytes(), once)

    def test_the_append_keeps_existing_bytes_even_without_a_final_newline(self):
        prefix = "# odd   spacing\r\nmodel='x'\n[hooks.state]\n[hooks.state.\"/elsewhere:stop:0:0\"]\ntrusted_hash = \"z\"\n[hooks.state.%s]\ntrusted_hash = \"h\" # tail" % json.dumps(self.base_key("stop:0:0"))
        original = self.fixture({}, prefix=prefix)
        self.assertFalse(original.endswith(b"\n"))
        home, err = self.regenerate([self.mkdir("d")])
        self.assertEqual(self.lines(err), [self.seeded_line(1, home)])
        after = self.config_bytes()
        self.assertEqual(after[:len(original)], original)
        self.assertEqual(after[len(original):], ("\n[hooks.state.%s]\ntrusted_hash = \"h\"\n" % json.dumps(os.path.join(home, "hooks.json") + ":stop:0:0")).encode())
        self.assertEqual(self.state()[os.path.join(home, "hooks.json") + ":stop:0:0"], {"trusted_hash": "h"})

    def test_keys_with_quotes_and_backslashes_are_escaped(self):
        weird = os.path.join(self.tmp, 'ro"ot\\x')
        os.makedirs(weird)
        os.environ["DSESSION_ROOT"] = weird
        self.fixture({self.base_key("stop:0:0"): 'h"\\'})
        home, err = self.regenerate([self.mkdir("d")])
        self.assertIn('"', home)
        self.assertIn("\\", home)
        self.assertEqual(self.lines(err), [self.seeded_line(1, home)])
        self.assertEqual(self.state()[os.path.join(home, "hooks.json") + ":stop:0:0"], {"trusted_hash": 'h"\\'})

    def test_the_append_holds_the_root_wide_trust_lock(self):
        self.fixture({self.base_key("stop:0:0"): "h-st"})
        held = []
        real = ds.replace_bytes

        def probe(path, data, mode):
            fd = os.open(os.path.join(self.root, "hooks-trust.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held.append(False)
            except BlockingIOError:
                held.append(True)
            finally:
                os.close(fd)
            real(path, data, mode)
        with mock.patch.object(ds, "replace_bytes", probe):
            self.regenerate([self.mkdir("d")])
        self.assertEqual(held, [True])

    def test_an_unparseable_config_warns_and_the_launch_still_execs(self):
        write_json(os.path.join(self.base, "hooks.json"), {"hooks": {"Stop": [self.S0]}})
        config = write(os.path.join(self.base, "config.toml"), "not = = toml\n")
        d = self.mkdir("d")
        result = self.run_launcher("new", "--dir", d, "--", "codex")
        self.assertEqual(self.lines(result.stderr), ["dsession: not seeding hook trust (config.toml unreadable)"])
        self.only_call(result)
        with open(config) as f:
            self.assertEqual(f.read(), "not = = toml\n")

    def test_a_missing_config_warns_and_the_launch_still_execs(self):
        write_json(os.path.join(self.base, "hooks.json"), {"hooks": {"Stop": [self.S0]}})
        result = self.run_launcher("new", "--dir", self.mkdir("d"), "--", "codex")
        self.assertEqual(self.lines(result.stderr), ["dsession: not seeding hook trust (config.toml unreadable)"])
        self.only_call(result)

    def test_an_append_that_breaks_the_file_is_undone_and_exits_1(self):
        prefix = "hooks = { state = { %s = { trusted_hash = \"h\" } } }\n" % json.dumps(self.base_key("stop:0:0"))
        original = self.fixture({}, prefix=prefix)
        result = self.run_launcher("new", "--dir", self.mkdir("d"), "--", "codex")
        self.assert_one_line_exit(result, 1, "dsession: could not seed hook trust in " + self.config)
        self.assertEqual(self.config_bytes(), original)
        self.assertEqual(mode(self.config), 0o640)
        self.assertEqual([n for n in os.listdir(os.path.dirname(self.config)) if n != "config.toml"], [])


class Agy(Case):
    def setUp(self):
        super().setUp()
        self.render_log = os.path.join(self.tmp, "render.log")
        os.environ["FAKE_RENDER_LOG"] = self.render_log
        self.addCleanup(os.environ.pop, "FAKE_RENDER_LOG", None)

    def conversation(self, session_id="abc"):
        return write(os.path.join(self.home, ".gemini", "antigravity-cli", "conversations", session_id + ".db"), "")

    def install_renderer(self):
        path = write(os.path.join(self.bin, "agy-agent-md"), RENDERER.format(python=sys.executable))
        os.chmod(path, 0o755)

    def renders(self):
        if not os.path.exists(self.render_log):
            return []
        with open(self.render_log) as f:
            return [json.loads(line) for line in f if line.strip()]

    def project(self, name, *agents):
        d = self.mkdir(name)
        for agent in agents:
            write(os.path.join(d, ".claude", "agents", agent + ".md"), "---\nname: %s\n---\n" % agent)
        return d

    def agy_dir(self, dirs):
        return os.path.join(self.root, self.expected_hash(dirs), "agy")

    def agents_link(self, dirs):
        return os.path.join(self.agy_dir(dirs), ".agents", "agents")

    def versions(self, dirs):
        return sorted(n for n in os.listdir(self.agy_dir(dirs)) if n.startswith("agents."))

    def test_resume_of_a_missing_conversation_exits_1_without_exec(self):
        d = self.mkdir("d")
        ctx = write(os.path.join(self.tmp, "ctx"), "task\n")
        line = "dsession: agy conversation abc is not on this machine"
        for args in (["--"], ["--dir", d, "--"], ["--dir", d, "--context", ctx, "--"]):
            with self.subTest(args=args):
                self.assert_one_line_exit(self.run_launcher("resume", "abc", *args, "agy"), 1, line)
                self.assertFalse(os.path.exists(self.log))
                self.assertEqual(os.listdir(self.root), [])

    def test_resume_with_a_dangling_conversation_link_is_missing(self):
        path = self.conversation()
        os.remove(path)
        os.symlink(os.path.join(self.tmp, "gone.db"), path)
        result = self.run_launcher("resume", "abc", "--", "agy")
        self.assert_one_line_exit(result, 1, "dsession: agy conversation abc is not on this machine")
        self.assertFalse(os.path.exists(self.log))

    def test_new_does_not_need_a_conversation(self):
        call = self.only_call(self.run_launcher("new", "--", "agy", "-p", "x"))
        self.assertEqual(call["argv"], ["-p", "x"])

    def test_zero_dirs_execs_agy_untouched(self):
        call = self.only_call(self.run_launcher("new", "--", "agy", "-p", "hi"))
        self.assertEqual(call["argv"], ["-p", "hi"])
        self.assertEqual(os.listdir(self.root), [])

    def test_zero_dirs_resume_is_conversation(self):
        self.conversation()
        call = self.only_call(self.run_launcher("resume", "abc", "--", "agy", "-p", "x"))
        self.assertEqual(call["argv"], ["--conversation", "abc", "-p", "x"])
        self.assertEqual(os.listdir(self.root), [])

    def test_dirs_then_overlay_then_passthrough_in_that_order(self):
        self.install_renderer()
        a = self.project("a", "one")
        b = self.project("b", "two")
        self.conversation()
        call = self.only_call(self.run_launcher("resume", "abc", "--dir", a, "--dir", b, "--", "agy", "agents"))
        self.assertEqual(call["name"], "agy")
        self.assertEqual(call["argv"], ["--conversation", "abc", "--add-dir", a, "--add-dir", b, "--add-dir", os.path.realpath(self.agy_dir([a, b])), "agents"])
        [render] = self.renders()
        self.assertEqual(render[1:], [os.path.join(a, ".claude", "agents", "one.md"), os.path.join(b, ".claude", "agents", "two.md")])
        link = self.agents_link([a, b])
        self.assertRegex(os.readlink(link), r"^\.\./agents\.[^/]+$")
        self.assertEqual(sorted(os.listdir(link)), ["one.md", "two.md"])

    def test_no_claude_agents_passes_no_overlay_and_skips_the_renderer(self):
        self.install_renderer()
        d = self.mkdir("d")
        call = self.only_call(self.run_launcher("new", "--dir", d, "--", "agy"))
        self.assertEqual(call["argv"], ["--add-dir", d])
        self.assertEqual(self.renders(), [])
        self.assertFalse(os.path.lexists(self.agy_dir([d])))

    def test_native_agent_shadows_the_claude_one(self):
        self.install_renderer()
        d = self.project("d", "x", "y")
        native = write(os.path.join(d, ".agents", "agents", "x.md"), "native\n")
        result = self.run_launcher("new", "--dir", d, "--", "agy")
        self.assertEqual(self.only_call(result)["argv"][:2], ["--add-dir", d])
        self.assertEqual(self.lines(result.stderr), ["dsession: agent x from %s dropped: already provided by %s" % (os.path.join(d, ".claude", "agents", "x.md"), native)])
        self.assertEqual(os.listdir(self.agents_link([d])), ["y.md"])

    def test_same_file_link_shadows_silently(self):
        self.install_renderer()
        d = self.project("d", "x")
        os.makedirs(os.path.join(d, ".agents", "agents"))
        os.symlink(os.path.join(d, ".claude", "agents", "x.md"), os.path.join(d, ".agents", "agents", "x.md"))
        result = self.run_launcher("new", "--dir", d, "--", "agy")
        self.assertEqual(self.only_call(result)["argv"], ["--add-dir", d])
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.renders(), [])

    def test_a_name_in_two_dirs_renders_the_first_and_warns(self):
        self.install_renderer()
        a = self.project("a", "x")
        b = self.project("b", "x", "z")
        result = self.run_launcher("new", "--dir", a, "--dir", b, "--", "agy")
        self.only_call(result)
        first = os.path.join(a, ".claude", "agents", "x.md")
        second = os.path.join(b, ".claude", "agents", "x.md")
        self.assertEqual(self.lines(result.stderr), ["dsession: agent x from %s dropped: already provided by %s" % (second, first)])
        self.assertEqual(self.renders()[0][1:], [first, os.path.join(b, ".claude", "agents", "z.md")])

    def test_two_native_agents_of_one_name_warn(self):
        self.install_renderer()
        a = self.mkdir("a")
        b = self.mkdir("b")
        first = write(os.path.join(a, ".agents", "agents", "x.md"), "a\n")
        second = write(os.path.join(b, ".agents", "agents", "x.md"), "b\n")
        result = self.run_launcher("new", "--dir", a, "--dir", b, "--", "agy")
        self.only_call(result)
        self.assertEqual(self.lines(result.stderr), ["dsession: agent x in %s collides with %s; agy picks one" % (second, first)])
        self.assertEqual(self.renders(), [])

    def test_missing_renderer_warns_and_launches_without_the_overlay(self):
        d = self.project("d", "x")
        result = self.run_launcher("new", "--dir", d, "--", "agy")
        self.assertEqual(self.only_call(result)["argv"], ["--add-dir", d])
        self.assertEqual(self.lines(result.stderr), ["dsession: agy-agent-md not on PATH; the linked directories' Claude agents are not loaded"])

    def test_renderer_exit_1_warns_and_still_passes_the_overlay(self):
        self.install_renderer()
        d = self.project("d", "x")
        result = self.run_launcher("new", "--dir", d, "--", "agy", env={"FAKE_RENDER_EXIT": "1"})
        self.assertEqual(self.only_call(result)["argv"], ["--add-dir", d, "--add-dir", os.path.realpath(self.agy_dir([d]))])
        self.assertEqual(self.lines(result.stderr), ["dsession: some linked agents were not rendered for agy"])

    def test_renderer_that_renders_nothing_passes_no_overlay(self):
        self.install_renderer()
        d = self.project("d", "x")
        result = self.run_launcher("new", "--dir", d, "--", "agy", env={"FAKE_RENDER_NONE": "1"})
        self.assertEqual(self.only_call(result)["argv"], ["--add-dir", d])
        self.assertEqual(self.lines(result.stderr), ["dsession: some linked agents were not rendered for agy"])

    def test_overlay_argument_is_the_resolved_path(self):
        self.install_renderer()
        d = self.project("d", "x")
        real = self.mkdir("real-parent")
        link = os.path.join(self.tmp, "link-parent")
        os.symlink(real, link)
        result = self.run_launcher("new", "--dir", d, "--", "agy", env={"DSESSION_ROOT": os.path.join(link, "root")})
        argv = self.only_call(result)["argv"]
        unresolved = os.path.join(link, "root", self.expected_hash([d]), "agy")
        self.assertEqual(argv, ["--add-dir", d, "--add-dir", os.path.realpath(unresolved)])
        self.assertNotEqual(argv[-1], unresolved)

    def test_relaunch_drops_a_deleted_source_and_keeps_two_versions(self):
        self.install_renderer()
        d = self.project("d", "x", "y")
        self.only_call(self.run_launcher("new", "--dir", d, "--", "agy"))
        link = self.agents_link([d])
        first = os.readlink(link)
        self.assertEqual(sorted(os.listdir(link)), ["x.md", "y.md"])
        os.remove(self.log)
        os.remove(os.path.join(d, ".claude", "agents", "y.md"))
        self.only_call(self.run_launcher("new", "--dir", d, "--", "agy"))
        second = os.readlink(link)
        self.assertNotEqual(first, second)
        self.assertEqual(os.listdir(link), ["x.md"])
        self.assertEqual(len(self.versions([d])), 2)
        for _ in range(2):
            os.remove(self.log)
            self.only_call(self.run_launcher("new", "--dir", d, "--", "agy"))
            self.assertEqual(len(self.versions([d])), 2)
        self.assertFalse(os.path.lexists(os.path.join(self.agy_dir([d]), os.path.basename(first))))

    def test_rendered_files_are_0600_and_directories_0700(self):
        self.install_renderer()
        d = self.project("d", "x")
        self.only_call(self.run_launcher("new", "--dir", d, "--", "agy"))
        agy = self.agy_dir([d])
        version = os.path.join(agy, self.versions([d])[0])
        for path in (agy, os.path.join(agy, ".agents"), version):
            self.assertEqual(mode(path), 0o700, path)
        self.assertEqual(mode(os.path.join(version, "x.md")), 0o600)

    def context_dir(self, dirs):
        return os.path.join(self.root, self.expected_hash(dirs), "agy-context")

    def context_folder(self, dirs, source):
        digest = hashlib.sha256(os.path.realpath(source).encode()).hexdigest()[:16]
        return os.path.join(self.context_dir(dirs), digest)

    def test_context_is_an_agents_md_folder_added_last(self):
        self.install_renderer()
        a = self.project("a", "one")
        ctx = write(os.path.join(self.tmp, "ctx"), "task\n")
        self.conversation()
        call = self.only_call(self.run_launcher("resume", "abc", "--dir", a, "--context", ctx, "--", "agy", "agents"))
        folder = self.context_folder([a], ctx)
        self.assertEqual(call["argv"], ["--conversation", "abc", "--add-dir", a, "--add-dir", os.path.realpath(self.agy_dir([a])), "--add-dir", os.path.realpath(folder), "agents"])
        self.assertEqual(read(os.path.join(folder, "AGENTS.md")), "task\n")

    def test_context_folder_modes(self):
        d = self.mkdir("d")
        ctx = write(os.path.join(self.tmp, "ctx"), "task\n")
        self.only_call(self.run_launcher("new", "--dir", d, "--context", ctx, "--", "agy"))
        folder = self.context_folder([d], ctx)
        self.assertEqual(mode(self.context_dir([d])), 0o700)
        self.assertEqual(mode(folder), 0o700)
        self.assertEqual(mode(os.path.join(folder, "AGENTS.md")), 0o600)

    def test_context_with_no_dirs_still_uses_the_overlay(self):
        ctx = write(os.path.join(self.tmp, "ctx"), "task\n")
        call = self.only_call(self.run_launcher("new", "--context", ctx, "--", "agy", "-p", "hi"))
        folder = self.context_folder([], ctx)
        self.assertEqual(call["argv"], ["--add-dir", os.path.realpath(folder), "-p", "hi"])
        self.assertEqual(read(os.path.join(folder, "AGENTS.md")), "task\n")

    def test_context_without_agents_passes_only_the_context_folder(self):
        self.install_renderer()
        d = self.mkdir("d")
        ctx = write(os.path.join(self.tmp, "ctx"), "task\n")
        call = self.only_call(self.run_launcher("new", "--dir", d, "--context", ctx, "--", "agy"))
        self.assertEqual(call["argv"], ["--add-dir", d, "--add-dir", os.path.realpath(self.context_folder([d], ctx))])

    def test_resume_with_context_rewrites_the_folder(self):
        d = self.mkdir("d")
        ctx = write(os.path.join(self.tmp, "ctx"), "one\n")
        self.only_call(self.run_launcher("new", "--dir", d, "--context", ctx, "--", "agy"))
        os.remove(self.log)
        write(ctx, "two\n")
        self.conversation()
        call = self.only_call(self.run_launcher("resume", "abc", "--dir", d, "--context", ctx, "--", "agy"))
        folder = self.context_folder([d], ctx)
        self.assertEqual(call["argv"], ["--conversation", "abc", "--add-dir", d, "--add-dir", os.path.realpath(folder)])
        self.assertEqual(read(os.path.join(folder, "AGENTS.md")), "two\n")

    def test_two_context_files_get_two_folders(self):
        d = self.mkdir("d")
        one = write(os.path.join(self.tmp, "one"), "1\n")
        two = write(os.path.join(self.tmp, "two"), "2\n")
        self.only_call(self.run_launcher("new", "--dir", d, "--context", one, "--", "agy"))
        os.remove(self.log)
        self.only_call(self.run_launcher("new", "--dir", d, "--context", two, "--", "agy"))
        self.assertEqual(len(os.listdir(self.context_dir([d]))), 2)
        self.assertEqual(read(os.path.join(self.context_folder([d], one), "AGENTS.md")), "1\n")
        self.assertEqual(read(os.path.join(self.context_folder([d], two), "AGENTS.md")), "2\n")

    def test_large_context_is_cut_at_24_kib(self):
        marker = "\n\n[dsession: context truncated at 24576 bytes]\n"
        text = "".join("line %05d\n" % n for n in range(3000))
        ctx = write(os.path.join(self.tmp, "ctx"), text)
        result = self.run_launcher("new", "--context", ctx, "--", "agy")
        self.only_call(result)
        self.assertEqual(self.lines(result.stderr), ["dsession: context %s truncated to 24576 bytes" % ctx])
        written = read(os.path.join(self.context_folder([], ctx), "AGENTS.md"))
        self.assertTrue(written.endswith(marker), written[-80:])
        self.assertLessEqual(len(written.encode()), 24576)
        self.assertGreater(len(written.encode()), 24576 - 100)
        kept = written[:-len(marker)]
        self.assertTrue(text.startswith(kept + "\n"))

    def test_blank_or_unreadable_context_adds_nothing(self):
        d = self.mkdir("d")
        blank = write(os.path.join(self.tmp, "blank"), " \n\t\n")
        missing = os.path.join(self.tmp, "gone")
        result = self.run_launcher("new", "--dir", d, "--context", blank, "--", "agy")
        self.assertEqual(self.only_call(result)["argv"], ["--add-dir", d])
        self.assertEqual(result.stderr, "")
        self.assertFalse(os.path.lexists(self.context_dir([d])))
        os.remove(self.log)
        result = self.run_launcher("new", "--dir", d, "--context", missing, "--", "agy")
        self.assertEqual(self.only_call(result)["argv"], ["--add-dir", d])
        self.assertEqual(self.lines(result.stderr), ["dsession: skipping unreadable context " + missing])
        self.assertFalse(os.path.lexists(self.context_dir([d])))

    def test_blank_context_with_no_dirs_execs_agy_untouched(self):
        blank = write(os.path.join(self.tmp, "blank"), "\n")
        call = self.only_call(self.run_launcher("new", "--context", blank, "--", "agy", "-p", "hi"))
        self.assertEqual(call["argv"], ["-p", "hi"])
        self.assertEqual(os.listdir(self.root), [])

    def test_claude_md_only_directory_warns(self):
        d = self.mkdir("d")
        write(os.path.join(d, "CLAUDE.md"), "rules\n")
        result = self.run_launcher("new", "--dir", d, "--", "agy")
        self.assertEqual(self.only_call(result)["argv"], ["--add-dir", d])
        self.assertEqual(self.lines(result.stderr), ["dsession: agy reads AGENTS.md, not CLAUDE.md, in " + d])

    def test_symlinked_overlay_root_is_refused(self):
        d = self.project("d", "x")
        target = self.mkdir("target")
        link = os.path.join(self.tmp, "link-root")
        os.symlink(target, link)
        result = self.run_launcher("new", "--dir", d, "--", "agy", env={"DSESSION_ROOT": link})
        self.assert_one_line_exit(result, 1, "dsession: refusing overlay root %s (symlink or not owned by you)" % link)
        self.assertEqual(os.listdir(target), [])


class Scratch(Case):
    def test_dirs_tmp_and_claude_settings_tmp_are_swept(self):
        d = self.mkdir("d")
        hashed = os.path.join(self.root, self.expected_hash([d]))
        write(os.path.join(hashed, "dirs.tmp"), "stale")
        self.only_call(self.run_launcher("new", "--dir", d, "--", "codex"))
        self.assertFalse(os.path.lexists(os.path.join(hashed, "dirs.tmp")))
        os.remove(self.log)
        write(os.path.join(hashed, "claude", "settings.json.tmp"), "stale")
        self.only_call(self.run_launcher("new", "--dir", d, "--", "claude"))
        self.assertFalse(os.path.lexists(os.path.join(hashed, "claude", "settings.json.tmp")))
        self.assertEqual(sorted(n for n in os.listdir(hashed) if re.search(r"\.tmp$", n)), [])


def main():
    global ds
    if LAUNCHER is None:
        sys.stderr.write("usage: test_dsession.py PATH/TO/dsession.py\n")
        return 2
    sys.dont_write_bytecode = True
    guard = os.path.realpath(tempfile.mkdtemp())
    os.environ["HOME"] = os.path.join(guard, "home")
    os.environ["DSESSION_ROOT"] = os.path.join(guard, "root")
    for key in ("CODEX_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
        os.environ.pop(key, None)
    ds = load_launcher(LAUNCHER)
    program = unittest.main(argv=[sys.argv[0], "-v"] + sys.argv[2:], exit=False)
    shutil.rmtree(guard, True)
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
