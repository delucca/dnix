import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

DM, RAW, BARE_PY = [os.path.abspath(a) for a in sys.argv[1:4]]
del sys.argv[1:]
sys.dont_write_bytecode = True

TMP = tempfile.mkdtemp(prefix="dm-test-")
HOSTILE = os.path.join(TMP, "hostile.gitconfig")
with open(HOSTILE, "w") as fh:
    fh.write(
        "[diff]\n\texternal = sh -c 'echo EXTERNAL'\n\tnoprefix = true\n\tmnemonicPrefix = true\n"
        "\talgorithm = histogram\n[color]\n\tui = always\n[core]\n\tquotePath = false\n"
        "[user]\n\tname = t\n\temail = t@example.com\n"
    )
GITONLY = os.path.join(TMP, "gitonly")
os.makedirs(GITONLY)
os.symlink(shutil.which("git"), os.path.join(GITONLY, "git"))
ENV = dict(
    os.environ, GIT_CONFIG_GLOBAL=HOSTILE, GIT_CONFIG_NOSYSTEM="1", HOME=TMP, PYTHONDONTWRITEBYTECODE="1",
)
ENV.pop("GIT_EXTERNAL_DIFF", None)
CLOCK = [1700000000]


def slurp(path, mode="rb"):
    with open(path, mode) as fh:
        return fh.read()


def run(args, cwd=None, inp=None, env=None, raw=False):
    p = subprocess.run(args, cwd=cwd, env=env or ENV, input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if raw:
        return p
    p.out, p.err = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    return p


def git(repo, *args, **kw):
    return run(["git", "-C", repo] + list(args), **kw)


def write(repo, rel, content="", mode=None):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content if isinstance(content, bytes) else content.encode("utf-8"))
    if mode:
        os.chmod(path, mode)


def commit(repo, msg="c"):
    CLOCK[0] += 60
    stamp = "%d +0000" % CLOCK[0]
    env = dict(ENV, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    git(repo, "add", "-A", env=env)
    p = git(repo, "commit", "-q", "-m", msg, env=env)
    assert p.returncode == 0, p.err
    return git(repo, "rev-parse", "HEAD").out.strip()


def make_repo(files=None):
    d = tempfile.mkdtemp(prefix="repo-", dir=TMP)
    git(d, "init", "-q", "-b", "main")
    for rel, content in (files or {"README.txt": "hi\n"}).items():
        write(d, rel, content)
    commit(d, "init")
    return d


def dm(*args, cwd=None, binary=None, env=None):
    return run([binary or DM] + list(args), cwd=cwd, env=env)


def measure(repo, mode="--worktree", base="HEAD", coverage=None, binary=None, env=None):
    out = os.path.join(TMP, "m-%d" % time.time_ns())
    os.makedirs(out)
    diff = dm("diff", "--repo", repo, "--base", base, *mode.split(), binary=binary, env=env)
    assert diff.returncode == 0, diff.err
    with open(os.path.join(out, "t.diff"), "wb") as fh:
        fh.write(diff.stdout)
    cmd = ["measure", "--repo", repo, "--diff", os.path.join(out, "t.diff"), "--out", os.path.join(out, "m.json"),
           "--base", base] + mode.split()
    if coverage:
        cmd += ["--coverage", coverage]
    p = dm(*cmd, binary=binary, env=env)
    assert p.returncode == 0, p.err
    with open(os.path.join(out, "m.json")) as fh:
        m = json.load(fh)
    m["_dir"] = out
    m["_stdout"] = p.out
    return m


def kinds(m, path=None):
    return sorted((g["kind"], g["file"]) for g in m["tripwires"] if path is None or g["file"] == path)


def degraded(*args, cwd=None):
    env = dict(ENV, PATH=GITONLY)
    return run([BARE_PY, "-I", RAW] + list(args), cwd=cwd, env=env)


class Case(unittest.TestCase):
    def repo(self, files=None):
        return make_repo(files)


class DiffVerb(Case):
    def test_worktree_has_tracked_and_untracked(self):
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 2\n"})
        write(r, "a.py", "x = 2\n")
        write(r, "new.py", "z = 3\n")
        a = dm("diff", "--repo", r, "--base", "HEAD", "--worktree")
        b = dm("diff", "--repo", r, "--base", "HEAD", "--worktree")
        self.assertEqual(a.returncode, 0, a.err)
        self.assertEqual(a.stdout, b.stdout)
        self.assertIn("diff --git a/a.py b/a.py", a.out)
        self.assertIn("new file mode", a.out)
        self.assertIn("+++ b/new.py", a.out)
        self.assertNotIn("EXTERNAL", a.out)
        self.assertNotIn("\x1b[", a.out)

    def test_index_only_staged(self):
        r = self.repo({"a.py": "x = 1\n", "b.py": "y = 2\n"})
        write(r, "a.py", "x = 2\n")
        write(r, "b.py", "y = 3\n")
        git(r, "add", "a.py")
        d = dm("diff", "--repo", r, "--base", "HEAD", "--index").out
        self.assertIn("a/a.py", d)
        self.assertNotIn("b.py", d)

    def test_head_range(self):
        r = self.repo({"a.py": "x = 1\n"})
        first = git(r, "rev-parse", "HEAD").out.strip()
        write(r, "a.py", "x = 2\n")
        commit(r)
        d = dm("diff", "--repo", r, "--base", first, "--head", "HEAD").out
        self.assertIn("+x = 2", d)

    def test_unknown_base_exits_2(self):
        r = self.repo()
        p = dm("diff", "--repo", r, "--base", "nope", "--worktree")
        self.assertEqual(p.returncode, 2)
        self.assertTrue(p.err.strip())

    def test_usage_error_exits_2(self):
        self.assertEqual(dm("diff").returncode, 2)

    def test_binary_diff_is_an_applicable_patch(self):
        r = self.repo({"keep.txt": "k\n", "gone.txt": "g\n", "old.txt": "".join("line %d\n" % i for i in range(30)),
                       "tool.sh": "echo hi\n", "bin.dat": b"\0\1\2base"})
        write(r, "tool.sh", "echo hi\n", mode=0o755)
        os.symlink("keep.txt", os.path.join(r, "link"))
        git(r, "add", "link")
        commit(r, "link")
        os.remove(os.path.join(r, "gone.txt"))
        git(r, "mv", "old.txt", "renamed.txt")
        write(r, "renamed.txt", "".join("line %d\n" % i for i in range(30)) + "extra\n")
        write(r, "bin.dat", b"\0\1\2changed\xff")
        write(r, "untracked.txt", "u\n")
        write(r, "untracked.bin", b"\0\0bin")
        os.remove(os.path.join(r, "link"))
        os.symlink("renamed.txt", os.path.join(r, "link"))
        patch = dm("diff", "--repo", r, "--base", "HEAD", "--worktree", "--binary")
        self.assertEqual(patch.returncode, 0, patch.err)
        clone = os.path.join(TMP, "clone-%d" % time.time_ns())
        self.assertEqual(run(["git", "clone", "-q", r, clone]).returncode, 0)
        pf = os.path.join(TMP, "p-%d.patch" % time.time_ns())
        with open(pf, "wb") as fh:
            fh.write(patch.stdout)
        ap = git(clone, "apply", "--binary", pf)
        self.assertEqual(ap.returncode, 0, ap.err)

        def state(root):
            out = {}
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [x for x in dirs if x != ".git"]
                for n in files:
                    full = os.path.join(dirpath, n)
                    rel = os.path.relpath(full, root)
                    if os.path.islink(full):
                        out[rel] = ("link", os.readlink(full))
                    else:
                        with open(full, "rb") as fh:
                            out[rel] = (hashlib.sha256(fh.read()).hexdigest(), os.access(full, os.X_OK))
            return out

        self.assertEqual(state(r), state(clone))


class Facts(Case):
    def test_exclusions_and_counts(self):
        r = self.repo({"src/a.py": "a = 1\n"})
        write(r, "src/a.py", "a = 1\nb = 2\nc = 3\n")
        write(r, "uv.lock", "x\ny\n")
        write(r, "vendor/lib.js", "var a;\n")
        write(r, "gen.py", "# Code generated by tool. DO NOT EDIT.\nx = 1\n")
        write(r, "blob.bin", b"\0\1\2")
        m = measure(r)["facts"]
        self.assertEqual(m["S"], 2)
        self.assertEqual(m["F"], 2)
        self.assertEqual(m["excluded"], ["gen.py", "uv.lock", "vendor/lib.js"])
        self.assertEqual(m["binary"], ["blob.bin"])

    def test_changed_lines_multi_hunk(self):
        body = "".join("line %d\n" % i for i in range(1, 41))
        r = self.repo({"f.py": body})
        lines = body.split("\n")
        lines[2] = "changed 3"
        lines[29:29] = ["ins a", "ins b"]
        write(r, "f.py", "\n".join(lines))
        self.assertEqual(measure(r)["facts"]["changed_lines"]["f.py"], [[3, 3], [30, 31]])

    def test_rename_and_mode_only(self):
        r = self.repo({"old.py": "".join("l%d\n" % i for i in range(20)), "x.sh": "echo\n"})
        git(r, "mv", "old.py", "new.py")
        write(r, "new.py", "".join("l%d\n" % i for i in range(20)) + "more\n")
        os.chmod(os.path.join(r, "x.sh"), 0o755)
        m = measure(r)["facts"]
        self.assertEqual(m["files"]["new.py"]["status"], "renamed")
        self.assertEqual(m["files"]["new.py"]["old_path"], "old.py")
        self.assertEqual(m["files"]["x.sh"]["added"] + m["files"]["x.sh"]["deleted"], 0)
        self.assertEqual(m["F"], 2)

    def test_hostile_path_names(self):
        names = ["sp ace.py", "tab\there.py", "new\nline.py", "café.py", 'quo"te.py']
        r = self.repo({"keep.py": "k = 1\n"})
        for n in names:
            write(r, n, "v = 1\nw = 2\n")
        m = measure(r)["facts"]
        for n in names:
            self.assertIn(n, m["files"], n)
            self.assertEqual(m["changed_lines"][n], [[1, 2]])
        git(r, "add", "-A")
        commit(r)
        for n in names:
            write(r, n, "v = 1\nw = 3\n")
        m = measure(r)["facts"]
        for n in names:
            self.assertIn(n, m["changed_lines"], n)

    def test_filter_lint(self):
        r = self.repo({"src/a.py": "".join("l%d\n" % i for i in range(1, 20)), "src/my file.py": "x\n" * 5})
        write(r, "src/a.py", "".join("l%d\n" % i for i in range(1, 11)) + "new 11\n" + "".join("l%d\n" % i for i in range(12, 20)))
        write(r, "src/my file.py", "x\nx\nchanged\nx\nx\n")
        m = measure(r)
        lint = (
            "src/a.py:11:1: E501 too long\n"
            "src/my file.py:3:1: E501 too long\n"
            "./src/a.py:12:1: E501 not changed\n"
            "%s/src/a.py:5:1: absolute, unchanged\n"
            "Found 3 errors\n" % r
        )
        p = run([DM, "filter-lint", "--metrics", os.path.join(m["_dir"], "m.json")], inp=lint.encode())
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.out.splitlines(), ["src/a.py:11:1: E501 too long", "src/my file.py:3:1: E501 too long"])
        self.assertEqual(p.err.strip().splitlines()[-1], "filter-lint: kept=2 located=4 unlocated=1")


FILES = {
    "py": ("tests/test_a.py", "def test_a():\n    assert 1 + 1 == 2\n\n\ndef test_b():\n    assert 2 == 2\n"),
    "ts": ("src/a.test.ts", "it('a', () => {\n  expect(1).toBe(1);\n});\n\nit('b', () => {\n  expect(2).toBe(2);\n});\n"),
    "go": ("a_test.go", "package a\n\nfunc TestA(t *testing.T) {\n\tif 1 != 1 {\n\t\tt.Errorf(\"x\")\n\t}\n}\n\nfunc TestB(t *testing.T) {\n\tt.Fatal(\"y\")\n}\n"),
    "rs": ("src/lib.rs", "#[test]\nfn a() {\n    assert_eq!(1, 1);\n}\n\n#[test]\nfn b() {\n    assert_eq!(2, 2);\n}\n"),
}


def tripwire_case(test, files_base, files_head):
    r = make_repo(files_base)
    for rel, content in files_head.items():
        if content is None:
            os.remove(os.path.join(r, rel))
        else:
            write(r, rel, content)
    return measure(r)


class Tripwires(Case):
    def check(self, files_base, files_head, expect, absent=()):
        m = tripwire_case(self, files_base, files_head)
        got = kinds(m)
        for e in expect:
            self.assertIn(e, got, got)
        for a in absent:
            self.assertNotIn(a, [k for k, _ in got], got)
        return m

    def test_python(self):
        p, base = FILES["py"]
        self.check({p: base}, {p: base.replace("def test_a():\n    assert 1 + 1 == 2\n\n\n", "")}, [("test-deleted", p)])
        self.check({p: base}, {p: "import pytest\n\n\n@pytest.mark.skip\n" + base}, [("test-skipped", p)])
        self.check({p: base}, {p: base.replace("    assert 2 == 2\n", "    pass\n")}, [("assertion-lost", p)])
        m = self.check({p: base}, {p: base + "\n\ndef test_new():\n    pass\n"}, [("test-no-assertion", p)])
        item = [g for g in m["tripwires"] if g["kind"] == "test-no-assertion"][0]["items"][0]
        self.assertEqual(item["line"], 9)
        self.check({"src/m.py": "x = 1\n"}, {"src/m.py": "x = 1\ny = f()  # noqa\n"}, [("suppression", "src/m.py")])

    def test_python_negatives(self):
        p, base = FILES["py"]
        self.check({p: base}, {p: base + "\n\ndef test_new():\n    assert 3 == 3\n"}, [],
                   absent=("test-no-assertion",))
        edited = base.replace("def test_b():", "def test_b(self, x=1):")
        self.check({p: base}, {p: edited}, [], absent=("test-no-assertion", "test-deleted", "assertion-lost"))
        self.check({"notes.md": "x\n"}, {"notes.md": "x\nuse # noqa or @ts-ignore sparingly\n"}, [],
                   absent=("suppression",))
        self.check({"pyproject.toml": "[project]\nname = 'a'\nversion = '1.0.0'\n"},
                   {"pyproject.toml": "[project]\nname = 'a'\nversion = '1.0.1'\n"}, [], absent=("gate-loosened",))

    def test_python_rename_is_flagged(self):
        p, base = FILES["py"]
        m = self.check({p: base}, {p: base.replace("def test_a", "def test_renamed")}, [("test-deleted", p)])
        self.assertNotIn("test-no-assertion", [k for k, _ in kinds(m)])

    def test_deleted_test_file_is_one_item(self):
        p, base = FILES["py"]
        m = self.check({p: base}, {p: None}, [("test-deleted", p)])
        g = [g for g in m["tripwires"] if g["kind"] == "test-deleted"][0]
        self.assertEqual(len(g["items"]), 1)
        self.assertEqual((g["items"][0]["line"], g["items"][0]["base_line"]), (1, 1))

    def test_typescript(self):
        p, base = FILES["ts"]
        self.check({p: base}, {p: base.replace("it('b', () => {\n  expect(2).toBe(2);\n});\n", "")}, [("test-deleted", p)])
        self.check({p: base}, {p: base.replace("it('a'", "it.skip('a'")}, [("test-skipped", p)])
        self.check({p: base}, {p: base.replace("  expect(2).toBe(2);\n", "")}, [("assertion-lost", p)])
        self.check({p: base}, {p: base + "\nit('c', () => {\n  foo();\n});\n"}, [("test-no-assertion", p)])
        self.check({p: base}, {p: base + "\nit('c', () => {\n  expect(foo()).toBe(1);\n});\n"}, [],
                   absent=("test-no-assertion",))
        self.check({"src/a.ts": "let a = 1;\n"}, {"src/a.ts": "let a = 1;\n// @ts-ignore\nlet b: number = 'x';\n"},
                   [("suppression", "src/a.ts")])

    def test_go(self):
        p, base = FILES["go"]
        self.check({p: base}, {p: base.split("func TestB")[0]}, [("test-deleted", p)])
        self.check({p: base}, {p: base.replace("\tt.Fatal(\"y\")\n", "\tt.Skip(\"later\")\n")},
                   [("test-skipped", p), ("assertion-lost", p)])
        self.check({p: base}, {p: base + "\nfunc TestC(t *testing.T) {\n\tfoo()\n}\n"}, [("test-no-assertion", p)])
        self.check({"a.go": "package a\n"}, {"a.go": "package a\n//nolint:errcheck\nvar x = f()\n"}, [("suppression", "a.go")])

    def test_rust(self):
        p, base = FILES["rs"]
        self.check({p: base}, {p: base.split("#[test]\nfn b")[0]}, [("test-deleted", p)])
        self.check({p: base}, {p: base.replace("#[test]\nfn b", "#[test]\n#[ignore]\nfn b")}, [("test-skipped", p)])
        self.check({p: base}, {p: base.replace("    assert_eq!(2, 2);\n", "")}, [("assertion-lost", p)])
        self.check({p: base}, {p: base + "\n#[tokio::test]\nasync fn c() {\n    foo().await;\n}\n"},
                   [("test-no-assertion", p)])
        self.check({"src/m.rs": "fn a() {}\n"}, {"src/m.rs": "#[allow(dead_code)]\nfn a() {}\n"},
                   [("suppression", "src/m.rs")])

    def test_kotlin(self):
        p = "src/FooTest.kt"
        base = "class FooTest {\n    @Test\n    fun a() {\n        assertEquals(1, 1)\n    }\n}\n"
        added = base[:-2] + "\n    @Test\n    suspend fun b() {\n        run()\n    }\n}\n"
        self.check({p: base}, {p: added}, [("test-no-assertion", p)])
        okay = base[:-2] + "\n    @Test\n    suspend fun b() {\n        assertEquals(2, 2)\n    }\n}\n"
        self.check({p: base}, {p: okay}, [], absent=("test-no-assertion",))

    def test_gate_loosened(self):
        self.check({"pyproject.toml": "[tool.coverage.report]\nfail_under = 90\n"},
                   {"pyproject.toml": "[tool.coverage.report]\nfail_under = 80\n"}, [("gate-loosened", "pyproject.toml")])
        self.check({".github/workflows/ci.yml": "steps:\n  - run: pytest\n  - run: ruff check\n"},
                   {".github/workflows/ci.yml": "steps:\n  - run: pytest\n"}, [("gate-loosened", ".github/workflows/ci.yml")])
        self.check({".eslintrc.json": "{\"rules\": {}}\n"}, {".eslintrc.json": "{\"rules\": {\"no-undef\": \"off\"}}\n"},
                   [("gate-loosened", ".eslintrc.json")])
        self.check({"pyproject.toml": "[tool.coverage.report]\nfail_under = 80\n"},
                   {"pyproject.toml": "[tool.coverage.report]\nfail_under = 90\n"}, [], absent=("gate-loosened",))

    def test_severity(self):
        p, base = FILES["py"]
        m = self.check({p: base}, {p: base.replace("    assert 2 == 2\n", "    x = 1  # noqa\n")},
                       [("assertion-lost", p), ("suppression", p)])
        sev = dict((g["kind"], g["severity"]) for g in m["tripwires"])
        self.assertEqual((sev["assertion-lost"], sev["suppression"]), ("major", "minor"))


class StringLiterals(Case):
    def test_matches_inside_literals_are_ignored(self):
        r = self.repo({"src/a.py": "x = 1\n", "src/b.ts": "let a = 1;\n", "src/c.rs": "fn a() {}\n",
                       "tests/test_a.py": "def test_a():\n    assert 1 == 1\n"})
        write(r, "src/a.py", 'x = 1\nPATS = ("# noqa", "# type: ignore")\nY = r"@Ignore\\b"\n')
        write(r, "src/b.ts", "let a = 1;\nconst s = `// @ts-ignore`;\nconst t = '@ts-nocheck';\n")
        write(r, "src/c.rs", 'fn a() {}\nconst S: &str = "#[allow(dead_code)]";\n')
        write(r, "tests/test_a.py", 'def test_a():\n    assert 1 == 1\n    assert "@pytest.mark.skip" in TEXT\n    s = "it.skip("\n')
        self.assertEqual(kinds(measure(r)), [])

    def test_real_directives_still_fire(self):
        r = self.repo({"src/a.py": "x = 1\n", "src/b.ts": "let a = 1;\n", "src/c.rs": "fn a() {}\n",
                       "tests/test_a.py": "def test_a():\n    assert 1 == 1\n", "tests/a.test.ts": "it('a', () => {});\n"})
        write(r, "src/a.py", 'x = 1\ny = "a#b"  # noqa\nz = f("it")  # type: ignore\n')
        write(r, "src/b.ts", "let a = 1;\nconst s = 'x'; // @ts-ignore\n")
        write(r, "src/c.rs", 'fn a() {}\n#[allow(dead_code)]\nfn b() {}\n')
        write(r, "tests/test_a.py", 'def test_a():\n    assert 1 == 1\n\n\n@pytest.mark.skip\ndef test_b():\n    assert "x"\n')
        write(r, "tests/a.test.ts", "it.skip('a', () => {});\n")
        got = kinds(measure(r))
        for e in (("suppression", "src/a.py"), ("suppression", "src/b.ts"), ("suppression", "src/c.rs"),
                  ("test-skipped", "tests/test_a.py"), ("test-skipped", "tests/a.test.ts")):
            self.assertIn(e, got)
        sup = [g for g in measure(r)["tripwires"] if g["kind"] == "suppression" and g["file"] == "src/a.py"][0]
        self.assertEqual([i["line"] for i in sup["items"]], [2, 3])


class Trivial(Case):
    def test_trivial_assertion_does_not_count(self):
        m = tripwire_case(self, {"tests/test_a.py": "def test_a():\n    assert 2 == 2\n"},
                          {"tests/test_a.py": "def test_a():\n    assert 2 == 2\n\n\ndef test_t():\n    assert True\n"})
        self.assertIn(("test-no-assertion", "tests/test_a.py"), kinds(m))


class DiffPointers(Case):
    def test_comments(self):
        r = self.repo({"a.py": "x = 1\n", "b.ts": "let a = 1;\n"})
        write(r, "a.py", "x = 1\n# loop over items\n# total = total + 1\n# noqa: E501\ny = 2\n#!/usr/bin/env python\n")
        write(r, "b.ts", "let a = 1;\n// explain why\n// const z = 3;\n// eslint-disable-next-line\nlet c = 2;\n")
        c = {(p["file"], p["text"]): p["kind"] for p in measure(r)["pointers"]["comments"]}
        self.assertEqual(c[("a.py", "# loop over items")], "comment")
        self.assertEqual(c[("a.py", "# noqa: E501")], "directive")
        self.assertEqual(c[("b.ts", "// explain why")], "comment")
        self.assertEqual(c[("b.ts", "// const z = 3;")], "code")
        self.assertEqual(c[("b.ts", "// eslint-disable-next-line")], "directive")
        self.assertNotIn(("a.py", "#!/usr/bin/env python"), c)

    def test_dependencies(self):
        r = self.repo({
            "package.json": json.dumps({"dependencies": {"left-pad": "1.0.0"}}),
            "requirements.txt": "flask==2.0\n",
            "go.mod": "module x\n\ngo 1.21\n\nrequire github.com/a/b v1.0.0\n",
            "Cargo.toml": "[package]\nname = \"x\"\n\n[dependencies]\nserde = \"1.0\"\n",
        })
        write(r, "package.json", json.dumps({"dependencies": {"left-pad": "1.3.0", "right-pad": "2.0.0"}}))
        write(r, "requirements.txt", "flask==3.0\nrequests==2.31\n")
        write(r, "go.mod", "module x\n\ngo 1.21\n\nrequire github.com/a/b v1.1.0\nrequire github.com/c/d v0.1.0\n")
        write(r, "Cargo.toml", "[package]\nname = \"x\"\n\n[dependencies]\nserde = \"1.0.1\"\nanyhow = \"1\"\n")
        names = sorted((p["file"], p["name"]) for p in measure(r)["pointers"]["dependencies"])
        self.assertEqual(names, [("Cargo.toml", "anyhow"), ("go.mod", "github.com/c/d"),
                                 ("package.json", "right-pad"), ("requirements.txt", "requests")])

    def coverage_repo(self, go=True):
        r = self.repo({"src/a.py": "a = 1\nb = 2\nc = 3\nd = 4\n", "src/b.py": "z = 0\n",
                       "go.mod": "module example.com/m\n", "m.go": "package m\n"})
        write(r, "src/a.py", "a = 1\nb = 20\nc = 30\nd = 4\n")
        write(r, "src/b.py", "z = 0\nq = 1\n")
        if go:
            write(r, "m.go", "package m\nvar x = 1\nvar y = 2\n")
        return r

    def unc(self, r, name, text):
        path = os.path.join(TMP, "cov-%s-%d" % (name, time.time_ns()))
        with open(path, "w") as fh:
            fh.write(text)
        m = measure(r, coverage=path)
        return m["checks"]["uncovered"], dict((p["file"], p["lines"]) for p in m["pointers"]["uncovered"]), m

    def test_lcov(self):
        r = self.coverage_repo(go=False)
        chk, got, m = self.unc(r, "lcov", "SF:%s/src/a.py\nDA:1,1\nDA:2,0\nDA:3,0\nDA:4,0\nend_of_record\n" % r)
        self.assertEqual(chk["status"], "measured")
        self.assertEqual(got["src/a.py"], [2, 3])
        self.assertEqual(got["src/b.py"], "all")
        self.assertIsNotNone(m["target"]["coverage_sha256"])

    def test_go_profile(self):
        r = self.repo({"go.mod": "module example.com/m\n", "m.go": "package m\n"})
        write(r, "m.go", "package m\nvar x = 1\nvar y = 2\n")
        chk, got, _ = self.unc(r, "go", "mode: set\nexample.com/m/m.go:2.1,2.10 1 0\nexample.com/m/m.go:3.1,3.10 1 1\n")
        self.assertEqual(got["m.go"], [2])

    def test_plain(self):
        r = self.coverage_repo(go=False)
        chk, got, _ = self.unc(r, "plain", "src/a.py:2\nsrc/a.py:4\nsrc/b.py:2\n")
        self.assertEqual(got["src/a.py"], [2])
        self.assertEqual(got["src/b.py"], [2])

    def test_malformed(self):
        r = self.coverage_repo()
        chk, got, _ = self.unc(r, "bad", "this is\nnot coverage\n")
        self.assertEqual(chk["status"], "unmeasured")
        self.assertEqual(chk["reason"], "coverage file not understood")


BLOCK = (
    "    total = 0\n    for value in values:\n        total = total + value * 2\n"
    "        total = total - offset(value)\n        log(total, value)\n    return total\n"
)


class Duplicates(Case):
    def pointers(self, r, **kw):
        m = measure(r, **kw)
        return m, m["pointers"]["duplicates"]

    def test_copied_from_another_file(self):
        r = self.repo({"src/util.py": "def helper(values):\n" + BLOCK, "src/new.py": "x = 1\n"})
        write(r, "src/new.py", "x = 1\n\n\ndef mine(values):\n" + BLOCK)
        m, dup = self.pointers(r)
        self.assertEqual(m["checks"]["duplicates"]["status"], "measured")
        self.assertEqual(len(dup), 1, dup)
        self.assertEqual((dup[0]["file"], dup[0]["match"]["file"], dup[0]["match"]["where"]),
                         ("src/new.py", "src/util.py", "base"))
        self.assertEqual(dup[0]["match"]["line"], 3)

    def test_vendor_and_test_sources_are_ignored(self):
        r = self.repo({"vendor/util.py": "def helper(values):\n" + BLOCK,
                       "tests/test_util.py": "def helper(values):\n" + BLOCK, "src/new.py": "x = 1\n"})
        write(r, "src/new.py", "x = 1\n\n\ndef mine(values):\n" + BLOCK)
        self.assertEqual(self.pointers(r)[1], [])

    def test_move_inside_the_diff_is_not_a_duplicate(self):
        r = self.repo({"src/a.py": "def helper(values):\n" + BLOCK, "src/b.py": "x = 1\n"})
        write(r, "src/a.py", "y = 1\n")
        write(r, "src/b.py", "x = 1\n\n\ndef helper(values):\n" + BLOCK)
        self.assertEqual(self.pointers(r)[1], [])

    def test_imports_only_repeat(self):
        imports = "import os\nimport sys\nimport json\nimport hashlib\nimport subprocess\nimport tempfile\n"
        r = self.repo({"src/a.py": imports, "src/b.py": "x = 1\n"})
        write(r, "src/b.py", imports + "x = 1\n")
        self.assertEqual(self.pointers(r)[1], [])

    def test_without_base_is_partial_but_finds_internal_copies(self):
        r = self.repo({"README.txt": "hi\n"})
        write(r, "src/a.py", "def one(values):\n" + BLOCK)
        write(r, "src/b.py", "def two(values):\n" + BLOCK)
        diff = dm("diff", "--repo", r, "--base", "HEAD", "--worktree").stdout
        d = os.path.join(TMP, "nobase-%d" % time.time_ns())
        os.makedirs(d)
        with open(os.path.join(d, "t.diff"), "wb") as fh:
            fh.write(diff)
        p = dm("measure", "--diff", os.path.join(d, "t.diff"), "--out", os.path.join(d, "m.json"), cwd=TMP)
        self.assertEqual(p.returncode, 0, p.err)
        with open(os.path.join(d, "m.json")) as fh:
            m = json.load(fh)
        self.assertEqual(m["checks"]["duplicates"]["status"], "partial")
        self.assertIn("no base in the local clone", m["checks"]["duplicates"]["reason"])
        self.assertTrue(m["pointers"]["duplicates"])

    def test_lizard_finds_long_identical_functions(self):
        body = "".join("    v%d = compute(values, %d)\n" % (i, i * 7) for i in range(34))
        r = self.repo({"README.txt": "hi\n"})
        write(r, "src/a.py", "def first(values):\n" + body + "    return v0\n")
        write(r, "src/b.py", "def second(values):\n" + body + "    return v0\n")
        dup = self.pointers(r)[1]
        self.assertTrue(dup)
        self.assertEqual(dup[0]["source"], "lizard")
        self.assertGreaterEqual(dup[0]["lines"], 30)


def py_src(body_branches):
    return "def f(x):\n    if x:\n        return 1\n" + "".join(
        "    if x == %d:\n        return %d\n" % (i, i) for i in range(body_branches)) + "    return 0\n"


class Complexity(Case):
    def test_measured_languages(self):
        r = self.repo({
            "src/a.py": py_src(0),
            "src/a.ts": "export function f(x: number) {\n  if (x) { return 1; }\n  return 0;\n}\n",
            "src/a.go": "package a\n\nfunc F(x int) int {\n\tif x > 0 {\n\t\treturn 1\n\t}\n\treturn 0\n}\n",
            "src/a.rs": "fn f(x: i32) -> i32 {\n    if x > 0 { return 1; }\n    0\n}\n",
        })
        write(r, "src/a.py", py_src(2))
        write(r, "src/a.ts", "export function f(x: number) {\n  if (x) { return 1; }\n  if (x > 2) { return 2; }\n  if (x > 3) { return 3; }\n  return 0;\n}\n")
        write(r, "src/a.go", "package a\n\nfunc F(x int) int {\n\tif x > 0 {\n\t\treturn 1\n\t}\n\tif x > 5 {\n\t\treturn 2\n\t}\n\tif x > 6 {\n\t\treturn 3\n\t}\n\treturn 0\n}\n")
        write(r, "src/a.rs", "fn f(x: i32) -> i32 {\n    if x > 0 { return 1; }\n    if x > 1 { return 2; }\n    if x > 2 { return 3; }\n    0\n}\n")
        m = measure(r)
        got = dict((c["file"], c) for c in m["pointers"]["complexity"])
        self.assertEqual(sorted(got), ["src/a.go", "src/a.py", "src/a.rs", "src/a.ts"])
        for c in got.values():
            self.assertEqual(c["status"], "changed")
            self.assertGreater(c["after"], c["before"])
        self.assertEqual(m["checks"]["complexity"]["status"], "measured")

    def test_renamed_function_is_new(self):
        r = self.repo({"src/a.py": py_src(1)})
        write(r, "src/a.py", py_src(1).replace("def f(x)", "def g(x)"))
        c = measure(r)["pointers"]["complexity"]
        self.assertEqual([(x["function"], x["status"], x["before"]) for x in c], [("g", "new", 0)])

    def test_nix_and_sh_are_unmeasured(self):
        r = self.repo({"a.nix": "{ a = 1; }\n", "b.sh": "echo a\n"})
        write(r, "a.nix", "{ a = 2; }\n")
        write(r, "b.sh", "echo b\n")
        c = measure(r)["checks"]["complexity"]
        self.assertEqual(c["status"], "unmeasured")
        self.assertEqual(sorted(c["unmeasured"]), [".nix", ".sh"])
        self.assertEqual(c["unmeasured"][".nix"], "lizard has no reader for .nix")

    def test_hotspot(self):
        files = dict(("f%d.py" % i, py_src(i % 3)) for i in range(10))
        r = self.repo(files)
        for k in range(5):
            write(r, "f3.py", py_src(1 + k % 2) + "# %d\n" % k)
            commit(r, "churn %d" % k)
        write(r, "f3.py", py_src(3))
        write(r, "f4.py", py_src(2))
        h = measure(r)["pointers"]["hotspots"]
        self.assertEqual([x["file"] for x in h], ["f3.py"])
        self.assertEqual(h[0]["rank"], 1)

    def test_shallow_clone_has_no_hotspots(self):
        r = self.repo({"a.py": py_src(0)})
        write(r, "a.py", py_src(1))
        commit(r, "two")
        clone = os.path.join(TMP, "shallow-%d" % time.time_ns())
        self.assertEqual(run(["git", "clone", "-q", "--depth", "1", "file://" + r, clone]).returncode, 0)
        write(clone, "a.py", py_src(3))
        c = measure(clone)["checks"]["hotspots"]
        self.assertEqual((c["status"], c["reason"]), ("unmeasured", "shallow clone"))

    def test_degraded_run(self):
        r = self.repo({"a.py": py_src(0), "tests/test_a.py": "def test_a():\n    assert 1 == 1\n"})
        write(r, "a.py", py_src(2))
        write(r, "tests/test_a.py", "def test_a():\n    pass\n")
        d = os.path.join(TMP, "deg-%d" % time.time_ns())
        os.makedirs(d)
        diff = degraded("diff", "--repo", r, "--base", "HEAD", "--worktree")
        self.assertEqual(diff.returncode, 0, diff.err)
        with open(os.path.join(d, "t.diff"), "wb") as fh:
            fh.write(diff.stdout)
        p = degraded("measure", "--repo", r, "--diff", os.path.join(d, "t.diff"), "--out", os.path.join(d, "m.json"),
                     "--base", "HEAD", "--worktree")
        self.assertEqual(p.returncode, 0, p.err)
        with open(os.path.join(d, "m.json")) as fh:
            m = json.load(fh)
        self.assertEqual(m["checks"]["complexity"]["reason"], "lizard not installed")
        self.assertEqual(m["checks"]["hotspots"]["reason"], "scc not installed")
        self.assertEqual(m["checks"]["tripwires"]["status"], "measured")
        self.assertEqual(m["tools"]["lizard"], None)
        self.assertIn(("assertion-lost", "tests/test_a.py"), kinds(m))


def ps_usable():
    try:
        return subprocess.run(["/bin/ps", "-o", "pid=", "-p", "1"], stdout=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def repo_state(r):
    idx = os.path.join(r, ".git", "index")
    return (
        git(r, "status", "--porcelain=v1", env=dict(ENV, GIT_OPTIONAL_LOCKS="0")).out,
        os.stat(idx).st_mtime_ns if os.path.exists(idx) else None,
        git(r, "count-objects", "-v").out,
    )


def mixed_repo(case):
    r = case.repo({"src/a.py": py_src(0), "src/b.py": "b = 1\n", "tests/test_a.py": "def test_a():\n    assert 1 == 1\n",
                   "conf.nix": "{ a = 1; }\n"})
    write(r, "src/a.py", py_src(3) + "x = f()  # type: ignore\n")
    git(r, "add", "src/a.py")
    write(r, "src/b.py", "b = 2\n")
    write(r, "tests/test_a.py", "def test_a():\n    pass\n")
    write(r, "conf.nix", "{ a = 2; }\n")
    write(r, "new.py", "n = 1\n")
    return r


class BundleAndReadOnly(Case):
    def test_read_only_around_diff_measure_bundle(self):
        r = mixed_repo(self)
        before = repo_state(r)
        m = measure(r)
        dm("bundle", "--metrics", os.path.join(m["_dir"], "m.json"), "--diff", os.path.join(m["_dir"], "t.diff"),
           "--dir", os.path.join(m["_dir"], "bundle"))
        self.assertEqual(repo_state(r), before)

    def test_determinism(self):
        r = mixed_repo(self)
        a, b = measure(r), measure(r)
        with open(os.path.join(a["_dir"], "m.json"), "rb") as fa, open(os.path.join(b["_dir"], "m.json"), "rb") as fb:
            self.assertEqual(fa.read(), fb.read())
        names = []
        for m in (a, b):
            d = os.path.join(m["_dir"], "bundle")
            self.assertEqual(dm("bundle", "--metrics", os.path.join(m["_dir"], "m.json"),
                                "--diff", os.path.join(m["_dir"], "t.diff"), "--dir", d).returncode, 0)
            names.append(dict((n, slurp(os.path.join(d, n))) for n in sorted(os.listdir(d))))
        self.assertEqual(names[0], names[1])
        self.assertEqual(sorted(names[0]), ["added.diff", "pointers-architecture.txt", "pointers-correctness.txt",
                                            "pointers-simplicity.txt", "pointers-tests.txt", "stat.txt", "tripwires.md"])

    def test_bundle_contents(self):
        r = mixed_repo(self)
        m = measure(r)
        d = os.path.join(m["_dir"], "bundle")
        dm("bundle", "--metrics", os.path.join(m["_dir"], "m.json"), "--diff", os.path.join(m["_dir"], "t.diff"), "--dir", d)
        read = lambda n: slurp(os.path.join(d, n), "r")
        self.assertIn("[MAJOR] tests/test_a.py", read("tripwires.md"))
        self.assertIn("grounding: metric: assertion-lost tests/test_a.py", read("tripwires.md"))
        self.assertIn("metric: complexity src/a.py", read("pointers-correctness.txt"))
        self.assertIn("complexity: unmeasured for .nix", read("pointers-correctness.txt"))
        self.assertTrue(read("pointers-correctness.txt").startswith("Pointers, ranked"))
        self.assertEqual(read("pointers-architecture.txt").splitlines()[1], "none")
        self.assertTrue(all(l.startswith(("diff --git", "+", "@@")) for l in read("added.diff").splitlines()))
        self.assertIn("conf.nix", read("stat.txt"))

    def test_remote_style_run(self):
        r = mixed_repo(self)
        diff = dm("diff", "--repo", r, "--base", "HEAD", "--worktree").stdout
        d = os.path.join(TMP, "remote-%d" % time.time_ns())
        os.makedirs(d)
        with open(os.path.join(d, "t.diff"), "wb") as fh:
            fh.write(diff)
        p = dm("measure", "--diff", os.path.join(d, "t.diff"), "--out", os.path.join(d, "m.json"), cwd=d)
        self.assertEqual(p.returncode, 0, p.err)
        m = json.loads(slurp(os.path.join(d, "m.json"), "r"))
        self.assertEqual(m["checks"]["tripwires"]["status"], "measured")
        self.assertIn(("assertion-lost", "tests/test_a.py"), kinds(m))
        self.assertEqual(m["checks"]["complexity"]["status"], "unmeasured")
        self.assertEqual(m["checks"]["complexity"]["reason"], "base not in the local clone")
        self.assertEqual(m["checks"]["hotspots"]["reason"], "base not in the local clone")
        self.assertEqual((m["target"]["repo"], m["target"]["base"], m["target"]["head"]), (None, None, None))

    def test_all_nix_and_sh_diff_is_never_empty_measured(self):
        r = self.repo({"a.nix": "{ a = 1; }\n", "b.sh": "echo a\n"})
        write(r, "a.nix", "{ a = 2; }\n")
        write(r, "b.sh", "echo b\n")
        m = measure(r)
        self.assertEqual(m["checks"]["complexity"]["status"], "unmeasured")
        self.assertEqual(m["pointers"]["complexity"], [])
        self.assertIn("unmeasured:", m["_stdout"].splitlines()[1])
        self.assertIn("complexity", m["_stdout"].splitlines()[1])
        self.assertTrue(m["_stdout"].splitlines()[2].startswith("wrote "))

    def test_target_identity(self):
        r = mixed_repo(self)
        m = measure(r)
        self.assertEqual(len(m["target"]["diff_sha256"]), 64)
        self.assertEqual(m["target"]["head"], "worktree")
        self.assertEqual(m["target"]["repo"], os.path.realpath(r))


class SnapshotFingerprintTimebox(Case):
    def snap(self, r, name="s"):
        d = os.path.join(TMP, "idx-%s-%d" % (name, time.time_ns()))
        p = dm("snapshot", "--repo", r, "--index-dir", d)
        return p, d

    def tree_of(self, r, tree, path):
        p = git(r, "cat-file", "-p", "%s:%s" % (tree, path), raw=True)
        return p.stdout if p.returncode == 0 else None

    def test_working_state_wins_over_index(self):
        r = self.repo({"a.txt": "base\n", "gone.txt": "g\n", "old.txt": "".join("l%d\n" % i for i in range(20)),
                       "x.sh": "echo\n"})
        write(r, "a.txt", "staged\n")
        git(r, "add", "a.txt")
        write(r, "a.txt", "working\n")
        os.remove(os.path.join(r, "gone.txt"))
        git(r, "mv", "old.txt", "new.txt")
        os.chmod(os.path.join(r, "x.sh"), 0o755)
        write(r, "untracked.txt", "u\n")
        write(r, ".gitignore", "ignored.txt\n")
        write(r, "ignored.txt", "i\n")
        before = repo_state(r)
        idx = os.path.join(r, ".git", "index")
        idx_bytes = slurp(idx)
        p, _ = self.snap(r)
        self.assertEqual(p.returncode, 0, p.err)
        tree = p.out.strip()
        self.assertEqual(self.tree_of(r, tree, "a.txt"), b"working\n")
        self.assertIsNone(self.tree_of(r, tree, "gone.txt"))
        self.assertIsNotNone(self.tree_of(r, tree, "new.txt"))
        self.assertIsNone(self.tree_of(r, tree, "old.txt"))
        self.assertEqual(self.tree_of(r, tree, "untracked.txt"), b"u\n")
        self.assertIsNone(self.tree_of(r, tree, "ignored.txt"))
        self.assertIn("100755", git(r, "ls-tree", tree, "x.sh").out)
        self.assertEqual(slurp(idx), idx_bytes)
        self.assertEqual(repo_state(r)[:2], before[:2])
        self.assertEqual(self.snap(r)[0].out, p.out)

    def test_linked_worktree(self):
        r = self.repo({"a.txt": "a\n"})
        wt = os.path.join(TMP, "wt-%d" % time.time_ns())
        self.assertEqual(git(r, "worktree", "add", "-q", "-b", "side", wt).returncode, 0)
        write(wt, "a.txt", "edited in worktree\n")
        write(wt, "extra.txt", "x\n")
        p, _ = self.snap(wt)
        self.assertEqual(p.returncode, 0, p.err)
        self.assertEqual(self.tree_of(wt, p.out.strip(), "a.txt"), b"edited in worktree\n")
        self.assertEqual(self.tree_of(wt, p.out.strip(), "extra.txt"), b"x\n")

    def test_refusals(self):
        d = tempfile.mkdtemp(dir=TMP)
        git(d, "init", "-q", "-b", "main")
        p, _ = self.snap(d)
        self.assertEqual(p.returncode, 2)
        self.assertIn("no commit yet", p.err)
        r = self.repo({"a.txt": "base\n"})
        git(r, "checkout", "-q", "-b", "other")
        write(r, "a.txt", "other\n")
        commit(r, "other")
        git(r, "checkout", "-q", "main")
        write(r, "a.txt", "main\n")
        commit(r, "main")
        git(r, "merge", "other")
        p, _ = self.snap(r)
        self.assertEqual(p.returncode, 2)

    def test_split_index_and_sparse(self):
        r = self.repo({"a/x.txt": "x\n", "b/y.txt": "y\n"})
        git(r, "update-index", "--split-index")
        write(r, "a/x.txt", "x2\n")
        write(r, "new.txt", "n\n")
        p, _ = self.snap(r, "split")
        want = os.path.join(TMP, "scratch-%d" % time.time_ns())
        run(["git", "clone", "-q", r, want])
        write(want, "a/x.txt", "x2\n")
        write(want, "new.txt", "n\n")
        git(want, "add", "-A")
        self.assertEqual(p.returncode, 0, p.err)
        self.assertEqual(p.out.strip(), git(want, "write-tree").out.strip())
        s = self.repo({"a/x.txt": "x\n", "b/y.txt": "y\n"})
        git(s, "sparse-checkout", "set", "a")
        write(s, "a/x.txt", "x2\n")
        p, _ = self.snap(s, "sparse")
        if p.returncode == 0:
            tree = p.out.strip()
            self.assertEqual(self.tree_of(s, tree, "b/y.txt"), b"y\n")
            self.assertEqual(self.tree_of(s, tree, "a/x.txt"), b"x2\n")
        else:
            self.assertEqual(p.returncode, 2)
            self.assertTrue(p.err.strip())

    def test_fingerprint(self):
        r = self.repo({"a.txt": "a\n"})
        write(r, "u.txt", "one\n")
        fp = lambda: dm("fingerprint", "--repo", r).out.strip()
        first = fp()
        self.assertEqual(len(first), 64)
        self.assertEqual(fp(), first)
        write(r, "u.txt", "one\ntwo\n")
        second = fp()
        self.assertNotEqual(second, first)
        write(r, "a.txt", "changed\n")
        third = fp()
        self.assertNotEqual(third, second)
        git(r, "add", "a.txt")
        fourth = fp()
        self.assertNotEqual(fourth, third)
        git(r, "reset", "-q")
        before = fp()
        self.assertEqual(git(r, "commit", "-q", "--allow-empty", "-m", "empty").returncode, 0)
        self.assertNotEqual(fp(), before)

    def alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def wait_dead(self, pid, seconds=5):
        end = time.time() + seconds
        while time.time() < end and self.alive(pid):
            time.sleep(0.1)
        return not self.alive(pid)

    def test_timebox_kills_grandchild_after_normal_exit(self):
        pidfile = os.path.join(TMP, "gc-%d.pid" % time.time_ns())
        p = dm("timebox", "--seconds", "20", "--", "sh", "-c", "sleep 60 & echo $! > %s" % pidfile)
        self.assertEqual(p.returncode, 0, p.err)
        pid = int(slurp(pidfile, "r"))
        self.assertTrue(self.wait_dead(pid))

    def test_timebox_timeout(self):
        pidfile = os.path.join(TMP, "to-%d.pid" % time.time_ns())
        t0 = time.time()
        p = dm("timebox", "--seconds", "1", "--", "sh", "-c", "sleep 60 & echo $! > %s; sleep 60" % pidfile)
        self.assertEqual(p.returncode, 124)
        self.assertLess(time.time() - t0, 8)
        self.assertTrue(self.wait_dead(int(slurp(pidfile, "r"))))

    def test_timebox_sweeps_setsid_daemon(self):
        if not ps_usable():
            self.skipTest("ps is not executable here (the nix build sandbox); the e2e run covers the sweep")
        pidfile = os.path.join(TMP, "dd-%d.pid" % time.time_ns())
        prog = (
            "import os,sys\n"
            "if os.fork()==0:\n"
            "    os.setsid()\n"
            "    open(sys.argv[1],'w').write(str(os.getpid()))\n"
            "    import time; time.sleep(60)\n"
            "else:\n"
            "    import time\n"
            "    while not os.path.exists(sys.argv[1]) or not open(sys.argv[1]).read(): time.sleep(0.05)\n"
        )
        p = dm("timebox", "--seconds", "20", "--", BARE_PY, "-c", prog, pidfile)
        self.assertEqual(p.returncode, 0, p.err)
        self.assertTrue(self.wait_dead(int(slurp(pidfile, "r"))))

    def test_timebox_separate_streams_and_exit_code(self):
        out, err = os.path.join(TMP, "so-%d" % time.time_ns()), os.path.join(TMP, "se-%d" % time.time_ns())
        p = dm("timebox", "--seconds", "10", "--stdout", out, "--stderr", err, "--", "sh", "-c", "echo OUT; echo ERR >&2; exit 3")
        self.assertEqual(p.returncode, 3)
        self.assertEqual(slurp(out, "r"), "OUT\n")
        self.assertEqual(slurp(err, "r"), "ERR\n")


def fake_bin(**scripts):
    d = tempfile.mkdtemp(dir=TMP)
    for name, body in scripts.items():
        path = os.path.join(d, name)
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\n" + body + "\n")
        os.chmod(path, 0o755)
    return d


class FixRound(Case):
    def test_generated_marker_cannot_switch_off_a_test_file(self):
        base = "def test_a():\n    assert 1 == 1\n\n\ndef test_b():\n    assert 2 == 2\n"
        r = self.repo({"tests/test_a.py": base})
        write(r, "tests/test_a.py", "# Fixtures are auto-generated by the helper below.\ndef test_a():\n    pass\n")
        m = measure(r)
        self.assertIn(("test-deleted", "tests/test_a.py"), kinds(m))
        self.assertIn(("assertion-lost", "tests/test_a.py"), kinds(m))
        self.assertTrue(m["facts"]["tests_touched"])
        self.assertFalse(m["facts"]["files"]["tests/test_a.py"]["excluded"])

    def test_generated_marker_must_be_there_at_base_too(self):
        r = self.repo({"src/a.py": "x = 1\n", "src/gen.py": "# Code generated by tool. DO NOT EDIT.\nx = 1\n"})
        write(r, "src/a.py", "# DO NOT EDIT\nx = 1\ny = 2\n")
        write(r, "src/gen.py", "# Code generated by tool. DO NOT EDIT.\nx = 1\ny = 2\n")
        write(r, "src/new_gen.py", "# @generated\nx = 1\n")
        files = measure(r)["facts"]["files"]
        self.assertFalse(files["src/a.py"]["excluded"])
        self.assertTrue(files["src/gen.py"]["excluded"])
        self.assertTrue(files["src/new_gen.py"]["excluded"])

    def test_complexity_covers_extensions_outside_the_language_map(self):
        r = self.repo({"b.pl": "sub f { return 1; }\n", "infra/main.tf": "resource \"a\" \"b\" {}\n", "a.py": py_src(0)})
        write(r, "b.pl", "sub f { my $x = shift; if ($x) { return 1; } if ($x > 2) { return 2; } if ($x > 3) { return 3; } return 0; }\n")
        write(r, "infra/main.tf", "resource \"a\" \"b\" { x = 1 }\n")
        write(r, "a.py", py_src(2))
        m = measure(r)
        self.assertEqual(m["checks"]["complexity"]["status"], "partial")
        self.assertEqual(m["checks"]["complexity"]["unmeasured"], {".tf": "lizard has no reader for .tf"})
        self.assertIn("b.pl", [c["file"] for c in m["pointers"]["complexity"]])
        self.assertEqual(m["facts"]["languages"].get("other"), 2)

    def test_a_failing_git_diff_is_an_error_not_an_empty_diff(self):
        r = self.repo({"a.py": "x = 1\n"})
        write(r, "a.py", "x = 2\n")
        env = dict(ENV, PATH=fake_bin(git='for a in "$@"; do [ "$a" = diff ] && { echo "fatal: boom" >&2; exit 128; }; done\nexec %s "$@"' % shutil.which("git")) + os.pathsep + ENV["PATH"])
        p = dm("diff", "--repo", r, "--base", "HEAD", "--worktree", env=env)
        self.assertEqual(p.returncode, 2)
        self.assertIn("boom", p.err)

    def test_unreadable_scc_output_is_unmeasured_not_measured(self):
        r = self.repo({"a.py": py_src(0)})
        for k in range(3):
            write(r, "a.py", py_src(k) + "# %d\n" % k)
            commit(r, "c%d" % k)
        write(r, "a.py", py_src(3))
        diff = degraded("diff", "--repo", r, "--base", "HEAD", "--worktree")
        d = os.path.join(TMP, "scc-%d" % time.time_ns())
        os.makedirs(d)
        with open(os.path.join(d, "t.diff"), "wb") as fh:
            fh.write(diff.stdout)
        env = dict(ENV, PATH=fake_bin(scc='echo garbage; exit 0') + os.pathsep + GITONLY)
        p = run([BARE_PY, "-I", RAW, "measure", "--repo", r, "--diff", os.path.join(d, "t.diff"),
                 "--out", os.path.join(d, "m.json"), "--base", "HEAD", "--worktree"], env=env)
        self.assertEqual(p.returncode, 0, p.err)
        m = json.loads(slurp(os.path.join(d, "m.json"), "r"))
        self.assertEqual(m["checks"]["hotspots"], {"status": "unmeasured", "reason": "scc output not understood"})
        self.assertEqual(m["checks"]["comments"]["unmeasured"], {"comment_deltas": "scc output not understood"})

    def test_paths_that_escape_the_repository_are_refused(self):
        r = self.repo({"a.py": "x = 1\n"})
        d = os.path.join(TMP, "esc-%d" % time.time_ns())
        os.makedirs(d)
        diff = "diff --git a/../outside.py b/../outside.py\nnew file mode 100644\n--- /dev/null\n+++ b/../outside.py\n@@ -0,0 +1 @@\n+x = 1\n"
        write(d, "t.diff", diff)
        p = dm("measure", "--repo", r, "--diff", os.path.join(d, "t.diff"), "--out", os.path.join(d, "m.json"),
               "--base", "HEAD", "--worktree")
        self.assertEqual(p.returncode, 2)
        self.assertIn("outside the repository", p.err)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(r), "outside.py")))
        write(d, "abs.diff", diff.replace("../outside.py", "/etc/outside.py").replace("a//etc", "a/etc"))
        p = dm("measure", "--repo", r, "--diff", os.path.join(d, "abs.diff"), "--out", os.path.join(d, "m2.json"))
        self.assertEqual(p.returncode, 2)

    def test_coverage_without_data_is_not_evidence(self):
        r = self.repo({"src/a.py": "a = 1\nb = 2\n", "m.go": "package m\n"})
        write(r, "src/a.py", "a = 1\nb = 20\n")

        def check(name, text):
            path = os.path.join(TMP, "cov-%s-%d" % (name, time.time_ns()))
            write(TMP, os.path.basename(path), text)
            return measure(r, coverage=path)["checks"]["uncovered"]

        self.assertEqual(check("goempty", "mode: set\n")["status"], "unmeasured")
        c = check("nodata", "SF:%s/src/a.py\nend_of_record\n" % r)
        self.assertEqual((c["status"], c["reason"]), ("unmeasured", "coverage report holds no line data"))
        c = check("other", "SF:%s/other.js\nDA:1,1\nend_of_record\n" % r)
        self.assertEqual((c["status"], c["reason"], c["applicable"]),
                         ("unmeasured", "coverage report has no evidence for: python", True))
        self.assertEqual(check("ok", "SF:%s/src/a.py\nDA:1,1\nDA:2,1\nend_of_record\n" % r)["status"], "measured")

    def cov_check(self, r, name, text):
        path = os.path.join(TMP, "cov-%s-%d" % (name, time.time_ns()))
        write(TMP, os.path.basename(path), text)
        return measure(r, coverage=path)["checks"]["uncovered"]

    def test_coverage_is_judged_per_language(self):
        r = self.repo({"src/a.py": "a = 1\nb = 2\n", "run.sh": "echo a\n", "web/app.js": "let a = 1;\n", "flake.nix": "{ }\n"})
        report = "SF:%s/src/a.py\nDA:1,1\nDA:2,1\nend_of_record\n" % r
        write(r, "run.sh", "echo b\n")
        write(r, "flake.nix", "{ a = 1; }\n")
        c = self.cov_check(r, "shellonly", report)
        self.assertEqual((c["status"], c["applicable"]), ("unmeasured", False))
        self.assertIn("no changed language has coverage (.nix .sh)", c["reason"])
        write(r, "src/a.py", "a = 1\nb = 3\n")
        c = self.cov_check(r, "pyok", report)
        self.assertEqual(c["status"], "measured")
        self.assertEqual(c["languages"], {"python": "measured", "shell": "not coverable", "nix": "not coverable"})
        write(r, "web/app.js", "let a = 2;\n")
        c = self.cov_check(r, "mixed", report)
        self.assertEqual((c["status"], c["applicable"], c["reason"]),
                         ("unmeasured", True, "coverage report has no evidence for: javascript"))
        self.assertEqual(c["languages"]["python"], "measured")

    def test_mixed_languages_keep_the_measured_ones_uncovered_lines(self):
        r = self.repo({"src/a.py": "a = 1\nb = 2\nc = 3\n", "web/app.js": "let a = 1;\n"})
        write(r, "src/a.py", "a = 1\nb = 20\nc = 30\n")
        write(r, "web/app.js", "let a = 2;\n")
        path = os.path.join(TMP, "cov-mixed-%d" % time.time_ns())
        write(TMP, os.path.basename(path), "SF:%s/src/a.py\nDA:1,1\nDA:2,0\nDA:3,1\nend_of_record\n" % r)
        m = measure(r, coverage=path)
        c = m["checks"]["uncovered"]
        self.assertEqual((c["status"], c["reason"]), ("unmeasured", "coverage report has no evidence for: javascript"))
        self.assertEqual([(p["file"], p["lines"]) for p in m["pointers"]["uncovered"]], [("src/a.py", [2])])
        out = os.path.join(TMP, "scope-%d" % time.time_ns())
        os.makedirs(out)
        diff = dm("diff", "--repo", r, "--base", "HEAD", "--worktree").stdout
        with open(os.path.join(out, "t.diff"), "wb") as fh:
            fh.write(diff)
        p = dm("measure", "--repo", r, "--diff", os.path.join(out, "t.diff"), "--out", os.path.join(out, "m.json"),
               "--base", "HEAD", "--worktree", "--coverage", path, "--coverage-langs", "python")
        self.assertEqual(p.returncode, 0, p.err)
        c = json.loads(slurp(os.path.join(out, "m.json"), "r"))["checks"]["uncovered"]
        self.assertEqual(c["status"], "measured")
        self.assertEqual(c["languages"], {"python": "measured", "javascript": "outside tool scope"})

    def test_unknown_coverage_language_names_are_rejected(self):
        r = self.repo({"src/a.py": "a = 1\n"})
        write(r, "src/a.py", "a = 2\n")
        out = os.path.join(TMP, "names-%d" % time.time_ns())
        os.makedirs(out)
        write(out, "t.diff", dm("diff", "--repo", r, "--base", "HEAD", "--worktree").out)
        cov = os.path.join(out, "cov")
        write(out, "cov", "SF:%s/x.js\nDA:1,1\nend_of_record\n" % r)
        cmd = ["measure", "--repo", r, "--diff", os.path.join(out, "t.diff"), "--out", os.path.join(out, "m.json"),
               "--base", "HEAD", "--worktree", "--coverage", cov]
        p = dm(*cmd, "--coverage-langs", "py,js")
        self.assertEqual(p.returncode, 2)
        self.assertIn("unknown language in --coverage-langs: js, py", p.err)
        self.assertIn("python", p.err)
        p = dm(*cmd, "--coverage-langs", "python")
        self.assertEqual(p.returncode, 0, p.err)
        c = json.loads(slurp(os.path.join(out, "m.json"), "r"))["checks"]["uncovered"]
        self.assertEqual(c["reason"], "coverage report has no evidence for: python")

    def test_an_inherited_git_dir_does_not_redirect_the_scripts(self):
        r = self.repo({"a.py": "x = 1\n"})
        write(r, "a.py", "x = 2\n")
        env = dict(ENV, GIT_DIR=os.path.join(TMP, "nonexistent"), GIT_WORK_TREE=TMP, GIT_INDEX_FILE=os.path.join(TMP, "nope"))
        p = dm("diff", "--repo", r, "--base", "HEAD", "--worktree", env=env)
        self.assertEqual(p.returncode, 0, p.err)
        self.assertIn("+x = 2", p.out)
        self.assertEqual(dm("fingerprint", "--repo", r, env=env).out, dm("fingerprint", "--repo", r).out)

    def test_a_language_the_tool_does_cover_still_needs_evidence(self):
        r = self.repo({"src/a.py": "a = 1\n", "web/app.js": "let a = 1;\n"})
        write(r, "src/a.py", "a = 2\n")
        write(r, "web/app.js", "let a = 2;\n")
        path = os.path.join(TMP, "cov-both-%d" % time.time_ns())
        write(TMP, os.path.basename(path), "SF:%s/src/a.py\nDA:1,1\nend_of_record\n" % r)
        out = os.path.join(TMP, "scope2-%d" % time.time_ns())
        os.makedirs(out)
        write(out, "t.diff", dm("diff", "--repo", r, "--base", "HEAD", "--worktree").out)
        p = dm("measure", "--repo", r, "--diff", os.path.join(out, "t.diff"), "--out", os.path.join(out, "m.json"),
               "--base", "HEAD", "--worktree", "--coverage", path, "--coverage-langs", "python,javascript")
        self.assertEqual(p.returncode, 0, p.err)
        c = json.loads(slurp(os.path.join(out, "m.json"), "r"))["checks"]["uncovered"]
        self.assertEqual((c["status"], c["reason"]), ("unmeasured", "coverage report has no evidence for: javascript"))

    def test_a_generated_marker_does_not_hide_a_new_files_tests_or_skips(self):
        r = self.repo({"README.txt": "hi\n"})
        write(r, "src/lib.rs", "// @generated\n#[test]\nfn t() {\n    run();\n}\n")
        write(r, "src/skip_test.go", "// Code generated by x. DO NOT EDIT.\npackage a\n\nfunc TestA(t *testing.T) {\n\tt.Skip(\"x\")\n}\n")
        m = measure(r)
        self.assertTrue(m["facts"]["tests_touched"])
        self.assertTrue(m["facts"]["files"]["src/lib.rs"]["excluded"])
        self.assertIn(("test-no-assertion", "src/lib.rs"), kinds(m))
        self.assertIn(("test-skipped", "src/skip_test.go"), kinds(m))

    def test_a_missing_coverage_file_is_unmeasured_not_a_crash(self):
        r = self.repo({"a.py": "x = 1\n"})
        write(r, "a.py", "x = 2\n")
        c = measure(r, coverage=os.path.join(TMP, "does-not-exist"))["checks"]["uncovered"]
        self.assertEqual((c["status"], c["reason"]), ("unmeasured", "coverage file not understood"))

    def test_dependencies_of_a_renamed_manifest_compare_with_its_old_path(self):
        def manifest(extra):
            deps = dict(("dep%d" % i, "1.%d.0" % i) for i in range(12))
            deps.update(extra)
            return json.dumps({"name": "x", "dependencies": deps}, indent=2, sort_keys=True) + "\n"

        r = self.repo({"pkg/package.json": manifest({}), "x.txt": "x\n"})
        os.makedirs(os.path.join(r, "app"))
        git(r, "mv", "pkg/package.json", "app/package.json")
        write(r, "app/package.json", manifest({"newdep": "9.0.0"}))
        m = measure(r)
        self.assertEqual(m["facts"]["files"]["app/package.json"]["status"], "renamed")
        self.assertEqual([(p["file"], p["name"]) for p in m["pointers"]["dependencies"]], [("app/package.json", "newdep")])


class CommitSet(Case):
    def test_commit_set_stages_to_exactly_the_approved_tree(self):
        r = self.repo({"keep.txt": "k\n", "old.txt": "".join("l%d\n" % i for i in range(20)), "gone.txt": "g\n",
                       "loop.txt": "".join("m%d\n" % i for i in range(20))})
        git(r, "mv", "old.txt", "new.txt")
        git(r, "rm", "-q", "gone.txt")
        write(r, "sp ace.txt", "s\n")
        os.symlink("nowhere", os.path.join(r, "dangling"))
        dirty = os.path.join(TMP, "dirty-%d" % time.time_ns())
        self.assertEqual(dm("dirty", "--repo", r, "--out", dirty).returncode, 0)
        t0 = dm("snapshot", "--repo", r, "--index-dir", os.path.join(TMP, "i0-%d" % time.time_ns())).out.strip()
        os.rename(os.path.join(r, "loop.txt"), os.path.join(r, "moved.txt"))
        t_end = dm("snapshot", "--repo", r, "--index-dir", os.path.join(TMP, "i1-%d" % time.time_ns())).out.strip()
        cs = os.path.join(TMP, "cs-%d" % time.time_ns())
        p = dm("commit-set", "--repo", r, "--from", t0, "--to", t_end, "--dirty", dirty, "--out", cs)
        self.assertEqual(p.returncode, 0, p.err)
        paths = slurp(cs).split(b"\0")[:-1]
        self.assertEqual(sorted(paths), [b"dangling", b"loop.txt", b"moved.txt", b"new.txt", b"sp ace.txt"])
        add = git(r, "--literal-pathspecs", "add", "-A", "--pathspec-from-file=" + cs, "--pathspec-file-nul")
        self.assertEqual(add.returncode, 0, add.err)
        self.assertEqual(git(r, "write-tree").out.strip(), t_end)

    def test_commit_set_run_from_a_subdirectory_still_stages_by_toplevel(self):
        r = self.repo({"sub/a.txt": "a\n", "b.txt": "b\n"})
        write(r, "sub/a.txt", "a2\n")
        write(r, "b.txt", "b2\n")
        dirty = os.path.join(TMP, "dirty-%d" % time.time_ns())
        dm("dirty", "--repo", os.path.join(r, "sub"), "--out", dirty)
        self.assertEqual(sorted(slurp(dirty).split(b"\0")[:-1]), [b"b.txt", b"sub/a.txt"])


class Signals(Case):
    def test_timebox_killed_by_sigterm_leaves_no_child(self):
        pidfile = os.path.join(TMP, "tb-%d.pid" % time.time_ns())
        proc = subprocess.Popen([DM, "timebox", "--seconds", "600", "--", "sh", "-c", "sleep 4242 & echo $! > %s; wait" % pidfile],
                                env=ENV, start_new_session=True)
        end = time.time() + 20
        while time.time() < end and not os.path.exists(pidfile):
            time.sleep(0.1)
        time.sleep(0.3)
        pid = int(slurp(pidfile, "r"))
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=30)
        end = time.time() + 10
        while time.time() < end:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
        with self.assertRaises(OSError):
            os.kill(pid, 0)


class Cli(Case):
    def test_every_verb_exists(self):
        for verb in ("diff", "measure", "bundle", "filter-lint", "snapshot", "fingerprint", "dirty", "commit-set", "timebox"):
            p = dm(verb, "--help")
            self.assertEqual(p.returncode, 0, verb)

    def test_head_without_repo_exits_2(self):
        d = os.path.join(TMP, "nr-%d" % time.time_ns())
        os.makedirs(d)
        write(d, "t.diff", "")
        p = dm("measure", "--diff", os.path.join(d, "t.diff"), "--out", os.path.join(d, "m.json"), "--worktree", cwd=d)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
