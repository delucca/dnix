#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["proxmoxer==2.3.0", "requests==2.34.2"]
# ///
"""
proxmox.py -- On-demand CLI for standalone Proxmox VE nodes.

The nodes come from ~/.config/ai/settings/use-proxmox.json. Target one node per
invocation with --host NODE ($PROXMOX_NODE, else settings.defaultNode).

Two transports, auto-selected:
  - API (default): proxmoxer over HTTPS with a scoped `automation@pve` token,
    TLS verified against the pinned PVE CA. Best blast radius.
  - SSH (fallback / bootstrap / pct exec): runs pvesh|qm|pct on the node via
    the node's ssh alias + `sudo -S` (per-node password from settings.secrets). Always used for `exec`
    (no REST equivalent) and whenever the API token/CA are not yet configured.

Every operation is expressed as (verb, api_path, params). The same path drives
both backends because `pvesh <verb> <path>` maps 1:1 to the REST API.

Safety rails (see references/safety-and-gotchas.md):
  - Every mutation polls the UPID task to completion and checks exitstatus.
  - Destructive ops (destroy/stop/rollback/delsnapshot, set --delete) require --yes.
  - Mutations refuse on a locked guest; the skill NEVER auto-unlocks.
  - The target guest's node is resolved from /cluster/resources on the selected host.
  - Snapshots refuse on classic-LVM storage (no snapshot support) without --force.
  - TLS is CA-pinned; verify_ssl is never disabled.

Short results (<=4 KB) print inline; larger spill to ~/.cache/proxmox-cm/.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants / configuration
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".config" / "proxmox"

SKILL = "use-proxmox"
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import credential  # noqa: E402

SETTINGS = credential.settings(SKILL)
HOSTS: dict[str, dict[str, Any]] = SETTINGS.get("nodes") or {}
DEFAULT_HOST: str | None = SETTINGS.get("defaultNode") or next(iter(HOSTS), None)
HOST_ALIASES = {a.lower(): name for name, n in HOSTS.items() for a in n.get("aliases", [])}

# Set once from --host / $PROXMOX_NODE before any handler runs.
_TARGET: str = ""

API_PORT = 8006

# The dedicated automation identity created by `setup-token`.
AUTOMATION_USER = "automation@pve"
AUTOMATION_TOKEN = "skill"
AUTOMATION_ROLE = "ClaudeAutomation"
# Least-privilege role for VM/LXC lifecycle. Omits Sys.Modify, Permissions.Modify,
# Realm.*, Datastore.Allocate, and VM.Monitor (removed in PVE 9). Add Sys.Modify
# manually only if bridge allocation fails. See references/token-setup.md.
ROLE_PRIVS = ",".join([
    "VM.Allocate", "VM.Audit", "VM.Clone", "VM.Config.CDROM", "VM.Config.CPU",
    "VM.Config.Cloudinit", "VM.Config.Disk", "VM.Config.HWType", "VM.Config.Memory",
    "VM.Config.Network", "VM.Config.Options", "VM.PowerMgmt", "VM.Console",
    "VM.Snapshot", "VM.Snapshot.Rollback", "VM.Migrate",
    "Datastore.AllocateSpace", "Datastore.AllocateTemplate", "Datastore.Audit",
    "Sys.Audit",
])

INLINE_LIMIT = 4096
OUT_DIR = Path.home() / ".cache" / "proxmox-cm"
OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)  # per-user 0700; spills may hold sensitive data
TASK_TIMEOUT = 600          # seconds to wait for a UPID task
POLL_INTERVAL = 2

# Storage types that natively support snapshots. Classic "lvm" (not lvmthin)
# and raw-on-dir cannot snapshot -- we hard-refuse on plain lvm without --force.
SNAPSHOT_OK = {"zfspool", "rbd", "btrfs", "cephfs", "lvmthin", "zfs"}
SNAPSHOT_NEVER = {"lvm"}

_API_CACHE: Any = None        # connected ProxmoxAPI once resolved
_API_RESOLVED = False         # True once we've decided whether the API is usable
_API_DOWN = False             # set after an API call fails at runtime -> stop retrying
_SSH_PW_CACHE: str | None = None


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def resolve_host(name: str | None) -> str:
    """Map a user-supplied spelling to a configured node."""
    if not HOSTS:
        sys.exit(f"No nodes configured: set dnix.ai.skills.{SKILL}.settings.nodes.")
    if not name:
        return DEFAULT_HOST
    key = HOST_ALIASES.get(name.lower(), name.lower())
    if key not in HOSTS:
        known = ", ".join(sorted(set(list(HOSTS) + list(HOST_ALIASES))))
        sys.exit(f"Unknown host '{name}'. Known: {known}")
    return key


def _cfg() -> dict[str, Any]:
    return HOSTS[_TARGET]


def _host() -> str:
    return os.environ.get("PROXMOX_HOST") or _cfg().get("apiHost") or _TARGET


def _ssh_alias() -> str:
    return os.environ.get("PROXMOX_SSH") or _cfg().get("sshAlias") or _TARGET


def _token_key() -> str:
    """Per-node: standalone nodes mean one token and one CA each."""
    return f"{_TARGET}-token"


def _ca_file() -> Path:
    return CONFIG_DIR / _TARGET / "pve-root-ca.pem"


def _read_token() -> tuple[str, str, str] | None:
    """Return (user, token_name, token_value), or None when no usable token is configured."""
    if not (SETTINGS.get("secrets") or {}).get(_token_key()):
        return None
    try:
        raw = credential.read(SKILL, _token_key(), label=f"the {_TARGET} API token")
    except SystemExit as exc:
        sys.stderr.write(f"# {exc}\n# Using SSH.\n")
        return None
    if "=" not in raw or "!" not in raw:
        return None
    ident, _, value = raw.partition("=")
    user, _, token_name = ident.partition("!")
    if not (user and token_name and value):
        return None
    return user, token_name, value


def _get_api():
    """Return a connected ProxmoxAPI, or None if token/CA are missing. Decision is cached."""
    global _API_CACHE, _API_RESOLVED
    if _API_RESOLVED:
        return _API_CACHE
    _API_RESOLVED = True
    tok = _read_token()
    if not tok:
        return None
    if not _ca_file().is_file():
        # CA-pin is mandatory; we never disable TLS verification.
        sys.stderr.write(
            f"# API token present but CA not pinned at {_ca_file()}.\n"
            f"# Run setup-token to fetch the CA, or fall back with --ssh. Using SSH for now.\n"
        )
        return None
    from proxmoxer import ProxmoxAPI
    user, token_name, token_value = tok
    _API_CACHE = ProxmoxAPI(
        _host(), port=API_PORT, user=user,
        token_name=token_name, token_value=token_value,
        verify_ssl=str(_ca_file()), service="PVE",
    )
    return _API_CACHE


def _get_ssh_password() -> str:
    """Sudo password for the *targeted* node: $PROXMOX_PASSWORD, else settings.secrets.<node>-password.

    Per-node on purpose: nodes with different passwords must never share one
    credential, or a retry with the wrong secret can lock the account out.
    """
    global _SSH_PW_CACHE
    if not _SSH_PW_CACHE:
        _SSH_PW_CACHE = os.environ.get("PROXMOX_PASSWORD") or credential.read(
            SKILL, f"{_TARGET}-password", label=f"the {_TARGET} sudo password")
    return _SSH_PW_CACHE


# ---------------------------------------------------------------------------
# Backend execution
# ---------------------------------------------------------------------------


def _ssh_sudo(remote_cmd: str, timeout: int = 180) -> str:
    """Run `sudo <remote_cmd>` on the node via ssh, feeding the password on stdin."""
    pw = _get_ssh_password()
    full = f"sudo -S -p '' {remote_cmd}"
    try:
        r = subprocess.run(
            ["ssh", _ssh_alias(), full],
            input=pw + "\n", capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        sys.exit(f"SSH command timed out after {timeout}s: {remote_cmd}")
    if r.returncode != 0:
        sys.exit(f"SSH command failed (exit {r.returncode}):\n{r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def _pvesh(verb: str, path: str, params: dict | None = None, timeout: int = 180) -> Any:
    """Run pvesh over SSH and return parsed JSON (or the raw UPID string)."""
    parts = ["pvesh", verb, path]
    for k, v in (params or {}).items():
        parts += [f"--{k}", str(v)]
    parts += ["--output-format", "json"]
    out = _ssh_sudo(shlex.join(parts), timeout=timeout).strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # pvesh mutations can emit status lines before the UPID JSON (old bug).
        for line in out.splitlines():
            line = line.strip().strip('"')
            if line.startswith("UPID:"):
                return line
        return out


def _api_call(verb: str, path: str, params: dict | None = None) -> Any:
    px = _get_api()
    node = px(path.lstrip("/"))
    params = params or {}
    if verb == "get":
        return node.get(**params)
    if verb == "create":
        return node.post(**params)
    if verb == "set":
        return node.put(**params)
    if verb == "delete":
        return node.delete(**params)
    raise ValueError(f"unknown verb {verb}")


def _backend() -> str:
    """'ssh' if forced, marked down, or no API creds, else 'api'."""
    if FORCE_SSH or _API_DOWN:
        return "ssh"
    return "api" if _get_api() is not None else "ssh"


def call(verb: str, path: str, params: dict | None = None) -> Any:
    """Unified API/SSH call. Falls back to SSH (once) only on an API *connection*
    failure -- never on an HTTP error the server actually returned."""
    global _API_DOWN
    if _backend() == "api":
        import socket

        import proxmoxer
        import requests
        try:
            return _api_call(verb, path, params)
        except proxmoxer.AuthenticationError as exc:
            sys.exit(f"Proxmox API auth failed: {exc}\nCheck the token, or use --ssh.")
        except proxmoxer.core.ResourceException as exc:
            # A real HTTP status (4xx/5xx) from the server. Surface it verbatim --
            # never silently re-run the call as root over SSH: that would let a
            # scoped-token 403 escalate to root, and would double-submit a mutation
            # that a 5xx reported only after it had already partly executed.
            sys.exit(f"Proxmox API error: {exc}")
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.SSLError,
                socket.error) as exc:  # connection refused, TLS, socket-level only
            _API_DOWN = True  # stop retrying the API for the rest of this run
            sys.stderr.write(f"# API unreachable ({exc}); using SSH for the rest of this run.\n")
    return _pvesh(verb, path, params)


# ---------------------------------------------------------------------------
# Task polling (mandatory on every mutation)
# ---------------------------------------------------------------------------


def wait_task(node: str, result: Any, label: str) -> None:
    """If `result` is a UPID, poll it to completion and fail on a bad exitstatus."""
    upid = result if isinstance(result, str) and result.startswith("UPID:") else None
    if not upid:
        return
    if _backend() == "api" and not FORCE_SSH:
        try:
            from proxmoxer.tools import Tasks
            status = Tasks.blocking_status(_get_api(), upid, timeout=TASK_TIMEOUT, polling_interval=POLL_INTERVAL)
            if status and status.get("exitstatus") not in (None, "OK"):
                _task_failed(node, upid, status.get("exitstatus"))
            return
        except Exception as exc:
            sys.stderr.write(f"# task poll via API failed ({exc}); polling via SSH.\n")
    deadline = time.monotonic() + TASK_TIMEOUT
    while time.monotonic() < deadline:
        st = _pvesh("get", f"/nodes/{node}/tasks/{upid}/status")
        if isinstance(st, dict) and st.get("status") == "stopped":
            if st.get("exitstatus") != "OK":
                _task_failed(node, upid, st.get("exitstatus"))
            return
        time.sleep(POLL_INTERVAL)
    sys.exit(f"Task {label} did not finish within {TASK_TIMEOUT}s (UPID {upid}).")


def _task_failed(node: str, upid: str, exitstatus: str | None) -> None:
    log = _pvesh("get", f"/nodes/{node}/tasks/{upid}/log")
    tail = ""
    if isinstance(log, list):
        tail = "\n".join(str(e.get("t", "")) for e in log[-15:])
    sys.exit(f"Task FAILED: {exitstatus}\nUPID: {upid}\n--- log tail ---\n{tail}")


# ---------------------------------------------------------------------------
# Resolution / guards
# ---------------------------------------------------------------------------


def resolve(target: str) -> dict:
    """Resolve a VMID or name to {'vmid', 'node', 'kind', 'name', 'status'}."""
    res = call("get", "/cluster/resources")
    guests = [r for r in (res or []) if r.get("type") in ("qemu", "lxc")]
    want = str(target)
    matches = []
    for r in guests:
        if str(r.get("vmid")) == want or (r.get("name") or "") == want:
            matches.append(r)
    if not matches:
        names = ", ".join(f"{r.get('name')}({r.get('vmid')})" for r in guests)
        sys.exit(f"No VM/CT matches '{target}'. Known: {names or '(none)'}")
    if len(matches) > 1:
        ids = ", ".join(str(r.get("vmid")) for r in matches)
        sys.exit(f"'{target}' is ambiguous (vmids: {ids}); use the numeric VMID.")
    r = matches[0]
    return {
        "vmid": int(r["vmid"]), "node": r["node"], "kind": r["type"],
        "name": r.get("name"), "status": r.get("status"),
    }


def _gpath(g: dict, *suffix: str) -> str:
    """Build /nodes/{node}/{qemu|lxc}/{vmid}[/...]."""
    base = f"/nodes/{g['node']}/{g['kind']}/{g['vmid']}"
    return base + ("/" + "/".join(suffix) if suffix else "")


def _guard_unlocked(g: dict) -> None:
    cfg = call("get", _gpath(g, "config"))
    lock = cfg.get("lock") if isinstance(cfg, dict) else None
    if lock:
        sys.exit(
            f"{g['kind']} {g['vmid']} is locked ('{lock}') -- a backup/migrate/snapshot is "
            f"likely in progress. Refusing to mutate. Wait for it to clear; do NOT force-unlock "
            f"a running operation (it corrupts the backup/migration)."
        )


def _require_yes(action: str) -> None:
    if not ASSUME_YES:
        sys.exit(
            f"Refusing destructive op '{action}' without --yes.\n"
            f"Confirm with the user first, then re-run with --yes."
        )


def _parse_kv(pairs: list[str]) -> dict:
    """Parse KEY=VALUE args into a params dict."""
    out: dict = {}
    for p in pairs:
        if "=" not in p:
            sys.exit(f"Expected KEY=VALUE, got '{p}'.")
        k, _, v = p.partition("=")
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


sys.path.insert(0, str(Path.home() / ".config" / "ai" / "common" / "lib"))
from emit import make_emit  # noqa: E402

emit = make_emit(OUT_DIR)


def _table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "(none)"
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    head = "  ".join(c.ljust(widths[c]) for c in cols)
    lines = [head, "  ".join("-" * widths[c] for c in cols)]
    for r in rows:
        lines.append("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subcommands -- read
# ---------------------------------------------------------------------------


def cmd_list(args) -> None:
    res = call("get", "/cluster/resources")
    guests = [r for r in (res or []) if r.get("type") in ("qemu", "lxc")]
    if args.json:
        emit("list", guests)
        return
    rows = [{
        "vmid": r.get("vmid"), "name": r.get("name"), "type": r.get("type"),
        "node": r.get("node"), "status": r.get("status"),
        "mem": _human(r.get("maxmem")), "disk": _human(r.get("maxdisk")),
    } for r in sorted(guests, key=lambda x: x.get("vmid", 0))]
    print(_table(rows, ["vmid", "name", "type", "node", "status", "mem", "disk"]))


def _human(n: Any) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}P"


def cmd_status(args) -> None:
    g = resolve(args.vm)
    emit("status", call("get", _gpath(g, "status", "current")))


def cmd_config(args) -> None:
    g = resolve(args.vm)
    emit("config", call("get", _gpath(g, "config")))


def cmd_snapshots(args) -> None:
    g = resolve(args.vm)
    emit("snapshots", call("get", _gpath(g, "snapshot")))


def cmd_storage(args) -> None:
    if args.node:
        emit("storage", call("get", f"/nodes/{args.node}/storage"))
    else:
        emit("storage", call("get", "/storage"))


def cmd_nodes(args) -> None:
    emit("nodes", call("get", "/nodes"))


# ---------------------------------------------------------------------------
# Subcommands -- lifecycle
# ---------------------------------------------------------------------------


def _status_op(args, op: str, label: str) -> None:
    g = resolve(args.vm)
    _guard_unlocked(g)
    res = call("create", _gpath(g, "status", op))
    wait_task(g["node"], res, label)
    print(f"{label}: {g['kind']} {g['vmid']} ({g['name']})")


def cmd_start(args) -> None:
    _status_op(args, "start", "start")


def cmd_shutdown(args) -> None:
    _status_op(args, "shutdown", "shutdown")  # graceful (ACPI)


def cmd_reboot(args) -> None:
    _status_op(args, "reboot", "reboot")


def cmd_stop(args) -> None:
    _require_yes("stop (hard power-off)")
    _status_op(args, "stop", "stop")  # hard kill -- can corrupt the guest FS


def cmd_clone(args) -> None:
    g = resolve(args.vm)
    _guard_unlocked(g)
    params: dict = {"newid": args.newid}
    if args.name:
        params["name"] = args.name
    if args.full:
        params["full"] = 1
    if args.storage:
        params["storage"] = args.storage
    res = call("create", _gpath(g, "clone"), params)
    wait_task(g["node"], res, "clone")
    print(f"cloned {g['vmid']} -> {args.newid}")


def cmd_create(args) -> None:
    kind = "lxc" if args.lxc else "qemu"
    node = args.node or _default_node()
    params = _parse_kv(args.params)
    params["vmid"] = args.vmid
    res = call("create", f"/nodes/{node}/{kind}", params)
    wait_task(node, res, "create")
    print(f"created {kind} {args.vmid} on {node}")


def cmd_set(args) -> None:
    g = resolve(args.vm)
    _guard_unlocked(g)
    params = _parse_kv(args.params)
    if args.delete:
        _require_yes(f"set --delete {args.delete}")
        params["delete"] = args.delete  # unset keys via the `delete` param, not key=""
    if not params:
        sys.exit("Nothing to set. Pass KEY=VALUE pairs and/or --delete KEY[,KEY].")
    res = call("set", _gpath(g, "config"), params)
    wait_task(g["node"], res, "set")
    print(f"updated config: {g['kind']} {g['vmid']}")


def cmd_migrate(args) -> None:
    g = resolve(args.vm)
    _guard_unlocked(g)
    params = {"target": args.target}
    if args.online:
        params["online"] = 1
    res = call("create", _gpath(g, "migrate"), params)
    wait_task(g["node"], res, "migrate")
    print(f"migrating {g['vmid']} -> {args.target}")


def cmd_destroy(args) -> None:
    _require_yes("destroy")
    g = resolve(args.vm)
    _guard_unlocked(g)
    params = {}
    if args.purge:
        params["purge"] = 1  # also strip HA/replication/firewall refs
    res = call("delete", _gpath(g), params)
    wait_task(g["node"], res, "destroy")
    print(f"destroyed {g['kind']} {g['vmid']}" + (" (purged)" if args.purge else ""))


# ---------------------------------------------------------------------------
# Subcommands -- snapshots / backup
# ---------------------------------------------------------------------------


def _snapshot_capable(g: dict) -> tuple[bool, str]:
    cfg = call("get", _gpath(g, "config"))
    if not isinstance(cfg, dict):
        return True, ""
    disk_keys = ("scsi", "virtio", "sata", "ide", "rootfs", "mp")
    storages = set()
    for k, v in cfg.items():
        if any(k.startswith(p) for p in disk_keys) and isinstance(v, str) and ":" in v:
            storages.add(v.split(":", 1)[0])
    for sid in storages:
        info = call("get", f"/storage/{sid}")
        stype = info.get("type") if isinstance(info, dict) else None
        if stype in SNAPSHOT_NEVER:
            return False, f"storage '{sid}' is classic LVM ({stype}); it cannot snapshot"
    return True, ""


def cmd_snapshot(args) -> None:
    g = resolve(args.vm)
    _guard_unlocked(g)
    ok, why = _snapshot_capable(g)
    if not ok and not args.force:
        sys.exit(f"Snapshot blocked: {why}. Use --force to attempt anyway.")
    params = {"snapname": args.snapname}
    if args.description:
        params["description"] = args.description
    if args.vmstate and g["kind"] == "qemu":
        params["vmstate"] = 1  # include RAM (LXC cannot)
    res = call("create", _gpath(g, "snapshot"), params)
    wait_task(g["node"], res, "snapshot")
    print(f"snapshot '{args.snapname}' created on {g['kind']} {g['vmid']}")


def cmd_rollback(args) -> None:
    _require_yes("rollback")
    g = resolve(args.vm)
    _guard_unlocked(g)
    res = call("create", _gpath(g, "snapshot", args.snapname, "rollback"))
    wait_task(g["node"], res, "rollback")
    print(f"rolled {g['kind']} {g['vmid']} back to '{args.snapname}'")


def cmd_delsnapshot(args) -> None:
    _require_yes("delsnapshot")
    g = resolve(args.vm)
    _guard_unlocked(g)
    res = call("delete", _gpath(g, "snapshot", args.snapname))
    wait_task(g["node"], res, "delsnapshot")
    print(f"deleted snapshot '{args.snapname}' on {g['kind']} {g['vmid']}")


def cmd_backup(args) -> None:
    g = resolve(args.vm)
    _guard_unlocked(g)
    params = {"vmid": g["vmid"], "mode": args.mode, "compress": args.compress}
    if args.storage:
        params["storage"] = args.storage
    res = call("create", f"/nodes/{g['node']}/vzdump", params)
    wait_task(g["node"], res, "backup")
    print(f"backup ({args.mode}) of {g['vmid']} complete")


# ---------------------------------------------------------------------------
# Subcommands -- exec (SSH only) / raw / setup
# ---------------------------------------------------------------------------


def cmd_exec(args) -> None:
    """Run a command inside a guest. LXC: pct exec. VM: qm guest exec (needs agent)."""
    g = resolve(args.vm)
    inner = shlex.join(args.command)
    if g["kind"] == "lxc":
        out = _ssh_sudo(f"pct exec {g['vmid']} -- {_sh_wrap(inner)}")
    else:
        out = _ssh_sudo(f"qm guest exec {g['vmid']} -- {_sh_wrap(inner)}")
    emit("exec", out)


def _sh_wrap(inner: str) -> str:
    return "sh -c " + shlex.quote(inner)


def cmd_raw(args) -> None:
    """Escape hatch: raw API path. e.g. raw get /version ; raw create /nodes/pve/qemu/100/status/start"""
    params = _parse_kv(args.params)
    if args.verb in ("create", "set", "delete"):
        _require_yes(f"raw {args.verb} {args.path}")
    emit(f"raw-{args.verb}", call(args.verb, args.path, params or None))


def _default_node() -> str:
    nodes = call("get", "/nodes")
    online = [n for n in (nodes or []) if isinstance(n, dict)]
    if not online:
        sys.exit("Could not determine a node from /nodes.")
    return online[0]["node"]


def cmd_setup_token(args) -> None:
    """One-time bootstrap: create the automation user/role/token + pin the CA. SSH only."""
    print("# Creating automation identity on the node (idempotent)...")
    seq = [
        f"pveum user add {AUTOMATION_USER} --comment 'Claude use-proxmox skill' || true",
        f"pveum role add {AUTOMATION_ROLE} --privs {shlex.quote(ROLE_PRIVS)} "
        f"|| pveum role modify {AUTOMATION_ROLE} --privs {shlex.quote(ROLE_PRIVS)}",
        f"pveum acl modify /vms --user {AUTOMATION_USER} --role {AUTOMATION_ROLE}",
        f"pveum acl modify /storage --user {AUTOMATION_USER} --role {AUTOMATION_ROLE}",
    ]
    for cmd in seq:
        _ssh_sudo(cmd)
    # Create the token (privsep=1) -- secret is shown exactly once.
    out = _ssh_sudo(
        f"pveum user token add {AUTOMATION_USER} {AUTOMATION_TOKEN} "
        f"--privsep 1 --output-format json || true"
    )
    secret = None
    try:
        data = json.loads(out)
        secret = data.get("value")
    except json.JSONDecodeError:
        pass
    # privsep tokens need their own ACLs.
    for path in ("/vms", "/storage"):
        _ssh_sudo(f"pveum acl modify {path} --tokens '{AUTOMATION_USER}!{AUTOMATION_TOKEN}' --role {AUTOMATION_ROLE}")
    # Pin the CA.
    ca = _ssh_sudo("cat /etc/pve/pve-root-ca.pem")
    _ca_file().parent.mkdir(parents=True, exist_ok=True)
    _ca_file().write_text(ca)
    print(f"# CA pinned -> {_ca_file()}")
    if secret:
        token_line = f"{AUTOMATION_USER}!{AUTOMATION_TOKEN}={secret}"
        _store_token(token_line)
    else:
        print("\n# Token may already exist (no secret returned). To rotate, remove and re-add:")
        print(f"#   ssh {_ssh_alias()} sudo pveum user token remove {AUTOMATION_USER} {AUTOMATION_TOKEN}")
        print(f"#   then re-run setup-token.")


def _store_token(token_line: str) -> None:
    """Write the new token to the op:// reference in settings.secrets.<node>-token."""
    ref = (SETTINGS.get("secrets") or {}).get(_token_key(), "")
    parts = ref.removeprefix("op://").split("/") if ref.startswith("op://") else []
    if len(parts) != 3:
        print(f"\n# Token created. Store it where settings.secrets.{_token_key()} points, then API calls use it:")
        print(f"#   {token_line}")
        return
    vault, title, field = parts
    # The agent's reader may be read-only, so the write goes through the human `op`. The
    # secret travels on stdin: as an argument it would land in argv and `ps`.
    item = {"title": title, "category": "API_CREDENTIAL",
            "fields": [{"id": field, "label": field, "type": "CONCEALED", "value": token_line}]}
    r = subprocess.run(["op", "item", "create", "--vault", vault, "--format", "json"],
                       input=json.dumps(item), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        sys.exit(f"Token created on the node, but storing it failed: {r.stderr.strip()}\n"
                 f"Remove it with `ssh {_ssh_alias()} sudo pveum user token remove "
                 f"{AUTOMATION_USER} {AUTOMATION_TOKEN}` and re-run setup-token.")
    print(f"\n# Token created and stored in {ref}.")
    print("# API calls will use it automatically from now on.")


def cmd_hosts(args) -> None:
    """The configured nodes, with each one's note. Reads settings only, never the network."""
    rows = [{"node": name + (" (default)" if name == DEFAULT_HOST else ""),
             "api": n.get("apiHost") or name, "ssh": n.get("sshAlias") or name,
             "aliases": ",".join(n.get("aliases", [])), "note": n.get("note", "")}
            for name, n in HOSTS.items()]
    if args.json:
        emit("hosts", HOSTS)
    else:
        print(_table(rows, ["node", "api", "ssh", "aliases", "note"]))


def cmd_shutdown_node(args) -> None:
    """Shut down every running guest (graceful, forced after --timeout), then power the node off."""
    _require_yes("shutdown-node (powers the whole node off)")
    node = _default_node()
    running = [{**g, "kind": kind} for kind in ("qemu", "lxc")
               for g in (call("get", f"/nodes/{node}/{kind}") or [])
               if g.get("status") == "running"]
    for g in running:
        print(f"shutting down {g['kind']} {g['vmid']} ({g.get('name', '')})...")
        res = call("create", f"/nodes/{node}/{g['kind']}/{g['vmid']}/status/shutdown",
                   {"timeout": args.timeout, "forceStop": 1})
        wait_task(node, res, f"shutdown {g['vmid']}")
    call("create", f"/nodes/{node}/status", {"command": "shutdown"})
    print(f"node {node} is shutting down")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

FORCE_SSH = False
ASSUME_YES = False


def _common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--host", "-H", default=None, metavar="NODE",
        help="Which configured node (see `hosts`). Also $PROXMOX_NODE; default settings.defaultNode.",
    )
    sp.add_argument("--ssh", action="store_true", help="Force the SSH backend (skip the API).")
    sp.add_argument("--yes", action="store_true", help="Confirm a destructive operation.")
    sp.add_argument("--json", action="store_true", help="Emit raw JSON instead of a table.")


def main() -> None:
    global FORCE_SSH, ASSUME_YES, _TARGET
    p = argparse.ArgumentParser(
        prog="proxmox",
        description="On-demand Proxmox VE control across standalone nodes.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="List all VMs and containers")
    _common(sp); sp.set_defaults(handler=cmd_list)

    sp = sub.add_parser("status", help="Current status of a VM/CT")
    sp.add_argument("vm", help="VMID or name"); _common(sp); sp.set_defaults(handler=cmd_status)

    sp = sub.add_parser("config", help="Config of a VM/CT")
    sp.add_argument("vm"); _common(sp); sp.set_defaults(handler=cmd_config)

    sp = sub.add_parser("snapshots", help="List snapshots of a VM/CT")
    sp.add_argument("vm"); _common(sp); sp.set_defaults(handler=cmd_snapshots)

    sp = sub.add_parser("storage", help="Storage status")
    sp.add_argument("--node", help="Limit to one node"); _common(sp); sp.set_defaults(handler=cmd_storage)

    sp = sub.add_parser("nodes", help="List nodes")
    _common(sp); sp.set_defaults(handler=cmd_nodes)

    sp = sub.add_parser("hosts", help="List the configured nodes and their notes")
    _common(sp); sp.set_defaults(handler=cmd_hosts)

    sp = sub.add_parser("start", help="Start a VM/CT")
    sp.add_argument("vm"); _common(sp); sp.set_defaults(handler=cmd_start)

    sp = sub.add_parser("shutdown", help="Graceful shutdown (ACPI)")
    sp.add_argument("vm"); _common(sp); sp.set_defaults(handler=cmd_shutdown)

    sp = sub.add_parser("reboot", help="Reboot a VM/CT")
    sp.add_argument("vm"); _common(sp); sp.set_defaults(handler=cmd_reboot)

    sp = sub.add_parser("stop", help="Hard power-off (destructive; needs --yes)")
    sp.add_argument("vm"); _common(sp); sp.set_defaults(handler=cmd_stop)

    sp = sub.add_parser("clone", help="Clone a VM/CT or template")
    sp.add_argument("vm"); sp.add_argument("newid", type=int)
    sp.add_argument("--name"); sp.add_argument("--full", action="store_true")
    sp.add_argument("--storage"); _common(sp); sp.set_defaults(handler=cmd_clone)

    sp = sub.add_parser("create", help="Create a VM (or --lxc container)")
    sp.add_argument("vmid", type=int); sp.add_argument("--lxc", action="store_true")
    sp.add_argument("--node"); sp.add_argument("params", nargs="*", help="KEY=VALUE config pairs")
    _common(sp); sp.set_defaults(handler=cmd_create)

    sp = sub.add_parser("set", help="Update config / cloud-init (KEY=VALUE ...)")
    sp.add_argument("vm"); sp.add_argument("params", nargs="*", help="KEY=VALUE pairs")
    sp.add_argument("--delete", help="Comma-separated keys to unset (needs --yes)")
    _common(sp); sp.set_defaults(handler=cmd_set)

    sp = sub.add_parser("migrate", help="Migrate a VM/CT to another node")
    sp.add_argument("vm"); sp.add_argument("target"); sp.add_argument("--online", action="store_true")
    _common(sp); sp.set_defaults(handler=cmd_migrate)

    sp = sub.add_parser("destroy", help="Delete a VM/CT (destructive; needs --yes)")
    sp.add_argument("vm"); sp.add_argument("--purge", action="store_true", help="Also strip HA/replication/firewall refs")
    _common(sp); sp.set_defaults(handler=cmd_destroy)

    sp = sub.add_parser("snapshot", help="Create a snapshot")
    sp.add_argument("vm"); sp.add_argument("snapname")
    sp.add_argument("--description"); sp.add_argument("--vmstate", action="store_true", help="Include RAM (VM only)")
    sp.add_argument("--force", action="store_true", help="Override the storage-capability check")
    _common(sp); sp.set_defaults(handler=cmd_snapshot)

    sp = sub.add_parser("rollback", help="Roll back to a snapshot (destructive; needs --yes)")
    sp.add_argument("vm"); sp.add_argument("snapname"); _common(sp); sp.set_defaults(handler=cmd_rollback)

    sp = sub.add_parser("delsnapshot", help="Delete a snapshot (destructive; needs --yes)")
    sp.add_argument("vm"); sp.add_argument("snapname"); _common(sp); sp.set_defaults(handler=cmd_delsnapshot)

    sp = sub.add_parser("backup", help="vzdump backup of a VM/CT")
    sp.add_argument("vm"); sp.add_argument("--storage")
    sp.add_argument("--mode", choices=["snapshot", "suspend", "stop"], default="snapshot")
    sp.add_argument("--compress", choices=["zstd", "gzip", "lzo", "0"], default="zstd")
    _common(sp); sp.set_defaults(handler=cmd_backup)

    sp = sub.add_parser("exec", help="Run a command inside a guest (SSH)")
    sp.add_argument("vm"); sp.add_argument("command", nargs=argparse.REMAINDER, help="Command to run")
    _common(sp); sp.set_defaults(handler=cmd_exec)

    sp = sub.add_parser("raw", help="Raw API call: raw <get|create|set|delete> <path> [KEY=VALUE...]")
    sp.add_argument("verb", choices=["get", "create", "set", "delete"])
    sp.add_argument("path"); sp.add_argument("params", nargs="*")
    _common(sp); sp.set_defaults(handler=cmd_raw)

    sp = sub.add_parser("shutdown-node", help="Shut down every running guest, then the node (needs --yes)")
    sp.add_argument("--timeout", type=int, default=60, help="Seconds per guest before a forced stop")
    _common(sp); sp.set_defaults(handler=cmd_shutdown_node)

    sp = sub.add_parser("setup-token", help="One-time: create the automation token + pin the CA (SSH)")
    _common(sp); sp.set_defaults(handler=cmd_setup_token)

    args = p.parse_args()
    # Resolve the target node before any handler touches auth or transport.
    if args.cmd != "hosts":
        _TARGET = resolve_host(getattr(args, "host", None) or os.environ.get("PROXMOX_NODE"))
    # The scoped token lacks Sys.PowerMgmt, so a node shutdown goes through sudo.
    FORCE_SSH = getattr(args, "ssh", False) or args.cmd in ("exec", "setup-token", "shutdown-node")
    ASSUME_YES = getattr(args, "yes", False)
    if not hasattr(args, "json"):
        args.json = False
    try:
        args.handler(args)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
