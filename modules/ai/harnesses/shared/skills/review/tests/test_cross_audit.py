import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = os.path.abspath(sys.argv[1])
del sys.argv[1:]
sys.dont_write_bytecode = True
CA = os.path.join(SCRIPTS, "cross_audit.py")
TMP = tempfile.mkdtemp(prefix="ca-test-")
PY = sys.executable

FAKE = '''#!%(py)s
import json, os, sys, time
name = os.path.basename(sys.argv[0])
cfg = json.load(open(os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "fake-config.json")))
mode = cfg.get("mode-" + name, "ok")
argv = sys.argv[1:]
with open(cfg["log"], "a") as fh:
    fh.write(json.dumps({"name": name, "argv": argv, "cwd": os.getcwd(), "env": sorted(os.environ),
                         "via": os.environ.get("FAKE_VIA"), "pwd": os.environ.get("PWD"), "path": os.environ.get("PATH")}) + "\\n")
if name == "codex" and argv[:1] == ["doctor"]:
    print(json.dumps({"checks": {"sandbox.helpers": {"details": {"filesystem sandbox": "unrestricted"}}}}))
    sys.exit(0)
sys.stderr.write("fake %%s noise\\n" %% name)
edit = cfg.get("edit-" + name)
if edit:
    target = edit.replace("{CWD}", os.getcwd())
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a") as fh:
        fh.write("tampered\\n")
if mode == "sleep":
    with open(cfg["pidfile"], "w") as fh:
        fh.write(str(os.getpid()))
    time.sleep(60)
if mode == "notlogged":
    sys.stderr.write("Not logged in\\n")
    sys.exit(1)
text = "" if mode == "empty" else "AUDIT-OK from " + name
if name == "codex":
    with open(argv[argv.index("-o") + 1], "w") as fh:
        fh.write(text)
elif name == "claude":
    print(json.dumps({"type": "result", "result": text}))
else:
    print(json.dumps({"response": text}))
'''
WRAPPER = '''#!%(py)s
import os, sys
os.environ["FAKE_VIA"] = "wrapper"
import json
cfg = json.load(open(os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "fake-config.json")))
real = os.path.join(cfg["real"], sys.argv[3])
os.execv(real, [real] + sys.argv[4:])
'''


def tool_dir(names):
    d = tempfile.mkdtemp(dir=TMP)
    for n in names:
        if shutil.which(n):
            os.symlink(shutil.which(n), os.path.join(d, n))
    return d


def ps_usable():
    try:
        return subprocess.run(["/bin/ps", "-o", "pid=", "-p", "1"], stdout=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t"] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def make_repo():
    d = tempfile.mkdtemp(prefix="repo-", dir=TMP)
    git(d, "init", "-q", "-b", "main")
    with open(os.path.join(d, "a.txt"), "w") as fh:
        fh.write("a\n")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "init")
    with open(os.path.join(d, "untracked.txt"), "w") as fh:
        fh.write("u\n")
    return d


class Env(object):
    """A fake PATH with chosen fake CLIs, a repo, a bundle and a template."""

    def __init__(self, fakes=("claude", "codex", "agy"), wrapper=False):
        self.log = os.path.join(TMP, "log-%d" % time.time_ns())
        open(self.log, "w").close()
        self.real = tempfile.mkdtemp(dir=TMP)
        for n in ("claude", "codex", "agy"):
            self.write_exec(os.path.join(self.real, n), FAKE % {"py": PY})
        self.bin = tool_dir(["python3", "git", "ps", "sh"])
        self.home = tempfile.mkdtemp(dir=TMP)
        if wrapper:
            self.write_exec(os.path.join(self.bin, "harness-wrap"), WRAPPER % {"py": PY})
            os.makedirs(os.path.join(self.home, ".config", "ai", "settings"))
            with open(os.path.join(self.home, ".config", "ai", "settings", "review.json"), "w") as fh:
                json.dump({"harnessWrapper": ["harness-wrap", "agent", "run"]}, fh)
            if "agy" in fakes:
                os.symlink(os.path.join(self.real, "agy"), os.path.join(self.bin, "agy"))
        else:
            for n in fakes:
                os.symlink(os.path.join(self.real, n), os.path.join(self.bin, n))
        self.repo = make_repo()
        self.bundle = tempfile.mkdtemp(dir=TMP)
        with open(os.path.join(self.bundle, "target.diff"), "w") as fh:
            fh.write("diff --git a/x b/x\n")
        self.template = os.path.join(TMP, "template-%d.md" % time.time_ns())
        with open(self.template, "w") as fh:
            fh.write("Audit {BUNDLE}; clone {CLONE}. Reply AUDIT-OK.\n")
        self.extra = {}

    @staticmethod
    def write_exec(path, text):
        with open(path, "w") as fh:
            fh.write(text)
        os.chmod(path, 0o755)

    def env(self):
        e = dict(os.environ, PATH=self.bin, HOME=self.home, PYTHONDONTWRITEBYTECODE="1", CLAUDECODE="1", CLAUDE_CODE_ENTRYPOINT="cli",
                 DMACS_SOCKET="x", GIT_CONFIG_GLOBAL="/dev/null", SOPS_AGE_KEY_CMD="cat key", VOYAGE_API_KEY="v",
                 ANTHROPIC_API_KEY="a", OLDPWD=self.repo, PWD=self.repo)
        e.pop("REVIEW_CROSS_AUDIT", None)
        cfg = {"log": self.log, "real": self.real}
        for k, v in self.extra.items():
            if k.startswith("FAKE_EDIT_"):
                cfg["edit-" + k[len("FAKE_EDIT_"):].lower()] = v
            elif k.startswith("FAKE_MODE_"):
                cfg["mode-" + k[len("FAKE_MODE_"):].lower()] = v
            elif k == "FAKE_PIDFILE":
                cfg["pidfile"] = v
            else:
                e[k] = v
        for d in (self.real, self.bin):
            with open(os.path.join(d, "fake-config.json"), "w") as fh:
                json.dump(cfg, fh)
        return e

    def run(self, harness, extra=(), out=None):
        self.out = out or tempfile.mkdtemp(dir=TMP)
        cmd = [PY, "-I", CA, "run", "--harness", harness, "--bundle", self.bundle, "--prompt-template", self.template,
               "--out", self.out, "--repo", self.repo] + list(extra)
        return subprocess.run(cmd, env=self.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def calls(self):
        rows = [json.loads(l) for l in read(self.log).splitlines() if l.strip()]
        return [r for r in rows if r["argv"][:1] != ["doctor"]]

    def status(self, short):
        return read(os.path.join(self.out, short, "status")).strip()


class Run(unittest.TestCase):
    def test_from_claude_runs_codex_and_agy_with_exact_flags(self):
        e = Env()
        p = e.run("claude")
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = dict((c["name"], c) for c in e.calls())
        self.assertEqual(sorted(calls), ["agy", "codex"])
        astra, argon = os.path.join(e.out, "astra"), os.path.join(e.out, "argon")
        prompt_a, prompt_g = read(os.path.join(astra, "prompt.md")), read(os.path.join(argon, "prompt.md"))
        flags = []
        for f in ("multi_agent", "computer_use", "browser_use", "browser_use_external", "in_app_browser", "apps"):
            flags += ["--disable", f]
        self.assertEqual(calls["codex"]["argv"], ["exec"] + flags + [
            "-s", "read-only", "--skip-git-repo-check", "--json", "-o", os.path.join(astra, "audit.md"),
            "-m", "gpt-6-astra", "-c", 'model_reasoning_effort="high"', "-C", os.path.join(astra, "bundle"), prompt_a])
        self.assertEqual(calls["agy"]["argv"], [
            "-p", prompt_g, "--model", "gemini-4-argon-high", "--output-format", "json", "--sandbox",
            "--dangerously-skip-permissions", "--print-timeout", "0"])
        self.assertEqual(calls["codex"]["cwd"], os.path.realpath(os.path.join(astra, "bundle")))
        self.assertEqual(calls["agy"]["cwd"], os.path.realpath(os.path.join(argon, "bundle")))
        self.assertEqual(read(os.path.join(argon, "audit.md")), "AUDIT-OK from agy")
        self.assertTrue(e.status("astra").startswith("ok"))
        self.assertIn("(no read-only sandbox: managed policy)", e.status("astra"))
        self.assertEqual(e.status("argon"), "ok")

    def test_from_codex_runs_restricted_claude_and_agy(self):
        e = Env()
        self.assertEqual(e.run("codex").returncode, 0)
        calls = dict((c["name"], c) for c in e.calls())
        self.assertEqual(sorted(calls), ["agy", "claude"])
        a = calls["claude"]["argv"]
        for flag in ("--restricted", "--strict-mcp-config", "--disable-slash-commands"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(a[a.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(a[a.index("--model") + 1], "opus")
        self.assertNotIn("default", a)
        self.assertNotIn("bypassPermissions", a)
        self.assertEqual(read(os.path.join(e.out, "opus", "audit.md")), "AUDIT-OK from claude")

    def test_from_agy_and_unknown(self):
        e = Env()
        e.run("agy")
        self.assertEqual(sorted(c["name"] for c in e.calls()), ["claude", "codex"])
        e = Env()
        e.run("unknown")
        self.assertEqual(sorted(c["name"] for c in e.calls()), ["agy", "claude", "codex"])

    def test_wrapper_routes_claude_and_codex_but_not_agy(self):
        e = Env(wrapper=True)
        p = e.run("unknown")
        self.assertEqual(p.returncode, 0, p.stderr)
        by = dict((c["name"], c) for c in e.calls())
        self.assertEqual(by["claude"]["via"], "wrapper")
        self.assertEqual(by["codex"]["via"], "wrapper")
        self.assertIsNone(by["agy"]["via"])

    def test_child_environment_and_isolation(self):
        e = Env()
        with open(os.path.join(e.bundle, "note.txt"), "w") as fh:
            fh.write("no repo path in here\n")
        clone = make_repo()
        git(clone, "remote", "remove", "origin")
        e.run("unknown", ["--clone", clone])
        for c in e.calls():
            self.assertNotIn("CLAUDECODE", c["env"])
            self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", c["env"])
            self.assertFalse([k for k in c["env"] if k.startswith("DMACS_")])
            self.assertIn(os.path.realpath(e.out), os.path.realpath(c["cwd"]))
            self.assertTrue(c["cwd"].endswith("/bundle"))
            self.assertNotIn(e.repo, " ".join(c["argv"]))
            self.assertNotIn(os.path.realpath(e.repo), " ".join(c["argv"]))
            self.assertIn(os.path.join(os.path.dirname(c["cwd"]), "clone"), [os.path.realpath(a) for a in c["argv"]])
            self.assertNotIn(clone, c["argv"])
        for short in ("opus", "astra", "argon"):
            self.assertNotIn(e.repo, read(os.path.join(e.out, short, "prompt.md")))

    def test_bundle_naming_the_repo_exits_2(self):
        e = Env()
        with open(os.path.join(e.bundle, "leak.txt"), "w") as fh:
            fh.write("see %s/a.txt\n" % e.repo)
        p = e.run("claude")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(e.calls(), [])

    def test_missing_binaries_are_skipped_with_a_note(self):
        e = Env(fakes=("agy",))
        p = e.run("unknown")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(e.status("opus"), "unavailable (claude not installed)")
        self.assertEqual(e.status("astra"), "unavailable (codex not installed)")
        self.assertEqual([c["name"] for c in e.calls()], ["agy"])

    def test_statuses(self):
        e = Env(fakes=("claude", "codex"))
        e.run("claude")
        self.assertEqual(e.status("argon"), "unavailable (agy not installed)")
        e = Env()
        e.extra["FAKE_MODE_AGY"] = "notlogged"
        e.run("claude")
        self.assertEqual(e.status("argon"), "unavailable (agy not signed in)")
        e = Env()
        e.extra["FAKE_MODE_AGY"] = "empty"
        e.run("claude")
        self.assertEqual(e.status("argon"), "empty (no response)")

    def test_timeout_leaves_no_process(self):
        e = Env()
        pidfile = os.path.join(TMP, "pid-%d" % time.time_ns())
        e.extra.update(FAKE_MODE_AGY="sleep", FAKE_PIDFILE=pidfile)
        t0 = time.time()
        e.run("claude", ["--timeout", "2"])
        self.assertLess(time.time() - t0, 20)
        self.assertEqual(e.status("argon"), "timeout")
        pid = int(read(pidfile))
        end = time.time() + 5
        while time.time() < end:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
        with self.assertRaises(OSError):
            os.kill(pid, 0)

    def test_kill_switch_starts_nothing(self):
        e = Env()
        e.extra["REVIEW_CROSS_AUDIT"] = "off"
        p = e.run("claude")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(e.calls(), [])
        self.assertEqual(e.status("astra"), "skipped (REVIEW_CROSS_AUDIT=off)")
        self.assertEqual(e.status("argon"), "skipped (REVIEW_CROSS_AUDIT=off)")

    def test_repo_write_discards_everything(self):
        e = Env()
        e.extra["FAKE_EDIT_AGY"] = os.path.join(e.repo, "untracked.txt")
        e.run("claude")
        self.assertTrue(json.loads(read(os.path.join(e.out, "integrity.json")))["repo_changed"])
        self.assertTrue(e.status("astra").startswith("discarded"))
        self.assertTrue(e.status("argon").startswith("discarded"))

    def test_bundle_write_discards_only_that_auditor(self):
        e = Env()
        e.extra["FAKE_EDIT_AGY"] = "{CWD}/target.diff"
        e.run("claude")
        self.assertEqual(e.status("argon"), "discarded (bundle changed)")
        self.assertTrue(e.status("astra").startswith("ok"))
        self.assertFalse(json.loads(read(os.path.join(e.out, "integrity.json")))["repo_changed"])

    def test_clone_write_discards_every_auditor(self):
        e = Env()
        clone = make_repo()
        e.extra["FAKE_EDIT_AGY"] = os.path.join(clone, "untracked.txt")
        e.run("claude", ["--clone", clone])
        self.assertEqual(e.status("astra"), "discarded (clone changed)")
        self.assertEqual(e.status("argon"), "discarded (clone changed)")

    def test_fable_is_refused(self):
        e = Env()
        p = e.run("claude", ["--codex-model", "Fable-5"])
        self.assertEqual(p.returncode, 2)
        self.assertEqual(e.calls(), [])


class Hardening(unittest.TestCase):
    def test_environment_is_an_allowlist(self):
        e = Env()
        e.run("claude")
        for c in e.calls():
            for leaked in ("SOPS_AGE_KEY_CMD", "VOYAGE_API_KEY", "OLDPWD", "SSH_AUTH_SOCK"):
                self.assertNotIn(leaked, c["env"])
            self.assertIn("ANTHROPIC_API_KEY", c["env"])
            self.assertEqual(os.path.realpath(c["pwd"]), os.path.realpath(c["cwd"]))
            self.assertNotIn(os.path.realpath(e.repo), c["pwd"])

    def test_path_entries_naming_the_repo_are_dropped(self):
        e = Env()
        e.extra["PATH"] = e.bin + os.pathsep + os.path.join(e.repo, "node_modules", "bin")
        e.run("claude")
        calls = e.calls()
        self.assertEqual(sorted(c["name"] for c in calls), ["agy", "codex"])
        for c in calls:
            self.assertNotIn(e.repo, c["path"])
            self.assertIn(e.bin, c["path"])

    def test_real_clone_reflog_is_named_and_refused(self):
        e = Env()
        clone = os.path.join(TMP, "realclone-%d" % time.time_ns())
        self.assertEqual(subprocess.run(["git", "clone", "--local", "--no-checkout", e.repo, clone],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode, 0)
        git(clone, "remote", "remove", "origin")
        p = e.run("claude", ["--clone", clone])
        self.assertEqual(p.returncode, 2)
        self.assertIn(os.path.join(".git", "logs"), p.stderr)
        shutil.rmtree(os.path.join(clone, ".git", "logs"))
        p = e.run("claude", ["--clone", clone])
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_untrusted_target_runs_only_the_enforced_sandbox(self):
        e = Env()
        p = e.run("codex", ["--untrusted"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual([c["name"] for c in e.calls()], ["claude"])
        self.assertEqual(e.status("argon"), "skipped (untrusted target, no sandbox)")

    def test_clone_copy_write_discards_only_that_auditor(self):
        e = Env()
        clone = make_repo()
        e.extra["FAKE_EDIT_AGY"] = "{CWD}/../clone/untracked.txt"
        e.run("claude", ["--clone", clone])
        self.assertEqual(e.status("argon"), "discarded (clone copy changed)")
        self.assertTrue(e.status("astra").startswith("ok"))

    def test_hook_planted_in_the_clone_discards_everything(self):
        e = Env()
        clone = make_repo()
        e.extra["FAKE_EDIT_AGY"] = os.path.join(clone, ".git", "hooks", "pre-commit")
        e.run("claude", ["--clone", clone])
        self.assertEqual(e.status("astra"), "discarded (clone changed)")
        self.assertEqual(e.status("argon"), "discarded (clone changed)")

    def test_a_file_link_leaving_the_bundle_is_refused_not_followed(self):
        e = Env()
        secret = os.path.join(TMP, "secret-%d" % time.time_ns())
        with open(secret, "w") as fh:
            fh.write("outside content\n")
        os.symlink(secret, os.path.join(e.bundle, "link.txt"))
        p = e.run("claude")
        self.assertEqual(p.returncode, 2)
        self.assertIn("link that leaves", p.stderr)

    def test_objects_directories_in_the_bundle_are_scanned(self):
        e = Env()
        d = os.path.join(e.bundle, "files", "src", "objects")
        os.makedirs(d)
        with open(os.path.join(d, "conf.py"), "w") as fh:
            fh.write('path = "%s/data"\n' % e.repo)
        p = e.run("claude")
        self.assertEqual(p.returncode, 2)
        self.assertIn("names the real repository", p.stderr)

    def test_a_directory_link_leaving_the_bundle_is_refused(self):
        e = Env()
        outside = tempfile.mkdtemp(dir=TMP)
        with open(os.path.join(outside, "secret.txt"), "w") as fh:
            fh.write("outside\n")
        os.symlink(outside, os.path.join(e.bundle, "dirlink"))
        p = e.run("claude")
        self.assertEqual(p.returncode, 2)
        self.assertIn("link that leaves", p.stderr)
        self.assertEqual(e.calls(), [])

    def test_links_inside_the_bundle_are_kept(self):
        e = Env()
        os.makedirs(os.path.join(e.bundle, "sub"))
        os.symlink("sub", os.path.join(e.bundle, "dirlink"))
        p = e.run("claude")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.islink(os.path.join(e.out, "astra", "bundle", "dirlink")))

    def test_a_link_leaving_the_clone_is_not_copied(self):
        e = Env()
        clone = make_repo()
        os.symlink(tempfile.mkdtemp(dir=TMP), os.path.join(clone, "escape"))
        e.run("claude", ["--clone", clone])
        self.assertFalse(os.path.lexists(os.path.join(e.out, "astra", "clone", "escape")))
        self.assertEqual(json.loads(read(os.path.join(e.out, "integrity.json")))["escaping_links_skipped"], ["escape"])

    def test_a_fifo_in_the_bundle_does_not_hang_the_copy(self):
        e = Env()
        os.mkfifo(os.path.join(e.bundle, "pipe"))
        done = {}

        def go():
            done["p"] = e.run("claude")

        import threading
        t = threading.Thread(target=go)
        t.start()
        t.join(60)
        self.assertFalse(t.is_alive())
        self.assertEqual(done["p"].returncode, 0, done["p"].stderr)
        self.assertFalse(os.path.exists(os.path.join(e.out, "astra", "bundle", "pipe")))

    def test_extra_environment_names_are_exact_and_never_secrets(self):
        e = Env()
        e.extra["CROSS_AUDIT_PASS_ENV"] = "S,MY_VAR,MY_TOKEN,MY_KEY_CMD,SSH_AUTH_SOCK"
        e.extra.update(MY_VAR="1", MY_TOKEN="t", MY_KEY_CMD="c", SSH_AUTH_SOCK="/tmp/sock", SHLVL="2")
        e.run("claude")
        for c in e.calls():
            self.assertIn("MY_VAR", c["env"])
            for leaked in ("MY_TOKEN", "MY_KEY_CMD", "SSH_AUTH_SOCK", "SHLVL", "SOPS_AGE_KEY_CMD"):
                self.assertNotIn(leaked, c["env"])
        e = Env()
        e.extra["CROSS_AUDIT_PASS_ENV"] = "MY_VAR"
        e.extra["MY_VAR"] = "1"
        e.run("codex", ["--untrusted"])
        self.assertNotIn("MY_VAR", e.calls()[0]["env"])

    def test_a_single_auditor_still_gets_its_own_clone_copy(self):
        e = Env()
        clone = make_repo()
        e.extra["FAKE_EDIT_CLAUDE"] = "{CWD}/../clone/node_modules/jest/index.js"
        e.run("codex", ["--clone", clone, "--untrusted"])
        call = e.calls()[0]
        self.assertIn(os.path.join(e.out, "opus", "clone"), [os.path.realpath(a) for a in call["argv"]] + call["argv"])
        self.assertNotIn(clone, call["argv"])
        self.assertTrue(os.path.exists(os.path.join(e.out, "opus", "clone", "node_modules", "jest", "index.js")))
        self.assertFalse(os.path.exists(os.path.join(clone, "node_modules")))
        self.assertEqual(e.status("opus"), "discarded (clone copy changed)")

    def test_two_auditors_each_get_a_copy(self):
        e = Env()
        clone = make_repo()
        e.run("claude", ["--clone", clone])
        for short in ("astra", "argon"):
            self.assertTrue(os.path.isdir(os.path.join(e.out, short, "clone")))

    def test_an_inherited_git_dir_does_not_switch_the_leak_check_off(self):
        e = Env()
        with open(os.path.join(e.bundle, "leak.txt"), "w") as fh:
            fh.write("see %s/a.txt\n" % e.repo)
        e.extra["GIT_DIR"] = os.path.join(TMP, "nonexistent")
        p = e.run("claude")
        self.assertEqual(p.returncode, 2)
        self.assertIn("names the real repository", p.stderr)

    def test_a_target_outside_a_repository_is_audited_not_discarded(self):
        e = Env()
        p = e.run("claude", [])
        self.assertEqual(p.returncode, 0)
        cmd = [PY, "-I", CA, "run", "--harness", "claude", "--bundle", e.bundle, "--prompt-template", e.template, "--out", tempfile.mkdtemp(dir=TMP)]
        p = subprocess.run(cmd, env=e.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("astra (codex): ok", p.stdout)
        plain = tempfile.mkdtemp(dir=TMP)
        p = subprocess.run(cmd + ["--repo", plain], env=e.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("argon (agy): ok", p.stdout)

    def test_copies_share_no_inodes_with_the_clone(self):
        e = Env()
        clone = make_repo()
        e.run("claude", ["--clone", clone])
        head = os.path.join(".git", "HEAD")
        self.assertNotEqual(os.stat(os.path.join(clone, head)).st_ino, os.stat(os.path.join(e.out, "astra", "clone", head)).st_ino)
        for dirpath, _, files in os.walk(os.path.join(e.out, "astra", "clone", ".git", "objects")):
            for n in files:
                self.assertEqual(os.stat(os.path.join(dirpath, n)).st_nlink, 1)

    def test_an_unreadable_clone_state_is_never_clean(self):
        e = Env()
        plain = tempfile.mkdtemp(dir=TMP)
        p = e.run("claude", ["--clone", plain])
        self.assertEqual(p.returncode, 2)
        self.assertTrue(e.status("astra").startswith("discarded (state unreadable)"))

    def test_old_auditor_output_is_cleared(self):
        e = Env()
        out = tempfile.mkdtemp(dir=TMP)
        os.makedirs(os.path.join(out, "astra"))
        stale = os.path.join(out, "astra", "stale.txt")
        with open(stale, "w") as fh:
            fh.write("stale")
        e.run("claude", out=out)
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(os.path.join(out, "astra", "audit.md")))

    def test_sigterm_kills_the_auditors_and_still_writes_the_summary(self):
        e = Env()
        pidfile = os.path.join(TMP, "sig-%d" % time.time_ns())
        e.extra.update(FAKE_MODE_CODEX="sleep", FAKE_PIDFILE=pidfile)
        out = tempfile.mkdtemp(dir=TMP)
        cmd = [PY, "-I", CA, "run", "--harness", "claude", "--bundle", e.bundle, "--prompt-template", e.template,
               "--out", out, "--repo", e.repo, "--timeout", "600"]
        proc = subprocess.Popen(cmd, env=e.env(), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.time() + 20
        while time.time() < end and not os.path.exists(pidfile):
            time.sleep(0.1)
        self.assertTrue(os.path.exists(pidfile))
        time.sleep(0.3)
        pid = int(read(pidfile))
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=60)
        self.assertTrue(os.path.exists(os.path.join(out, "summary.json")))
        self.assertTrue(read(os.path.join(out, "astra", "status")).startswith("interrupted"))
        end = time.time() + 10
        while time.time() < end:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
        with self.assertRaises(OSError):
            os.kill(pid, 0)


DAEMONIZE = (
    "import os, sys\n"
    "if os.fork():\n    sys.exit(0)\n"
    "os.setsid()\n"
    "if os.fork():\n    sys.exit(0)\n"
    "os.execv(sys.argv[1], sys.argv[1:])\n"
)


class Harness(unittest.TestCase):
    def under(self, name, claudecode):
        """Runs `harness` as a child of a copy of sh called NAME, detached so no real harness is an ancestor."""
        if not ps_usable():
            self.skipTest("ps is not executable here (the nix build sandbox); run the suite outside it")
        d = tempfile.mkdtemp(dir=TMP)
        link = os.path.join(d, name)
        shutil.copy2(os.path.realpath(shutil.which("sh")), link)
        done = os.path.join(d, "answer")
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)
        if claudecode:
            env["CLAUDECODE"] = "1"
        cmd = '"%s" -I "%s" harness > "%s.tmp"; mv "%s.tmp" "%s"' % (PY, CA, done, done, done)
        subprocess.run([PY, "-c", DAEMONIZE, link, "-c", cmd], env=env, check=True)
        end = time.time() + 20
        while time.time() < end and not os.path.exists(done):
            time.sleep(0.1)
        return read(done).strip()

    def test_nearest_ancestor_wins_over_claudecode(self):
        self.assertEqual(self.under("codex", True), "codex")

    def test_wrapped_names(self):
        self.assertEqual(self.under(".agy-wrapped", True), "agy")
        self.assertEqual(self.under("antigravity-cli", False), "agy")
        self.assertEqual(self.under("codex-aarch64-apple-darwin", False), "codex")

    def test_env_fallback_and_unknown(self):
        self.assertEqual(self.under("sh", True), "claude")
        self.assertEqual(self.under("sh", False), "unknown")


class Spawn(unittest.TestCase):
    def test_codex_runs_with_astra_high(self):
        e = Env()
        prompt = os.path.join(TMP, "lens-%d.md" % time.time_ns())
        with open(prompt, "w") as fh:
            fh.write("Review this.\n")
        out = os.path.join(tempfile.mkdtemp(dir=TMP), "lens.md")
        work = tempfile.mkdtemp(dir=TMP)
        p = subprocess.run([PY, "-I", CA, "spawn", "--harness", "codex", "--prompt", prompt, "--out", out, "--workdir", work],
                           env=e.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        argv = e.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-6-astra")
        self.assertIn('model_reasoning_effort="high"', argv)
        self.assertEqual(argv[argv.index("-C") + 1], work)
        self.assertEqual(read(out), "AUDIT-OK from codex")
        self.assertEqual(read(out + ".status").strip(), "ok")


if __name__ == "__main__":
    unittest.main()
