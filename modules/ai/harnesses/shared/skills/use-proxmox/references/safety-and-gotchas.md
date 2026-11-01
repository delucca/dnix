# Safety rails & Proxmox automation gotchas

The footguns below are why the script behaves the way it does. Read this before
"fixing" a rail that seems to be in the way.

## Enforced rails (in the script)

### 1. Always poll the UPID task
Every mutating API call returns a **UPID** immediately and runs asynchronously.
The initial HTTP 200 means "accepted", not "done" — the operation can still fail.
`wait_task()` polls `/nodes/{node}/tasks/{upid}/status` until `stopped` and fails
on any `exitstatus != OK`, dumping the task log tail. Never treat a POST as success.

### 2. Confirmation gate on destructive ops
`stop` (hard power-off), `destroy`, `rollback`, `delsnapshot`, and `set --delete`
require `--yes`. The gate exists because these lose data:
- `stop` pulls the virtual power cord — guest filesystems can corrupt. Prefer `shutdown`.
- `destroy` is immediate and has no recycle bin. Without `--purge` it leaves
  HA/replication/firewall refs that silently re-attach to the next VM reusing
  that VMID — so we expose `--purge`.
- `rollback` discards everything since the snapshot.
- `set --delete` removes a disk/NIC permanently.

The agent must still get the user's explicit OK before passing `--yes`.

### 3. Lock awareness — never auto-unlock
Backup, migrate, snapshot, and clone hold a lock (`config.lock`). Mutating a
locked guest fails with `got timeout`. `_guard_unlocked()` refuses up front.
`qm unlock` exists but force-unlocking an **in-flight** backup/migration corrupts
it — so the skill never does this automatically.

### 4. Resolve the node, never assume it
`/nodes/{node}/...` calls fail if the guest is on a different node. `resolve()`
queries `/cluster/resources` for the live node and the qemu-vs-lxc kind. (We are
single-node today, but this stays correct if that changes.)

### 5. Snapshot storage capability
Snapshots need qcow2 / ZFS / LVM-thin / Ceph. Classic **LVM** and raw-on-dir
cannot snapshot — the failure is cryptic. `_snapshot_capable()` hard-refuses on a
classic-`lvm` backing store unless `--force`.

## Other gotchas worth knowing

- **Booleans are `1`/`0`**, not `true`/`false`, in API params.
- **Unset a config key with the `delete` param** (`set --delete net1`), not by
  sending `net1=""` (silently ignored).
- **Array/map params are serialized strings**: `net0='virtio,bridge=vmbr0,tag=20'`,
  `scsi0='local-lvm:32'` — pass them quoted, not as structured data.
- **Cloud-init does not apply live.** Changing `ciuser`/`ipconfig0`/`sshkeys`
  requires regenerating the cloud-init drive and rebooting; an already-booted
  guest won't re-run cloud-init without `cloud-init clean` inside it.
- **VMID reuse races.** After a destroy the VMID is immediately free. Prefer
  `--purge` so stale refs don't attach to the next guest with that ID.
- **`sshkeys` must be URL-encoded** when sent raw over the API; proxmoxer/pvesh
  handle typical cases, but odd characters can trip it.
- **`pct exec` / `qm guest exec` are SSH/CLI only** — no clean REST equivalent,
  which is why `exec` always uses the SSH backend (and `qm guest exec` needs the
  guest agent installed).
- **pvesh mutation output** historically prefixed the UPID with status lines on
  PVE 7.2; `_pvesh()` tolerates this by scanning for the `UPID:` line.
- **PVE 7→8/9 drift**: default CPU type changed to `x86-64-v2-AES`; TLS 1.0/1.1
  dropped in 8; `VM.Monitor` removed in 9 (see token-setup.md).

## Transport notes

- The API backend is preferred; on a connection/TLS error the script warns and
  falls back to SSH so reads/lifecycle still work.
- The SSH backend runs `sudo -S -p ''` and feeds the password on **stdin** (not in
  argv), an improvement over the older `echo "$pw" | sudo -S` shell helpers.
- `pvesh` requires root, so the SSH backend always goes through sudo.
