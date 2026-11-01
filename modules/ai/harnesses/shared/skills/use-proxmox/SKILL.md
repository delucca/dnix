---
name: use-proxmox
description: Controls VMs and LXC containers on the configured standalone Proxmox nodes, start, stop, clone, snapshot, backup, node shutdown. Use for a known guest or listing VMs. NOT for non-Proxmox SSH, Docker or cloud VMs.
allowed-tools: Bash(uv run *), Read
argument-hint: "[hosts|list|status|start|stop|clone|snapshot|backup|exec|shutdown-node|...] [vm] [--host NODE] [args]"
---

# use-proxmox -- on-demand Proxmox VE control

Control VMs and LXC containers on standalone Proxmox nodes without paying any
standing context cost. One script speaks to a node two ways and picks the right
one automatically.

## Which node

The nodes come from `~/.config/ai/settings/use-proxmox.json`, which
`dnix.ai.skills.use-proxmox.settings` writes. They are **standalone**, never a
cluster, so `/cluster/resources` on one never sees another's guests, and every
invocation targets exactly one: `--host NODE`, else `$PROXMOX_NODE`, else
`defaultNode`.

**Run `hosts` first.** It reads the settings only and prints every node with its
aliases and its `note`. The note is where the user says what lives on a node and
how it behaves: one that is powered off most of the time, and how to wake it, is
written there. A connection failure to such a node usually means it is asleep,
not broken.

```bash
uv run $SCRIPT hosts                   # the configured nodes and their notes
uv run $SCRIPT list                    # guests on the default node
uv run $SCRIPT list --host <node>      # guests on another node
```

## When NOT to use this skill

- **Non-Proxmox SSH** — plain SSH to a host that is not one of these nodes.
- **Docker/Kubernetes** — container orchestration outside Proxmox is out of scope.
- **Cloud VMs** (AWS/GCP/etc.) — this skill only drives the on-prem nodes.

**Why this design.** No Proxmox MCP is mature enough to trust with destructive
operations, and registering one would load its tool schemas into every
conversation. This wrapper loads nothing until invoked, runs one operation, and
exits, like `use-home-assistant`.

**Transports (auto-selected).**
- **API (default).** `proxmoxer` over HTTPS using a scoped `automation@pve`
  token, TLS verified against the pinned PVE CA. Least blast radius, full JSON.
- **SSH (fallback / bootstrap / guest exec / node shutdown).** The node's ssh alias
  + `sudo -S pvesh|qm|pct`, with the sudo password read **per node**, so nodes
  with different passwords never share one. Used automatically when the token/CA
  are not yet set up, for `exec` (no REST equivalent), for `shutdown-node`, and
  whenever you pass `--ssh`.

The same API path drives both backends, because `pvesh <verb> <path>` maps 1:1
to the REST API. If the API is unreachable, the script warns and falls back to SSH.

## First run -- one-time setup

The API token does **not** exist yet, so out of the box the skill runs over SSH
(works today). To switch to the safer token transport, run once:

```bash
SCRIPT={baseDir}/scripts/proxmox.py
uv run $SCRIPT setup-token
```

This creates a least-privilege `automation@pve` user + token on the selected node,
pins the CA to `~/.config/proxmox/<node>/pve-root-ca.pem`, and stores the token
at the `op://` reference in `settings.secrets.<node>-token` through the human
`op` (one desktop-app prompt). With no such reference it prints the token once
for the user to store. Run it once per node. After that, API calls are used
automatically. Full rationale and the exact privilege set: see
`references/token-setup.md`.

## Usage

All subcommands run through one script:

```bash
SCRIPT={baseDir}/scripts/proxmox.py
uv run $SCRIPT <subcommand> [args]
```

**Requirements.** `uv` runs the script and fetches its pinned deps. Secrets are
read through `dnix.ai.secrets.readCommand`. The SSH backend needs the node's ssh
alias to resolve and `settings.secrets.<node>-password` (or `$PROXMOX_PASSWORD`
exported); the API backend needs `settings.secrets.<node>-token` and the pinned
CA. The script reports which one is missing rather than crashing.

A guest is addressed by **VMID or name** on whichever node you selected. The VM-vs-container kind is resolved
automatically from `/cluster/resources` -- never hardcode it.

**Names match exactly, so prefer the VMID when the name carries a version.** A
guest named `haos-17.2` is not `haos`, and the suffix moves with every upgrade.
The VMID never changes. `list` prints the current names when in doubt.

Global flags (on any subcommand): `--ssh` force the SSH backend, `--yes` confirm
a destructive op, `--json` raw JSON instead of a table.

## Read

```bash
uv run $SCRIPT list                  # all VMs + CTs: vmid, name, type, node, status, mem, disk
uv run $SCRIPT status web         # live status (uptime, cpu, mem)
uv run $SCRIPT config 100            # full config
uv run $SCRIPT snapshots web      # snapshot tree
uv run $SCRIPT storage               # storage pools and capacity
uv run $SCRIPT nodes                 # cluster nodes
```

## Lifecycle

```bash
uv run $SCRIPT start web
uv run $SCRIPT shutdown 100                         # graceful ACPI -- preferred
uv run $SCRIPT reboot web
uv run $SCRIPT stop desktop --host <node> --yes  # HARD power-off; can corrupt the guest FS
uv run $SCRIPT clone 9000 105 --name test-vm --full --storage local-lvm
uv run $SCRIPT destroy 105 --purge --yes   # delete + strip HA/replication/firewall refs
```

`create` and `set` take free-form `KEY=VALUE` pairs that map straight to the
Proxmox API (so any field works without the skill enumerating the schema):

```bash
# Create an LXC container
uv run $SCRIPT create 110 --lxc \
  hostname=test ostemplate=local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  rootfs=local-lvm:8 memory=512 net0='name=eth0,bridge=vmbr0,ip=dhcp' unprivileged=1

# Configure cloud-init on a cloned VM, then start it
uv run $SCRIPT set 105 ciuser=ubuntu ipconfig0='ip=dhcp' sshkeys='ssh-ed25519 AAAA...'
uv run $SCRIPT start 105

# Unset a config key (uses the API `delete` param, not key="")
uv run $SCRIPT set 105 --delete net1 --yes
```

## Snapshots and backups

```bash
uv run $SCRIPT snapshot web pre-upgrade --description "before an upgrade"
uv run $SCRIPT snapshot 100 pre-upgrade --vmstate             # include RAM (VM only)
uv run $SCRIPT rollback web pre-upgrade --yes                  # destructive
uv run $SCRIPT delsnapshot web pre-upgrade --yes               # destructive
uv run $SCRIPT backup 100 --storage local --mode snapshot --compress zstd
```

`snapshot` refuses on classic-LVM storage (which cannot snapshot) unless you pass
`--force`. Snapshots need qcow2 / ZFS / LVM-thin / Ceph backing.

## Node shutdown (SSH)

```bash
uv run $SCRIPT shutdown-node --host <node> --yes            # every running guest, then the node
uv run $SCRIPT shutdown-node --host <node> --timeout 120 --yes
```

Each running guest gets a graceful shutdown, forced after `--timeout` seconds
(default 60), then the node powers off. Destructive: confirm with the user first.

## Guest exec (SSH)

```bash
uv run $SCRIPT exec web uptime                       # LXC: pct exec
uv run $SCRIPT exec 100 hostname                   # VM: qm guest exec (needs guest agent)
```

## Escape hatch

```bash
uv run $SCRIPT raw get /version
uv run $SCRIPT raw get /nodes/<node>/qemu/100/status/current
uv run $SCRIPT raw create /nodes/<node>/qemu/100/status/start --yes
```

`raw` reaches any API path; write verbs (`create`/`set`/`delete`) require `--yes`.

## Safety rails (enforced)

These are built into the script -- do not try to bypass them. Detail and the
"why" behind each: `references/safety-and-gotchas.md`.

1. **Every mutation polls its UPID task** to completion and fails loudly on a bad
   `exitstatus`. A successful POST does not mean the operation succeeded.
2. **Destructive ops require `--yes`**: `stop`, `destroy`, `rollback`,
   `delsnapshot`, `set --delete` and `shutdown-node`. **Always confirm with the user before
   passing `--yes`** -- these can lose data.
3. **Locked guests are not mutated.** If a backup/migrate/snapshot holds the lock,
   the op refuses. **Never force-unlock** an in-flight operation (corrupts it).
4. **The node is resolved live** from `/cluster/resources`, never assumed.
5. **TLS is CA-pinned**; the skill never disables certificate verification.

## Output handling

- Results <=4 KB print inline. Larger payloads spill to
  `~/.cache/proxmox-cm/<timestamp>-<label>.json`; the script prints the path and the
  first 1500 chars. Read the file for the rest.

## Common mistakes

1. **Hard `stop` when you meant `shutdown`.** `stop` is a power-pull. Default to
   `shutdown`; only `stop --yes` a guest that won't shut down gracefully.
2. **Skipping the user confirmation before `--yes`.** The flag silences the
   guard; the human confirmation is still required.
3. **Expecting cloud-init `set` to apply live.** Changing cloud-init keys needs a
   drive regen + reboot, and won't re-run on an already-booted guest without
   `cloud-init clean` inside it.
4. **A secret missing.** Both backends read theirs through the secret reader:
   the SSH backend the sudo password, the API backend the token. Errors name
   which setting is missing.

## Hard prohibitions

- Never disable TLS verification (`verify_ssl=False`) to "make it connect" --
  pin the CA via `setup-token` instead. Self-signed does not mean unverified.
- Never force-unlock a guest to push an operation through -- if it is locked, a
  backup/migration/snapshot is running and unlocking corrupts it.
- Never pass `--yes` on a destructive op without the user's explicit confirmation
  in this session.
- Never hardcode a node name or VM-vs-CT kind -- resolve from cluster resources.
- Never store the API token or the SSH password in a repo or on disk -- they
  stay behind the secret reader.
