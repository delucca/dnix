#!/usr/bin/env python3
"""cross-audit: the review's cross-harness audit and headless Codex lenses, with isolation checks."""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
DIFF_METRICS = os.path.join(HERE, "diff_metrics.py")

AUDITORS = {
    "claude": ("opus", "opus (claude)"),
    "codex": ("astra", "astra (codex)"),
    "agy": ("argon", "argon (agy)"),
}
ALLOW_ENV = frozenset((
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "TERM", "SHELL", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "NIX_SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
    "ALL_PROXY", "https_proxy", "http_proxy", "no_proxy", "all_proxy", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "CODEX_HOME", "CODEX_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
))
ALLOW_ENV_PREFIXES = ("LC_", "XDG_")
IDENTITY_VARS = (
    "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_EXECPATH",
    "CLAUDE_PID", "CLAUDE_BUFFER_NAME",
)
CODEX_DISABLE = ("multi_agent", "computer_use", "browser_use", "browser_use_external", "in_app_browser", "apps")
NOT_SIGNED_IN = re.compile(r"not logged in|not signed in|login required|unauthorized|authentication", re.I)
POLICY_NOTE = "(no read-only sandbox: managed policy)"
DEFAULT_MODELS = {"claude": "opus", "codex": "gpt-6-astra", "agy": "gemini-4-argon-high"}


def die(msg):
    sys.stderr.write("cross-audit: %s\n" % msg)
    sys.exit(2)


def ps_path():
    return "/bin/ps" if os.path.exists("/bin/ps") else (shutil.which("ps") or "ps")


def normalize(comm):
    base = os.path.basename(comm.strip()).lower()
    base = base[1:] if base.startswith(".") else base
    if base.endswith("-wrapped"):
        base = base[:-len("-wrapped")]
    if base == "claude":
        return "claude"
    if base == "codex" or base.startswith("codex-"):
        return "codex"
    if base in ("agy", "antigravity", "antigravity-cli"):
        return "agy"
    if "claude" in comm.split("/")[:-1]:
        return "claude"
    return None


def detect_harness():
    pid = os.getppid()
    for _ in range(64):
        if pid <= 1:
            break
        try:
            p = subprocess.run([ps_path(), "-o", "ppid=,comm=", "-p", str(pid)], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, universal_newlines=True)
        except OSError:
            break
        line = p.stdout.strip()
        if not line:
            break
        ppid, _, comm = line.partition(" ")
        found = normalize(comm)
        if found:
            return found
        try:
            pid = int(ppid)
        except ValueError:
            break
    return "claude" if os.environ.get("CLAUDECODE") == "1" else "unknown"


SECRET_SUFFIXES = ("_KEY_CMD", "_TOKEN", "_SECRET")


def settings():
    """~/.config/ai/settings/review.json, or {} when missing or unreadable."""
    try:
        with open(os.path.expanduser("~/.config/ai/settings/review.json"), encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def pass_env_prefixes():
    """Extra env-name prefixes from passEnvPrefixes, for what a harness wrapper reads."""
    value = settings().get("passEnvPrefixes")
    return tuple(x for x in value if isinstance(x, str) and x) if isinstance(value, list) else ()


def harness_wrapper():
    """The argv prefix from harnessWrapper in ~/.config/ai/settings/review.json, or [] when unset or unusable."""
    wrapper = settings().get("harnessWrapper")
    if isinstance(wrapper, list) and wrapper and all(isinstance(x, str) and x for x in wrapper) and shutil.which(wrapper[0]):
        return wrapper
    return []


def allowed_env_name(name, extra=()):
    if name in IDENTITY_VARS or name.startswith("DMACS_") or name in ("OLDPWD", "SSH_AUTH_SOCK"):
        return False
    if name in ALLOW_ENV or name.startswith(ALLOW_ENV_PREFIXES + pass_env_prefixes()):
        return True
    return name in extra and not name.endswith(SECRET_SUFFIXES)


def child_env(cwd, needles=(), untrusted=False):
    """The auditor's environment: an allowlist, PWD set to its own cwd, and no value naming the repository."""
    extra = () if untrusted else tuple(x for x in os.environ.get("CROSS_AUDIT_PASS_ENV", "").split(",") if x)
    env = dict((k, v) for k, v in os.environ.items() if allowed_env_name(k, extra))
    if harness_wrapper():
        sock = os.environ.get("SSH_AUTH_SOCK", "")
        if not sock:
            try:
                p = subprocess.run(["/bin/launchctl", "asuser", str(os.getuid()), "/bin/launchctl", "getenv", "SSH_AUTH_SOCK"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
                sock = p.stdout.strip()
            except OSError:
                sock = ""
        if sock:
            env["SSH_AUTH_SOCK"] = sock
    if needles:
        for k in list(env):
            if any(n in env[k] for n in needles):
                if k == "PATH":
                    env[k] = os.pathsep.join(e for e in env[k].split(os.pathsep) if not any(n in e for n in needles))
                else:
                    del env[k]
    env["PWD"] = cwd
    return env


def diff_metrics(*args):
    return subprocess.run([sys.executable, "-I", DIFF_METRICS] + list(args), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)


def fingerprint(path):
    p = diff_metrics("fingerprint", "--repo", path)
    return p.stdout.strip() if p.returncode == 0 else None


def file_bytes(path):
    """Content of a regular file, the target of a link, or a type marker; never opens special files."""
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return b"link:" + os.readlink(path).encode("utf-8", "surrogateescape")
    if stat.S_ISREG(st.st_mode):
        with open(path, "rb") as fh:
            return fh.read()
    return b"special:%o" % stat.S_IFMT(st.st_mode)


def walk_entries(root, skip=()):
    """Every entry under ROOT (files, links and directories alike) as (relative path, absolute path), by lstat."""
    stack = [""] if os.path.isdir(root) else []
    while stack:
        rel = stack.pop()
        with os.scandir(os.path.join(root, rel) if rel else root) as it:
            entries = sorted(it, key=lambda e: e.name)
        for e in entries:
            sub = os.path.join(rel, e.name) if rel else e.name
            if sub in skip:
                continue
            yield sub, e.path
            if e.is_dir(follow_symlinks=False):
                stack.append(sub)


def escaping_links(root, skip=()):
    """Relative paths of links under ROOT whose target resolves outside ROOT."""
    base = os.path.realpath(root)
    out = []
    for rel, full in walk_entries(root, skip):
        if os.path.islink(full):
            target = os.path.realpath(full)
            if target != base and not target.startswith(base + os.sep):
                out.append(rel)
    return out


def tree_hash(root, skip=()):
    h = hashlib.sha256()
    for rel, full in walk_entries(root, skip):
        h.update(rel.encode("utf-8", "surrogateescape") + b"\0")
        h.update(file_bytes(full))
        h.update(b"\0")
    return h.hexdigest()


def leaks(root, needles, skip=()):
    """First entry under ROOT whose content, link target or name contains one of NEEDLES, else None."""
    for rel, full in walk_entries(root, skip):
        data = rel.encode("utf-8", "surrogateescape") + b"\0" + file_bytes(full)
        if any(x.encode() in data for x in needles):
            return full
    return None


def copy_ignore(root, links):
    """shutil.copytree ignore callback: skip special files and the links that leave ROOT."""
    skip = set(os.path.join(root, x) for x in links)

    def ignore(directory, names):
        out = []
        for n in names:
            full = os.path.join(directory, n)
            st = os.lstat(full)
            if full in skip or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)):
                out.append(n)
        return out
    return ignore


def clone_state(clone):
    """Fingerprint plus the git metadata that runs code (config, hooks, info); None when unreadable."""
    fp = fingerprint(clone)
    if fp is None:
        return None
    h = hashlib.sha256(fp.encode())
    for sub in ("config", "hooks", "info"):
        path = os.path.join(clone, ".git", sub)
        if os.path.islink(path) or os.path.isfile(path):
            h.update(file_bytes(path))
        elif os.path.isdir(path):
            h.update(tree_hash(path).encode())
    return h.hexdigest()


def refuse_fable(values):
    for v in values:
        if "fable" in str(v).lower():
            die("refusing a Fable model: %s" % v)


def launcher(name, args):
    """argv for the harness NAME, through the configured wrapper when there is one; None when it cannot start."""
    if name == "agy":
        return ["agy"] + args if shutil.which("agy") else None
    wrapper = harness_wrapper()
    if wrapper:
        return wrapper + [name] + args
    return [name] + args if shutil.which(name) else None


def codex_policy_note():
    if harness_wrapper():
        return "(sandbox state unknown: wrapped route)"
    if not shutil.which("codex"):
        return ""
    try:
        p = subprocess.run(["codex", "doctor", "--json", "-c", 'sandbox_mode="read-only"'], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, universal_newlines=True, timeout=60)
        fs = json.loads(p.stdout)["checks"]["sandbox.helpers"]["details"]["filesystem sandbox"]
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return "(sandbox state unknown)"
    return "" if "read-only" in str(fs) else POLICY_NOTE


def codex_args(out_file, workdir, model, sandbox=False):
    a = ["exec"]
    for f in CODEX_DISABLE:
        a += ["--disable", f]
    if sandbox:
        a += ["-s", "read-only"]
    return a + ["--skip-git-repo-check", "--json", "-o", out_file, "-m", model,
                "-c", 'model_reasoning_effort="high"', "-C", workdir]


def audit_args(harness, prompt, bundle, out_dir, clone, models):
    if harness == "codex":
        head = codex_args(os.path.join(out_dir, "audit.md"), bundle, models["codex"], sandbox=True)
        return head + (["--add-dir", clone] if clone else []) + [prompt]
    if harness == "claude":
        a = ["-p", prompt, "--model", models["claude"], "--effort", "high", "--output-format", "json", "--restricted",
             "--strict-mcp-config", "--tools", "Read,Grep,Glob", "--disallowedTools", "Agent", "SendMessage",
             "ListAgents", "--disable-slash-commands", "--permission-mode", "dontAsk", "--permission-prompts", "none"]
        return a + (["--add-dir", clone] if clone else [])
    a = ["-p", prompt, "--model", models["agy"], "--output-format", "json", "--sandbox",
         "--dangerously-skip-permissions", "--print-timeout", "0"]
    return a + (["--add-dir", clone] if clone else [])


def parse_json(text):
    try:
        return json.loads(text)
    except ValueError:
        pass
    for line in reversed(text.strip().split("\n")):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def extract_response(harness, out_dir):
    if harness == "codex":
        return read_text(os.path.join(out_dir, "audit.md"))
    data = parse_json(read_text(os.path.join(out_dir, "stdout.log")))
    if isinstance(data, list):
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), {})
    if not isinstance(data, dict):
        return ""
    return str(data.get("result" if harness == "claude" else "response") or "")


def classify(harness, rc, out_dir, note):
    if rc == 124:
        status = "timeout"
    else:
        err = read_text(os.path.join(out_dir, "stderr.log"))
        if rc != 0:
            if NOT_SIGNED_IN.search(err):
                status = "unavailable (%s not signed in)" % harness
            else:
                last = [l for l in err.strip().split("\n") if l.strip()]
                status = "failed (exit %d: %s)" % (rc, last[-1] if last else "no stderr")
        else:
            text = extract_response(harness, out_dir)
            if text.strip():
                with open(os.path.join(out_dir, "audit.md"), "w", encoding="utf-8") as fh:
                    fh.write(text)
                status = "ok"
            else:
                status = "empty (no response)"
    return status + (" " + note if note and harness == "codex" else "")


class Interrupted(Exception):
    def __init__(self, sig):
        Exception.__init__(self, "interrupted by signal %d" % sig)
        self.sig = sig


def raise_interrupted(sig, _frame):
    raise Interrupted(sig)


def catch_termination():
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, raise_interrupted)


def ignore_termination():
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)


def start(argv, cwd, out_dir, seconds, env):
    cmd = [sys.executable, "-I", DIFF_METRICS, "timebox", "--seconds", str(seconds), "--cwd", cwd,
           "--stdout", os.path.join(out_dir, "stdout.log"), "--stderr", os.path.join(out_dir, "stderr.log"), "--"] + argv
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def write_status(out_dir, status):
    with open(os.path.join(out_dir, "status"), "w", encoding="utf-8") as fh:
        fh.write(status + "\n")


def cmd_harness(args):
    print(detect_harness())
    return 0


def repo_opens(repo):
    """True when git opens REPO, False when it is not a repository; any other failure is an error."""
    env = dict((k, v) for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"))
    try:
        p = subprocess.run(["git", "-C", repo, "rev-parse", "--git-dir"], env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, universal_newlines=True)
    except OSError as e:
        die("cannot run git to open --repo: %s" % e)
    if p.returncode == 0:
        return True
    if "not a git repository" in p.stderr:
        return False
    die("git cannot open --repo %s: %s" % (repo, p.stderr.strip().split("\n")[-1]))


def cmd_run(args):
    models = {"claude": args.claude_model, "codex": args.codex_model, "agy": args.agy_model}
    refuse_fable(models.values())
    harness = detect_harness() if args.harness == "auto" else args.harness
    names = [h for h in ("claude", "codex", "agy") if h != harness]
    repo = os.path.realpath(args.repo) if args.repo else None
    in_repo = bool(repo) and repo_opens(repo)
    needles = sorted(set([repo, os.path.abspath(args.repo)])) if repo else []
    out = os.path.abspath(args.out)
    bundle = os.path.abspath(args.bundle)
    clone = os.path.abspath(args.clone) if args.clone else None
    os.makedirs(out, exist_ok=True)
    hit = leaks(bundle, needles)
    if hit:
        die("the bundle names the real repository: %s" % hit)
    bad = escaping_links(bundle)
    if bad:
        die("the bundle has a link that leaves it: %s" % bad[0])
    hit = leaks(os.path.join(clone, ".git"), needles, skip=("objects",)) if clone else None
    if hit:
        die("the clone names the real repository: %s" % hit)
    with open(args.prompt_template, encoding="utf-8") as fh:
        template = fh.read()
    note = codex_policy_note() if "codex" in names else ""
    plans = []
    summary = []
    off = os.environ.get("REVIEW_CROSS_AUDIT") == "off"
    clone_links = escaping_links(clone, skip=(os.path.join(".git", "objects"),)) if clone else []
    for h in names:
        short, label = AUDITORS[h]
        d = os.path.join(out, short)
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        entry = {"auditor": label, "command": None, "status": None, "seconds": 0, "policy_note": note if h == "codex" else ""}
        summary.append(entry)
        if off:
            entry["status"] = "skipped (REVIEW_CROSS_AUDIT=off)"
            write_status(d, entry["status"])
            continue
        if args.untrusted and h != "claude":
            entry["status"] = "skipped (untrusted target, no sandbox)"
            write_status(d, entry["status"])
            continue
        copy = os.path.join(d, "bundle")
        shutil.copytree(bundle, copy, symlinks=True, ignore=copy_ignore(bundle, []))
        own_clone = None
        if clone:
            own_clone = os.path.join(d, "clone")
            shutil.copytree(clone, own_clone, symlinks=True, ignore=copy_ignore(clone, clone_links))
        prompt = template.replace("{BUNDLE}", copy).replace("{CLONE}", own_clone or "none")
        if any(n in prompt for n in needles):
            die("the rendered prompt names the real repository")
        with open(os.path.join(d, "prompt.md"), "w", encoding="utf-8") as fh:
            fh.write(prompt)
        argv = launcher(h, audit_args(h, prompt, copy, d, own_clone, models))
        if argv is None:
            entry["status"] = "unavailable (%s not installed)" % h
            write_status(d, entry["status"])
            continue
        if any(n in a for a in argv for n in needles):
            die("a command line names the real repository")
        entry["command"] = [a if a != prompt else "<prompt.md>" for a in argv]
        plans.append((h, short, d, copy, own_clone, argv, entry))

    def state():
        return {"repo": fingerprint(repo) if in_repo else "no repository", "clone": clone_state(clone) if clone else None,
                "bundles": dict((p[1], tree_hash(p[3])) for p in plans),
                "copies": dict((p[1], clone_state(p[4])) for p in plans if p[4])}

    before = state()
    t0 = time.time()
    codes = {}
    interrupted = None
    catch_termination()
    procs = []
    try:
        for p in plans:
            procs.append((p, start(p[5], p[3], p[2], args.timeout, child_env(p[3], needles, args.untrusted))))
        for p, proc in procs:
            codes[p[1]] = proc.wait()
            p[6]["seconds"] = round(time.time() - t0, 1)
    except Interrupted as e:
        interrupted = e.sig
        ignore_termination()
        for p, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for p, proc in procs:
            try:
                codes[p[1]] = proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                codes[p[1]] = proc.wait()
            p[6]["seconds"] = round(time.time() - t0, 1)
    ignore_termination()
    after = state()
    unreadable = any(v is None for st in (before, after) for v in
                     [st["repo"], st["clone"] if clone else 0] + list(st["copies"].values()))
    repo_changed = before["repo"] != after["repo"]
    clone_changed = bool(clone) and before["clone"] != after["clone"]
    for h, short, d, copy, own_clone, argv, entry in plans:
        status = classify(h, codes.get(short, 1), d, note)
        if interrupted:
            status = "interrupted (signal %d)" % interrupted
        elif unreadable:
            status = "discarded (state unreadable)"
        elif repo_changed:
            status = "discarded (repository changed)"
        elif before["bundles"][short] != after["bundles"][short]:
            status = "discarded (bundle changed)"
        elif clone_changed:
            status = "discarded (clone changed)"
        elif own_clone and before["copies"][short] != after["copies"][short]:
            status = "discarded (clone copy changed)"
        entry["status"] = status
        write_status(d, status)
    integrity = {
        "repo_changed": repo_changed, "clone_changed": clone_changed,
        "bundles_changed": sorted(k for k in before["bundles"] if before["bundles"][k] != after["bundles"][k]),
        "clone_copies_changed": sorted(k for k in before["copies"] if before["copies"][k] != after["copies"][k]),
        "interrupted": interrupted, "state_unreadable": unreadable, "escaping_links_skipped": clone_links,
        "repo_fingerprint": {"before": before["repo"], "after": after["repo"]},
        "clone_fingerprint": {"before": before["clone"], "after": after["clone"]},
    }
    for name, data in (("summary.json", summary), ("integrity.json", integrity)):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True, indent=2)
            fh.write("\n")
    for e in summary:
        print("%s: %s" % (e["auditor"], e["status"]))
    return 128 + interrupted if interrupted else (2 if unreadable else 0)


def cmd_spawn(args):
    if args.harness != "codex":
        die("spawn supports codex only")
    model = args.codex_model
    refuse_fable([model])
    with open(args.prompt, encoding="utf-8") as fh:
        prompt = fh.read()
    out = os.path.abspath(args.out)
    work = os.path.abspath(args.workdir)
    argv = launcher("codex", codex_args(out, work, model) + [prompt])
    status_file = out + ".status"
    d = os.path.dirname(out)
    os.makedirs(d, exist_ok=True)
    if argv is None:
        status = "unavailable (codex not installed)"
    else:
        logs = os.path.join(d, os.path.basename(out) + ".logs")
        os.makedirs(logs, exist_ok=True)
        catch_termination()
        proc = start(argv, work, logs, args.timeout, child_env(work))
        try:
            rc = proc.wait()
            status = classify_spawn(rc, logs, out)
        except Interrupted as e:
            ignore_termination()
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            status = "interrupted (signal %d)" % e.sig
    with open(status_file, "w", encoding="utf-8") as fh:
        fh.write(status + "\n")
    print(status)
    return 0


def classify_spawn(rc, logs, out):
    if rc == 124:
        return "timeout"
    err = read_text(os.path.join(logs, "stderr.log"))
    if rc != 0:
        if NOT_SIGNED_IN.search(err):
            return "unavailable (codex not signed in)"
        last = [l for l in err.strip().split("\n") if l.strip()]
        return "failed (exit %d: %s)" % (rc, last[-1] if last else "no stderr")
    if not read_text(out).strip():
        return "empty (no response)"
    return "ok"


def build_parser():
    ap = argparse.ArgumentParser(prog="cross-audit", description=__doc__)
    sub = ap.add_subparsers(dest="verb")
    sub.required = True
    p = sub.add_parser("harness")
    p.set_defaults(fn=cmd_harness)
    p = sub.add_parser("run")
    p.add_argument("--harness", choices=("auto", "claude", "codex", "agy", "unknown"), default="auto")
    p.add_argument("--bundle", required=True)
    p.add_argument("--prompt-template", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--repo")
    p.add_argument("--clone")
    p.add_argument("--untrusted", action="store_true")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--claude-model", default=DEFAULT_MODELS["claude"])
    p.add_argument("--codex-model", default=DEFAULT_MODELS["codex"])
    p.add_argument("--agy-model", default=DEFAULT_MODELS["agy"])
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("spawn")
    p.add_argument("--harness", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--codex-model", default=DEFAULT_MODELS["codex"])
    p.set_defaults(fn=cmd_spawn)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
