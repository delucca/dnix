# node

The system-manager base of a Proxmox node: the `dnix.node` block the deploy scripts reach the node through, [the secrets module](../secrets/README.md), and opt-in node services: a vzdump hook chain with Home Assistant sensors and offsite copies, host health sensors, and power tuning. A flake takes it as `dnix.nixosModules.node` in a `system-manager.lib.makeSystemConfig`, next to `dnix.nixosModules.observability` when a service publishes to Home Assistant. It turns userborn off, so it is not for a NixOS host.

## Files

```
default.nix           the options, the scripts as nix packages, their units and timers
backup/vzdump-hook    the dispatcher at /etc/vzdump-hook
backup/obs-hook       per-job summary to Home Assistant, a dispatcher child
backup/obs-register   the backup entities, created once at boot
backup/offsite        ships one guest's archive with rclone, a dispatcher child
backup/setup-s3       the laptop side of an offsite domain, the setup-s3 package
health/report         NIC hang count, boot time and heartbeat, every five minutes
health/register       the health entities, created once at boot
power/pin             keeps the NIC and the backup disk awake after powertop
```

Each script is wrapped with `writeShellApplication`, so shellcheck runs at build time, and its values come from the options as shell variables set before the script body.

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.node.ssh` | required | The ssh destination of the node. |
| `dnix.node.sudoPasswordRef` | required | The reference `readSecret` resolves to the node's sudo password. |
| `dnix.node.area` | required by the sensors | The Home Assistant area the backup and health devices are suggested into. |
| `dnix.node.backup.disk` | `null` | The backup disk: `uuid`, `mount` (its systemd mount unit must exist) and `storage` (its Proxmox storage id). Adds a udev rule that starts the mount when the disk appears. |
| `dnix.node.backup.localStorage` | `local` | The Proxmox storage id of the local backup job. |
| `dnix.node.backup.observability.enable` | `false` | Publishes each backup job to Home Assistant as the `backup_<node>` device, in external, local and disk tiers. Needs `backup.disk`. |
| `dnix.node.backup.observability.expireAfter` | `108000` | Seconds before the external job's last run reads as unavailable. |
| `dnix.node.backup.offsite.<name>` | `{ }` | Ships guest `vmid`'s archive and log to the rclone remote `remote`, read from the config file `rcloneConfig`, only from the job on `storage` (default `backup.disk.storage`) and only on ISO `weekday` (1 is Monday). |
| `dnix.node.backup.hooks` | `[ ]` | More dispatcher children, as packages with a main program. |
| `dnix.node.health.enable` | `false` | Publishes the `health_<node>` device: e1000e `Hardware Unit Hang` lines this boot, boot time and a heartbeat. |
| `dnix.node.health.nic` | required by health | The e1000e interface the hang sensor reports on. |
| `dnix.node.health.expireAfter` | `1200` | Seconds before the heartbeat reads as unavailable. |
| `dnix.node.power.enable` | `false` | Runs `powertop --auto-tune` after the guests start, sets every CPU to powersave, then pins the NIC and the disk below on. |
| `dnix.node.power.nic` | `null` | The interface whose runtime power management stays on. |
| `dnix.node.power.diskUuid` | `null` | The filesystem UUID of a USB disk whose device stays awake. |

```nix
dnix.node = {
  ssh = "pve";
  sudoPasswordRef = "op://Vault/pve/password";
  area = "Office";
  backup = {
    disk = { uuid = "0b4c…"; mount = "/mnt/usb"; storage = "usb"; };
    observability.enable = true;
    offsite.ha = {
      vmid = 100;
      remote = "ha-crypt";
      rcloneConfig = config.dnix.secrets.files."rclone-ha.conf".path;
      weekday = 6;
    };
  };
  health = { enable = true; nic = "eno1"; };
  power = { enable = true; nic = "eno1"; diskUuid = "0b4c…"; };
};
```

## Backups

Every vzdump job that should be watched names `/etc/vzdump-hook` as its hook script. The dispatcher runs every child for every phase and always exits zero, because vzdump aborts the job on a failing hook. It exists while at least one child is configured.

`obs-hook` records the job start, each guest's outcome and archive size, and publishes the summary at `job-end` or `job-abort`. Only `job-end` sets `last_run`, so an aborted job trips the dead man's switch. `obs-register` creates the entities at boot and seeds `last_run` from the newest archive on the disk.

An `offsite.<name>` child copies at `backup-end` and `log-end`. The rclone config is the caller's: a crypt remote over S3 fits, as a `dnix.secrets` file whose template holds the four references `setup-s3` stored.

`setup-s3` converges the cloud side of one offsite domain from the laptop: a scoped IAM user, its inline policy and access key, two crypt passwords stored in a 1Password item, and a bucket lifecycle rule merged into the existing ones. It is dry-run unless `--apply`.

```sh
nix run github:delucca/dnix#setup-s3 -- --bucket my-archive --region eu-west-1 --prefix ha --op-vault Private
```

`--bucket`, `--region`, `--prefix` and `--op-vault` are required. `--user` defaults to `<prefix>-backup`, `--op-item` to `<prefix>-s3-backup` and `--expire-days` to 35. `--account` warns when the caller is in another AWS account.
