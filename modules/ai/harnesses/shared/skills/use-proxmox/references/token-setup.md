# Token setup & auth model

The skill prefers a scoped API token and only falls back to SSH+sudo. This file
explains the one-time setup that `setup-token` automates, the privilege set, and
the TLS model — so you can verify or redo it by hand.

## Why a dedicated token, not root

The SSH backend drives a node as `ssh <node>` + `sudo -S qm ...`,
i.e. effectively `root@pam`. That is the maximum blast radius for an agent that
can issue `destroy --purge`. A dedicated `automation@pve` user is:

- **RBAC-constrained** — its powers are exactly the role's privileges, nothing more.
- **No Linux account** — the `@pve` realm lives only in Proxmox's DB, so a leaked
  token is not a shell on the box (unlike `@pam`).
- **Revocable** — drop the token without touching anything else.

API tokens never need the CSRF header (unlike password/ticket auth), and with
`privsep=1` the token's effective rights are the **intersection** of its own ACLs
and the user's ACLs.

## What `setup-token` does (idempotent)

Run over SSH as root:

```bash
pveum user add automation@pve --comment 'Claude use-proxmox skill' || true
pveum role add ClaudeAutomation --privs "<PRIVS>" || pveum role modify ClaudeAutomation --privs "<PRIVS>"
pveum acl modify /vms     --user automation@pve --role ClaudeAutomation
pveum acl modify /storage --user automation@pve --role ClaudeAutomation
pveum user token add automation@pve skill --privsep 1 --output-format json   # secret shown ONCE
pveum acl modify /vms     --tokens 'automation@pve!skill' --role ClaudeAutomation
pveum acl modify /storage --tokens 'automation@pve!skill' --role ClaudeAutomation
```

Then it copies `/etc/pve/pve-root-ca.pem` to `~/.config/proxmox/<host>/pve-root-ca.pem`
and stores the token secret (below).

The `--tokens` ACL lines are required because `privsep=1` gives the token an
empty ACL until you grant it one.

## The privilege set

VM/LXC lifecycle, snapshots, clone, migrate, and disk/template allocation — and
deliberately nothing node- or permission-level:

```
VM.Allocate, VM.Audit, VM.Clone, VM.Config.CDROM, VM.Config.CPU,
VM.Config.Cloudinit, VM.Config.Disk, VM.Config.HWType, VM.Config.Memory,
VM.Config.Network, VM.Config.Options, VM.PowerMgmt, VM.Console,
VM.Snapshot, VM.Snapshot.Rollback, VM.Migrate,
Datastore.AllocateSpace, Datastore.AllocateTemplate, Datastore.Audit, Sys.Audit
```

Deliberately omitted:
- **`Sys.Modify`** — sometimes needed to attach a NIC to a bridge during VM
  create. If create fails with a bridge-permission error, add it: `pveum role
  modify ClaudeAutomation --privs "<PRIVS>,Sys.Modify"`.
- **`VM.Monitor`** — removed in PVE 9; including it makes `pveum role add` fail on
  9.x. We do not use the monitor, so it is left out.
- **`Permissions.Modify`, `Realm.*`, `Datastore.Allocate`, `Sys.PowerMgmt`,
  `Sys.Console`** — never; these escalate or touch the host.

## Storing the secret

The token id+secret is `automation@pve!skill=<UUID>`, one per node. `setup-token`
stores it at the `op://<vault>/<item>/<field>` reference in
`settings.secrets.<node>-token`, through the human `op` because the agent's reader
may be read-only, and passes the secret on stdin so it never reaches argv. With
any other kind of reference it prints the token once for the user to store. The
skill reads it back through `dnix.ai.secrets.readCommand`.

## TLS — CA pinning, never `verify_ssl=False`

Proxmox ships a self-signed cert from its own CA at `/etc/pve/pve-root-ca.pem`.
Self-signed is fine; **unverified is not**. `setup-token` pins that CA locally and
the skill passes it as `verify_ssl=<path>`. Note that Python `requests` ignores
the OS trust store, so the explicit path is required. To rotate, re-fetch the CA.

## Host / reachability

The API uses the node's `apiHost` setting on :8006 (the node name when unset;
override with `$PROXMOX_HOST`). Prefer a literal address: a `.local` name with no
mDNS responder on the node never resolves, and the API path then dies quietly
with every call falling back to SSH. If :8006 is not reachable from this machine,
the skill falls back to SSH automatically, but the token path needs the port
open. The SSH side uses the node's `sshAlias`, so LAN-first or Tailscale routing
belongs in the ssh config.
