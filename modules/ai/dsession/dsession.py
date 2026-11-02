"""dsession: start or resume Codex, Claude Code or agy with linked directories loaded.

Usage:
    dsession new    [--dir PATH]... [--context FILE] -- CLIENT [ARGS...]
    dsession resume ID [--dir PATH]... [--context FILE] -- CLIENT [ARGS...]
    dsession trust  [--dir PATH]...

CLIENT is codex, claude or agy; ARGS ride through to it verbatim. A wrapper listed
in $XDG_CONFIG_HOME/dsession/config.json, an argv ending in one of those clients,
runs that client through its prefix. Without --dir,
DSESSION_DIRS (a JSON array of strings) is the directory list. Codex runs on
an overlay CODEX_HOME under /tmp/dsession-<user> that links the real home and
generates AGENTS.md, hooks.json and skills/ from it plus the linked
directories, and agents/ when a linked directory has Claude agents, rendered
by codex-agent-toml beside the global ones. Claude runs on its real home
with --add-dir, a generated --settings and --append-system-prompt; a linked
directory's Claude hooks are included only after `dsession trust` recorded them. agy runs on its real home
with one --add-dir per linked directory, which it reads natively, plus an
overlay folder holding the directories' Claude agents rendered by agy-agent-md.
A resume of an agy conversation with no .db under ~/.gemini exits 1, since agy would start a new one.
--context FILE is text the session is born with: Claude gets it in
--append-system-prompt, Codex in -c developer_instructions=; agy in an
AGENTS.md inside an overlay folder added with --add-dir. DSESSION_ROOT replaces
the overlay root; it is the test seam. Exit codes: 2 usage, 1 overlay failure, 127
client not on PATH.
"""

import argparse
import contextlib
import copy
import fcntl
import getpass
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib

USAGE = "usage: dsession new|resume ID [--dir PATH]... [--context FILE] -- CLIENT [ARGS...] | trust [--dir PATH]..."
GENERATED = ("AGENTS.md", "skills", "hooks.json", "agents")
IGNORED = ("AGENTS.override.md",)
SCRATCH = ("AGENTS.md.tmp", "hooks.json.tmp")
SKILLS_PREFIX = "skills."
ADAPTERS = ("codex", "claude", "agy")
AGY_RENDERER = "agy-agent-md"
CODEX_RENDERER = "codex-agent-toml"
AGENTS_PREFIX = "agents."
VERSIONED = (SKILLS_PREFIX, AGENTS_PREFIX)
AGENTS_MD_LIMIT = 32 * 1024
CONTEXT_LIMIT = 64 * 1024
AGY_CONTEXT_LIMIT = 24 * 1024
AGY_CONTEXT_DIR = "agy-context"
AGY_CONVERSATIONS = "~/.gemini/antigravity-cli/conversations"
IMPORT_RE = re.compile(r"^@\S", re.MULTILINE)
HOOK_KEY_RE = re.compile(r"([a-z_]+):([0-9]+):([0-9]+)")
EVENT_LABELS = {
    "pre_tool_use": "PreToolUse",
    "permission_request": "PermissionRequest",
    "post_tool_use": "PostToolUse",
    "pre_compact": "PreCompact",
    "post_compact": "PostCompact",
    "session_start": "SessionStart",
    "session_end": "SessionEnd",
    "user_prompt_submit": "UserPromptSubmit",
    "subagent_start": "SubagentStart",
    "subagent_stop": "SubagentStop",
    "stop": "Stop",
    "interrupt": "Interrupt",
}


class Refused(Exception):
    pass


def warn(msg):
    sys.stderr.write("dsession: " + msg + "\n")


def usage_error(msg):
    warn(msg + "; " + USAGE)
    raise SystemExit(2)


def parse_args(argv):
    argv = list(argv)
    if not argv or argv[0] not in ("new", "resume", "trust"):
        usage_error("expected new, resume or trust")
    verb = argv[0]
    i = 1
    session_id = None
    if verb == "resume":
        if i >= len(argv) or argv[i].startswith("-"):
            usage_error("resume needs a session id")
        session_id = argv[i]
        i += 1
    dirs = []
    context = None
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            break
        if arg == "--dir":
            if i + 1 >= len(argv):
                usage_error("--dir needs a path")
            dirs.append(argv[i + 1])
            i += 2
        elif arg.startswith("--dir="):
            dirs.append(arg[len("--dir="):])
            i += 1
        elif arg == "--context" or arg.startswith("--context="):
            if verb == "trust":
                usage_error("trust takes no context")
            if arg == "--context":
                if i + 1 >= len(argv):
                    usage_error("--context needs a path")
                value = argv[i + 1]
                i += 2
            else:
                value = arg[len("--context="):]
                i += 1
            if not value:
                usage_error("--context needs a path")
            if context is not None:
                usage_error("--context given twice")
            context = value
        else:
            usage_error("unexpected argument " + arg)
    if verb == "trust":
        if i < len(argv):
            usage_error("trust takes no client")
        return argparse.Namespace(verb=verb, session_id=None, dirs=dirs, context=None, client=None, passthrough=[])
    if i >= len(argv):
        usage_error("missing --")
    if i + 1 >= len(argv):
        usage_error("missing client after --")
    return argparse.Namespace(
        verb=verb,
        session_id=session_id,
        dirs=dirs,
        context=context,
        client=argv[i + 1],
        passthrough=argv[i + 2:],
    )


def dirs_from_env():
    raw = os.environ.get("DSESSION_DIRS", "")
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except ValueError:
        usage_error("DSESSION_DIRS is not a JSON array of strings")
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        usage_error("DSESSION_DIRS is not a JSON array of strings")
    return value


def resolve_dirs(raw, cwd):
    seen = []
    for entry in raw:
        path = os.path.expanduser(entry)
        if not os.path.isabs(path):
            path = os.path.join(cwd, path)
        path = os.path.normpath(path)
        if not os.path.isdir(path):
            warn("skipping missing directory " + path)
            continue
        path = os.path.realpath(path)
        if path not in seen:
            seen.append(path)
    return seen


def overlay_root():
    root = os.environ.get("DSESSION_ROOT")
    if root:
        return os.path.abspath(os.path.expanduser(root))
    return "/tmp/dsession-" + getpass.getuser()


def base_codex_home():
    env = os.environ.get("CODEX_HOME", "")
    if env:
        real = os.path.realpath(env)
        root = os.path.realpath(overlay_root())
        if real != root and not real.startswith(root + os.sep):
            return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), ".codex")


def overlay_paths(base, dirs):
    key = "\0".join([os.path.realpath(base)] + list(dirs))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    root = os.path.join(overlay_root(), digest)
    return root, os.path.join(root, "codex"), os.path.join(root, "claude")


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def load_context(path, max_bytes=CONTEXT_LIMIT, fit_marker=False):
    try:
        text = read_text(path)
    except OSError:
        warn("skipping unreadable context " + path)
        return None
    if not text.strip():
        return None
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    limit = str(max_bytes)
    marker = "\n\n[dsession: context truncated at " + limit + " bytes]\n"
    cut = data[:max_bytes - len(marker.encode("utf-8")) if fit_marker else max_bytes]
    end = cut.rfind(b"\n")
    if end >= 0:
        cut = cut[:end]
    warn("context " + path + " truncated to " + limit + " bytes")
    return cut.decode("utf-8", errors="ignore") + marker


def write_replace(path, text):
    tmp = path + ".tmp"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def sweep(*paths):
    for path in paths:
        if os.path.lexists(path):
            remove_entry(path)


@contextlib.contextmanager
def private_umask():
    old = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(old)


def secure_dir(path, label):
    if not os.path.lexists(path):
        os.makedirs(path, mode=0o700, exist_ok=True)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
        raise Refused("refusing " + label + " " + path + " (symlink or not owned by you)")
    if not stat.S_ISDIR(info.st_mode):
        raise NotADirectoryError(path + " is not a directory")
    if stat.S_IMODE(info.st_mode) != 0o700:
        os.chmod(path, 0o700)


def linked_block(path):
    return "\n\n# Linked directory: " + path + "\n\n" + read_text(path).rstrip("\n") + "\n"


def compose_agents_md(base, dirs):
    parts = []
    base_agents = os.path.join(base, "AGENTS.md")
    if os.path.isfile(base_agents):
        parts.append(read_text(base_agents))
    for d in dirs:
        agents = os.path.join(d, "AGENTS.md")
        claude = os.path.join(d, "CLAUDE.md")
        if os.path.isfile(agents):
            parts.append(linked_block(agents))
        elif os.path.isfile(claude):
            block = linked_block(claude)
            if IMPORT_RE.search(read_text(claude)):
                warn(claude + " has @imports Codex will not expand")
            parts.append(block)
    text = "".join(parts)
    size = len(text.encode("utf-8"))
    if size > AGENTS_MD_LIMIT:
        warn("composed AGENTS.md is " + str(size) + " bytes")
    return text


def is_skill(path):
    return os.path.isdir(path) and os.path.isfile(os.path.join(path, "SKILL.md"))


def listdir_sorted(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def pick_skills(global_roots, linked_roots):
    owners = {}
    picked = []
    for root, linked in global_roots:
        for name in listdir_sorted(root):
            if name == ".system" or name in owners:
                continue
            path = os.path.join(root, name)
            owners[name] = path
            if linked:
                picked.append((name, path))
    for root in linked_roots:
        for name in listdir_sorted(root):
            path = os.path.join(root, name)
            if name == ".system" or not is_skill(path):
                continue
            if name in owners:
                if os.path.realpath(path) != os.path.realpath(owners[name]):
                    warn("skill " + name + " from " + path + " dropped: already provided by " + owners[name])
                continue
            owners[name] = path
            picked.append((name, path))
    return picked


def collect_skills(base, dirs):
    home = os.path.expanduser("~")
    global_roots = [
        (os.path.join(base, "skills"), True),
        (os.path.join(home, ".agents", "skills"), False),
    ]
    linked_roots = []
    for d in dirs:
        linked_roots.append(os.path.join(d, ".agents", "skills"))
        linked_roots.append(os.path.join(d, ".claude", "skills"))
    return pick_skills(global_roots, linked_roots)


def claude_skill_warnings(dirs):
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    pick_skills(
        [(os.path.join(config, "skills"), False)],
        [os.path.join(d, ".claude", "skills") for d in dirs],
    )


def merge_hook_groups(target, hooks):
    for event, groups in hooks.items():
        target.setdefault(event, []).extend(copy.deepcopy(g) for g in groups)


def read_hooks(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(path)
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict) or not all(isinstance(g, list) for g in hooks.values()):
        raise ValueError(path)
    return hooks


def compose_hooks(sources):
    hooks = {}
    used = []
    for src in sources:
        if not os.path.exists(src):
            continue
        try:
            groups = read_hooks(src)
        except (OSError, ValueError):
            warn("skipping unreadable " + src)
            continue
        used.append(src)
        merge_hook_groups(hooks, groups)
    return {"description": "Generated by dsession from " + ", ".join(used), "hooks": hooks}


def stray_name(base, name):
    stamp = time.strftime("%Y%m%dT%H%M%S")
    candidate = os.path.join(base, name + ".dsession-stray-" + stamp)
    n = 1
    while os.path.lexists(candidate):
        candidate = os.path.join(base, name + ".dsession-stray-" + stamp + "-" + str(n))
        n += 1
    return candidate


def adopt_stray(overlay_entry, base):
    name = os.path.basename(overlay_entry)
    dest = os.path.join(base, name)
    if not os.path.lexists(dest):
        shutil.move(overlay_entry, dest)
        warn("adopted " + name + " into " + base)
        return dest
    aside = stray_name(base, name)
    shutil.move(overlay_entry, aside)
    warn(dest + " already exists; kept the overlay copy at " + aside)
    return aside


def remove_entry(path):
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


def clear_strays(codex_home, base):
    for name in os.listdir(codex_home):
        path = os.path.join(codex_home, name)
        if name in GENERATED or name.startswith(VERSIONED):
            continue
        if name in SCRATCH:
            remove_entry(path)
            continue
        if os.path.islink(path):
            if name in IGNORED or not os.path.exists(path) or os.readlink(path) != os.path.join(base, name):
                os.unlink(path)
            continue
        adopt_stray(path, base)


def link_base(codex_home, base):
    for name in os.listdir(base):
        if name in IGNORED:
            warn("ignoring " + os.path.join(base, name) + " so the composed AGENTS.md applies")
            continue
        if name in GENERATED or name.startswith(VERSIONED):
            continue
        path = os.path.join(codex_home, name)
        target = os.path.join(base, name)
        if os.path.islink(path) and os.readlink(path) == target:
            continue
        if os.path.lexists(path):
            remove_entry(path)
        os.symlink(target, path)


def publish_link(parent, live, prefix, target, keep):
    link = live + ".tmp"
    if os.path.islink(live):
        keep.add(os.path.basename(os.readlink(live)))
    elif os.path.isdir(live):
        os.rename(live, tempfile.mkdtemp(prefix=prefix, dir=parent))
    sweep(link)
    os.symlink(target, link)
    os.replace(link, live)
    for name in os.listdir(parent):
        if name.startswith(prefix) and name not in keep:
            remove_entry(os.path.join(parent, name))


def publish_version(parent, live, prefix, version):
    publish_link(parent, live, prefix, os.path.relpath(version, os.path.dirname(live)), {os.path.basename(version)})


def build_skills(codex_home, base, dirs):
    live = os.path.join(codex_home, "skills")
    sweep(live + ".tmp")
    version = tempfile.mkdtemp(prefix=SKILLS_PREFIX, dir=codex_home)
    for name, path in collect_skills(base, dirs):
        os.symlink(path, os.path.join(version, name))
    system = os.path.join(base, "skills", ".system")
    if os.path.lexists(system):
        os.symlink(system, os.path.join(version, ".system"))
    publish_version(codex_home, live, SKILLS_PREFIX, version)


def agent_files(folder):
    return [(n[:-3], os.path.join(folder, n)) for n in listdir_sorted(folder) if n.endswith(".md") and os.path.isfile(os.path.join(folder, n))]


def collect_agy_agents(dirs):
    owners = {}
    for d in dirs:
        for name, path in agent_files(os.path.join(d, ".agents", "agents")):
            if name in owners and os.path.realpath(path) != os.path.realpath(owners[name]):
                warn("agent " + name + " in " + path + " collides with " + owners[name] + "; agy picks one")
            owners.setdefault(name, path)
    sources = []
    for d in dirs:
        for name, path in agent_files(os.path.join(d, ".claude", "agents")):
            if name in owners:
                if os.path.realpath(path) != os.path.realpath(owners[name]):
                    warn("agent " + name + " from " + path + " dropped: already provided by " + owners[name])
                continue
            owners[name] = path
            sources.append(path)
    return sources


def build_agy_agents(agy_dir, sources):
    renderer = shutil.which(AGY_RENDERER)
    if renderer is None:
        warn(AGY_RENDERER + " not on PATH; the linked directories' Claude agents are not loaded")
        return False
    secure_dir(agy_dir, "overlay directory")
    live = os.path.join(agy_dir, ".agents", "agents")
    secure_dir(os.path.dirname(live), "overlay directory")
    version = tempfile.mkdtemp(prefix=AGENTS_PREFIX, dir=agy_dir)
    try:
        status = subprocess.run([renderer, version] + sources).returncode
    except OSError as exc:
        warn(AGY_RENDERER + " failed: " + str(exc))
        status = 1
    if status != 0:
        warn("some linked agents were not rendered for agy")
    publish_version(agy_dir, live, AGENTS_PREFIX, version)
    return bool(os.listdir(version))


def collect_codex_agents(base_agents, dirs):
    owners = {n[:-5]: os.path.join(base_agents, n) for n in listdir_sorted(base_agents) if n.endswith(".toml")}
    sources = []
    for d in dirs:
        for name, path in agent_files(os.path.join(d, ".claude", "agents")):
            if name in owners:
                if os.path.realpath(path) != os.path.realpath(owners[name]):
                    warn("agent " + name + " from " + path + " dropped: already provided by " + owners[name])
                continue
            owners[name] = path
            sources.append(path)
    return sources


def build_codex_agents(codex_home, base, dirs):
    live = os.path.join(codex_home, "agents")
    base_agents = os.path.join(base, "agents")
    sources = collect_codex_agents(base_agents, dirs)
    renderer = shutil.which(CODEX_RENDERER) if sources else None
    if sources and renderer is None:
        warn(CODEX_RENDERER + " not on PATH; the linked directories' Claude agents are not loaded")
    if renderer is None:
        # The base folder itself, so an agent a plugin writes mid-session lands in the real home.
        if os.path.lexists(base_agents):
            publish_link(codex_home, live, AGENTS_PREFIX, base_agents, set())
        else:
            sweep(live, *(os.path.join(codex_home, n) for n in os.listdir(codex_home) if n.startswith(AGENTS_PREFIX)))
        return
    version = tempfile.mkdtemp(prefix=AGENTS_PREFIX, dir=codex_home)
    for name in listdir_sorted(base_agents):
        os.symlink(os.path.join(base_agents, name), os.path.join(version, name))
    # Rendered apart from the links: a frontmatter name can differ from its file name,
    # and writing through a link would overwrite the base agent it points at.
    scratch = tempfile.mkdtemp(prefix=AGENTS_PREFIX, dir=codex_home)
    try:
        status = subprocess.run([renderer, scratch] + sources).returncode
    except OSError as exc:
        warn(CODEX_RENDERER + " failed: " + str(exc))
        status = 1
    if status != 0:
        warn("some linked agents were not rendered for Codex")
    for name in listdir_sorted(scratch):
        dest = os.path.join(version, name)
        if os.path.lexists(dest):
            warn("rendered agent " + name + " dropped: already provided by " + os.readlink(dest))
        else:
            os.rename(os.path.join(scratch, name), dest)
    remove_entry(scratch)
    publish_version(codex_home, live, AGENTS_PREFIX, version)


def build_agy_context(parent, source, text):
    secure_dir(parent, "overlay directory")
    digest = hashlib.sha256(os.path.realpath(source).encode("utf-8")).hexdigest()[:16]
    folder = os.path.join(parent, digest)
    secure_dir(folder, "overlay directory")
    write_replace(os.path.join(folder, "AGENTS.md"), text)
    return os.path.realpath(folder)


class OverlayLock:
    def __init__(self, root, name="lock"):
        self.path = os.path.join(root, name)
        self.fd = None

    def __enter__(self):
        self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.fchmod(self.fd, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def secure_overlay(root):
    secure_dir(overlay_root(), "overlay root")
    secure_dir(root, "overlay directory")


def toml_string(value):
    out = []
    for ch in value:
        if ch in ("\\", '"'):
            out.append("\\" + ch)
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def base_hook_trust(state, base):
    prefixes = []
    for spelling in (os.path.realpath(base), os.path.abspath(base)):
        prefix = os.path.join(spelling, "hooks.json") + ":"
        if prefix not in prefixes:
            prefixes.append(prefix)
    found = []
    for key, entry in state.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("trusted_hash"), str):
            continue
        for prefix in prefixes:
            match = HOOK_KEY_RE.fullmatch(key[len(prefix):]) if key.startswith(prefix) else None
            if match:
                found.append((match.group(1), int(match.group(2)), int(match.group(3)), entry["trusted_hash"]))
                break
    return found


def trust_to_seed(state, base, base_hooks, composed, codex_home):
    seeded = {}
    for label, group, handler, digest in base_hook_trust(state, base):
        event = EVENT_LABELS.get(label)
        base_groups = base_hooks.get(event, [])
        groups = composed.get(event, [])
        if event is None or group >= len(base_groups) or group >= len(groups):
            continue
        if json.dumps(groups[group]) != json.dumps(base_groups[group]):
            continue
        handlers = base_groups[group].get("hooks") if isinstance(base_groups[group], dict) else None
        if not isinstance(handlers, list) or handler >= len(handlers):
            continue
        key = "%s:%s:%d:%d" % (os.path.join(codex_home, "hooks.json"), label, group, handler)
        if key not in state and key not in seeded:
            seeded[key] = digest
    return seeded


def replace_bytes(path, data, mode):
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".dsession", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)


def parse_toml(data):
    return tomllib.loads(data.decode("utf-8"))


def read_base_hooks(path):
    try:
        return read_hooks(path)
    except (OSError, ValueError):
        return {}


def seed_hook_trust(base, codex_home, base_hooks, composed):
    with OverlayLock(overlay_root(), "hooks-trust.lock"):
        seed_hook_trust_locked(base, codex_home, base_hooks, composed)


def seed_hook_trust_locked(base, codex_home, base_hooks, composed):
    config = os.path.realpath(os.path.join(base, "config.toml"))
    try:
        with open(config, "rb") as handle:
            original = handle.read()
        hooks = parse_toml(original).get("hooks", {})
        state = hooks.get("state", {}) if isinstance(hooks, dict) else None
        if not isinstance(state, dict):
            raise ValueError(config)
        mode = stat.S_IMODE(os.stat(config).st_mode)
    except (OSError, ValueError):
        warn("not seeding hook trust (config.toml unreadable)")
        return
    seeded = trust_to_seed(state, base, base_hooks, composed, codex_home)
    if not seeded:
        return
    blocks = "".join("\n[hooks.state.%s]\ntrusted_hash = %s\n" % (toml_string(k), toml_string(v)) for k, v in seeded.items())
    replace_bytes(config, original + blocks.encode("utf-8"), mode)
    try:
        with open(config, "rb") as handle:
            parse_toml(handle.read())
    except (OSError, ValueError):
        replace_bytes(config, original, mode)
        raise Refused("could not seed hook trust in " + config)
    warn("seeded trust for %d global hooks into %s" % (len(seeded), codex_home))


def regenerate_codex(base, dirs):
    root, codex_home, _ = overlay_paths(base, dirs)
    with private_umask():
        secure_overlay(root)
        with OverlayLock(root):
            secure_dir(codex_home, "overlay directory")
            sweep(os.path.join(root, "dirs.tmp"))
            clear_strays(codex_home, base)
            link_base(codex_home, base)
            write_replace(os.path.join(codex_home, "AGENTS.md"), compose_agents_md(base, dirs))
            base_hooks_path = os.path.join(base, "hooks.json")
            sources = [base_hooks_path] + [os.path.join(d, ".codex", "hooks.json") for d in dirs]
            composed = compose_hooks(sources)
            write_replace(os.path.join(codex_home, "hooks.json"), json.dumps(composed, indent=2, sort_keys=False) + "\n")
            build_skills(codex_home, base, dirs)
            build_codex_agents(codex_home, base, dirs)
            write_replace(os.path.join(root, "dirs"), "".join(d + "\n" for d in dirs))
            real_home = os.path.realpath(codex_home)
            base_hooks = read_base_hooks(base_hooks_path)
            if base_hooks:
                seed_hook_trust(base, real_home, base_hooks, composed["hooks"])
    return real_home


def split_settings(passthrough):
    rest = []
    values = []
    i = 0
    while i < len(passthrough):
        arg = passthrough[i]
        if arg == "--settings" and i + 1 < len(passthrough):
            values.append(passthrough[i + 1])
            i += 2
        elif arg.startswith("--settings="):
            values.append(arg[len("--settings="):])
            i += 1
        else:
            rest.append(arg)
            i += 1
    return rest, values


def split_prompts(passthrough):
    rest = []
    texts = []
    i = 0
    while i < len(passthrough):
        arg = passthrough[i]
        if arg in ("--append-system-prompt", "--append-system-prompt-file") and i + 1 < len(passthrough):
            value = passthrough[i + 1]
            i += 2
        elif arg.startswith("--append-system-prompt=") or arg.startswith("--append-system-prompt-file="):
            arg, value = arg.split("=", 1)
            i += 1
        else:
            rest.append(arg)
            i += 1
            continue
        if arg == "--append-system-prompt":
            texts.append(value)
            continue
        try:
            texts.append(read_text(value))
        except OSError:
            warn("ignoring unreadable --append-system-prompt-file " + value)
    return rest, texts


def has_developer_instructions(passthrough):
    for i, arg in enumerate(passthrough):
        if arg in ("-c", "--config") and i + 1 < len(passthrough):
            value = passthrough[i + 1]
        elif arg.startswith("-c=") or arg.startswith("--config="):
            value = arg.split("=", 1)[1]
        else:
            continue
        if re.match(r"\s*developer_instructions\s*=", value):
            return True
    return False


def load_settings_value(v):
    try:
        if os.path.isfile(v):
            with open(v, encoding="utf-8") as handle:
                data = json.load(handle)
        else:
            data = json.loads(v)
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        warn("ignoring unreadable --settings " + v)
        return None
    return data


def trust_path():
    state = os.environ.get("XDG_STATE_HOME", "")
    if not os.path.isabs(state):
        state = os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(state, "dsession", "claude-hooks.json")


def load_trust():
    path = trust_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        warn("ignoring unreadable " + path)
        return {}
    return data


def save_trust(state):
    path = trust_path()
    folder = os.path.dirname(path)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".claude-hooks.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)


def hooks_digest(hooks):
    canonical = json.dumps(hooks, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def linked_claude_hooks(d):
    path = os.path.join(d, ".claude", "settings.json")
    if not os.path.exists(path):
        return {}
    try:
        return read_hooks(path)
    except (OSError, ValueError):
        warn("skipping unreadable " + path)
        return {}


def confirm(prompt):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    if not sys.stdin.isatty():
        sys.stdout.write("\n")
        warn("stdin is not a terminal; declining")
        return False
    return sys.stdin.readline().strip() in ("y", "Y")


def trust(dirs):
    if not dirs:
        warn("no directories to trust")
    for d in dirs:
        hooks = linked_claude_hooks(d)
        if not hooks:
            continue
        digest = hooks_digest(hooks)
        if load_trust().get(d) == digest:
            warn("Claude hooks in " + d + " are already trusted")
            continue
        sys.stdout.write("Claude hooks in " + d + ":\n" + json.dumps(hooks, indent=2, sort_keys=True) + "\n")
        if not confirm("Trust these hooks? [y/N] "):
            warn("left Claude hooks in " + d + " untrusted")
            continue
        state = load_trust()
        state[d] = digest
        save_trust(state)
        warn("trusted Claude hooks in " + d)
    return 0


def compose_claude_settings(dirs, extra, trusted):
    hooks = {}
    for d in dirs:
        groups = linked_claude_hooks(d)
        if not groups:
            continue
        if trusted.get(d) != hooks_digest(groups):
            warn("skipping untrusted Claude hooks in " + d + " (run: dsession trust --dir " + d + ")")
            continue
        merge_hook_groups(hooks, groups)
    settings = {"hooks": hooks} if hooks else {}
    for value in extra:
        for key, item in value.items():
            if key == "hooks" and isinstance(item, dict):
                merge_hook_groups(settings.setdefault("hooks", {}), {e: g for e, g in item.items() if isinstance(g, list)})
            else:
                settings[key] = copy.deepcopy(item)
    return settings or None


def append_prompt(dirs):
    blocks = []
    for d in dirs:
        agents = os.path.join(d, "AGENTS.md")
        if os.path.isfile(agents) and not os.path.isfile(os.path.join(d, "CLAUDE.md")):
            blocks.append(linked_block(agents))
    if not blocks:
        return None
    return "".join(blocks).lstrip("\n")


def claude_argv(dirs, session_id, passthrough, claude_dir, context=None):
    argv = ["claude"]
    if session_id:
        argv += ["--resume", session_id]
    for d in dirs:
        argv += ["--add-dir", d]
    rest, values = split_settings(passthrough)
    extra = [s for s in (load_settings_value(v) for v in values) if s is not None]
    settings = compose_claude_settings(dirs, extra, load_trust())
    sweep(os.path.join(claude_dir, "settings.json.tmp"))
    if settings:
        secure_dir(claude_dir, "overlay directory")
        path = os.path.join(claude_dir, "settings.json")
        write_replace(path, json.dumps(settings, indent=2) + "\n")
        argv += ["--settings", path]
    rest, prompts = split_prompts(rest)
    blocks = [b for b in [append_prompt(dirs), context] + prompts if b is not None]
    if blocks:
        argv += ["--append-system-prompt", "\n\n".join(b.rstrip("\n") for b in blocks) + "\n"]
    return argv + rest, {"CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1", "CLAUDE_CODE_NO_FLICKER": "1"}


def codex_argv(dirs, session_id, passthrough, context=None):
    argv = ["codex"]
    if session_id:
        argv += ["resume", session_id]
    for d in dirs:
        argv += ["--add-dir", d]
    if context is not None:
        argv += ["-c", "developer_instructions=" + toml_string(context)]
        if has_developer_instructions(passthrough):
            warn("pass-through developer_instructions overrides --context")
    return argv + list(passthrough)


def agy_argv(dirs, session_id, passthrough, agy_dir, context=None, context_source=None):
    argv = ["agy"]
    if session_id:
        argv += ["--conversation", session_id]
    for d in dirs:
        argv += ["--add-dir", d]
        if not os.path.isfile(os.path.join(d, "AGENTS.md")) and os.path.isfile(os.path.join(d, "CLAUDE.md")):
            warn("agy reads AGENTS.md, not CLAUDE.md, in " + d)
    sources = collect_agy_agents(dirs)
    if sources and build_agy_agents(agy_dir, sources):
        argv += ["--add-dir", os.path.realpath(agy_dir)]
    if context is not None:
        parent = os.path.join(os.path.dirname(agy_dir), AGY_CONTEXT_DIR)
        argv += ["--add-dir", build_agy_context(parent, context_source, context)]
    return argv + list(passthrough), {}


def agy_has_conversation(session_id):
    return os.path.isfile(os.path.join(os.path.expanduser(AGY_CONVERSATIONS), session_id + ".db"))


def native_argv(client, session_id, passthrough):
    if session_id is None:
        return [client] + list(passthrough)
    if client == "claude":
        return [client, "--resume", session_id] + list(passthrough)
    if client == "agy":
        return [client, "--conversation", session_id] + list(passthrough)
    return [client, "resume", session_id] + list(passthrough)


def config_path():
    config = os.environ.get("XDG_CONFIG_HOME", "")
    if not os.path.isabs(config):
        config = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(config, "dsession", "config.json")


def load_wrappers():
    path = config_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        data = None
    wrappers = data.get("wrappers", []) if isinstance(data, dict) else None
    if not isinstance(wrappers, list) or not all(
        isinstance(w, list) and len(w) > 1 and all(isinstance(a, str) for a in w) and w[-1] in ADAPTERS
        for w in wrappers
    ):
        warn("ignoring unreadable " + path)
        return []
    return [tuple(w) for w in wrappers]


def unwrap(client, passthrough):
    for wrapper in load_wrappers():
        if tuple([client] + passthrough[:len(wrapper) - 1]) == wrapper:
            return list(wrapper[:-1]), wrapper[-1], passthrough[len(wrapper) - 1:]
    return [], client, passthrough


def exec_client(argv, env_extra, prefix=()):
    argv = list(prefix) + argv
    path = shutil.which(argv[0])
    if path is None:
        warn(argv[0] + " not found on PATH")
        return 127
    env = dict(os.environ)
    env.update(env_extra)
    os.execvpe(path, argv, env)


def overlay_argv(root, build, *args):
    try:
        with private_umask():
            secure_overlay(root)
            with OverlayLock(root):
                return build(*args)
    except Refused as exc:
        warn(str(exc))
    except OSError as exc:
        warn("overlay failed: " + str(exc))
    return None


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        ns = parse_args(argv)
        raw = ns.dirs or dirs_from_env()
    except SystemExit as exc:
        return exc.code
    dirs = resolve_dirs(raw, os.getcwd())
    if ns.verb == "trust":
        try:
            return trust(dirs)
        except OSError as exc:
            warn("trust failed: " + str(exc))
            return 1
    if shutil.which(ns.client) is None:
        warn(ns.client + " not found on PATH")
        return 127
    prefix, ns.client, ns.passthrough = unwrap(ns.client, ns.passthrough)
    if ns.client not in ADAPTERS:
        if dirs:
            warn("linked directories need codex, claude or agy; " + USAGE)
            return 2
        if ns.context:
            warn("--context needs codex, claude or agy; " + USAGE)
            return 2
        if ns.session_id is not None:
            warn("resume needs codex, claude or agy; " + USAGE)
            return 2
    if ns.client == "agy" and ns.session_id is not None and not agy_has_conversation(ns.session_id):
        warn("agy conversation " + ns.session_id + " is not on this machine")
        return 1
    context = None
    if ns.context:
        context = load_context(ns.context, AGY_CONTEXT_LIMIT, True) if ns.client == "agy" else load_context(ns.context)
    if not dirs and context is None:
        return exec_client(native_argv(ns.client, ns.session_id, ns.passthrough), {}, prefix)
    base = base_codex_home()
    if ns.client == "codex":
        env_extra = {}
        if dirs:
            if not os.path.isdir(base):
                warn(base + " is not a directory")
                return 1
            try:
                env_extra["CODEX_HOME"] = regenerate_codex(base, dirs)
            except Refused as exc:
                warn(str(exc))
                return 1
            except OSError as exc:
                warn("overlay failed: " + str(exc))
                return 1
        return exec_client(codex_argv(dirs, ns.session_id, ns.passthrough, context), env_extra, prefix)
    root = overlay_paths(base, dirs)[0]
    if ns.client == "agy":
        built = overlay_argv(root, agy_argv, dirs, ns.session_id, ns.passthrough, os.path.join(root, "agy"), context, ns.context)
    else:
        claude_skill_warnings(dirs)
        built = overlay_argv(root, claude_argv, dirs, ns.session_id, ns.passthrough, os.path.join(root, "claude"), context)
    if built is None:
        return 1
    return exec_client(built[0], built[1], prefix)


if __name__ == "__main__":
    raise SystemExit(main())
