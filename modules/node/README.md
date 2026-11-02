# node

The system-manager base of a Proxmox node: the `dnix.node` block the deploy scripts reach the node through, and opt-in node services: a vzdump hook chain with Home Assistant sensors and offsite copies, host health sensors, power tuning, a GPU handed between VMs, and kernel module options with the initramfs rebuilt to match. A flake takes it as `dnix.nixosModules.node` in a `system-manager.lib.makeSystemConfig`, next to `dnix.nixosModules.observability` when a service publishes to Home Assistant. It turns userborn off, so it is not for a NixOS host.

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
gpu/allocate.pl       the Proxmox hookscript that moves the GPU onto the starting VM
gpu/allocate.nix      writes the VM list and the device line above the hookscript
gpu/reprime           the full stop and start a cross-VM handoff needs
gpu/assign            sets the hookscript on each GPU VM, at every switch and boot
gpu/test.sh           drives the hookscript against a stub qm
modprobe/refresh      rebuilds the initramfs when a modprobe file changes
test.nix              the flake check node
```

Each shell script is wrapped with `writeShellApplication`, so shellcheck runs at build time, and its values come from the options as shell variables set before the script body. The hookscript is Perl, as Proxmox runs it, and gets its values the same way; `perl -c` checks it at build time.

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
| `dnix.node.gpu.vms` | `[ ]` | The VMs that share one passthrough GPU, one at a time. |
| `dnix.node.gpu.hostpci` | required by `gpu.vms` | The `hostpci0` value a VM gets when it takes the card, such as `0000:01:00,pcie=1,x-vga=1`. |
| `dnix.node.modprobe.<name>` | `{ }` | The lines of `/etc/modprobe.d/<name>.conf`. A change rebuilds the initramfs and touches `/run/reboot-required`. |

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
      rcloneConfig = "/var/lib/secrets/rclone-ha.conf";
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

An `offsite.<name>` child copies at `backup-end` and `log-end`. The rclone config is the caller's: a crypt remote over S3 fits, as a root-only file holding the four values `setup-s3` stored.

`setup-s3` converges the cloud side of one offsite domain from the laptop: a scoped IAM user, its inline policy and access key, two crypt passwords stored in a 1Password item, and a bucket lifecycle rule merged into the existing ones. It is dry-run unless `--apply`.

```sh
nix run github:delucca/dnix#setup-s3 -- --bucket my-archive --region eu-west-1 --prefix ha --op-vault Private
```

`--bucket`, `--region`, `--prefix` and `--op-vault` are required. `--user` defaults to `<prefix>-backup`, `--op-item` to `<prefix>-s3-backup` and `--expire-days` to 35. `--account` warns when the caller is in another AWS account.

## GPU handoff

Some cards, an RTX 5070 Ti among them, cannot move to a different VM without a full QEMU exit: no host-side reset, no romfile and no warm guest reboot brings them up, only a stop and start of the same VM. `gpu.vms` handles that for one card shared by several VMs.

At switch and at every boot, `pve-gpu-hookscript` sets `local:snippets/gpu-allocate.pl` as the hookscript of each VM in the list that exists. The `local` storage must allow the `snippets` content type. Adding a VM to the list takes effect at the next switch.

Before a VM starts, the hookscript aborts the start if another VM in the list is running. Otherwise it removes the `hostpci0` line from the others and writes it into the starting VM's config. Proxmox reads a VM's config before it runs the hook and does not read it again, so when the card came from a different VM, the first boot runs without a usable card. After that boot starts, the hookscript launches `gpu-reprime` as a transient unit: it waits 90 seconds, shuts the VM down (forcing it after 45) and starts it again. Both log to `/var/log/gpu-allocate.log`.

The configs are the record of who held the card last, so a handoff across a host reboot still gets its reprime. Only the VMs in the list are read and written: a `hostpci0` line on any other VM is taken to be some other device. The cost is that a card passed to a VM outside the list by hand is invisible to that record, and a handoff from it can skip the reprime.

```nix
dnix.node = {
  gpu = {
    vms = [ 100 101 ];
    hostpci = "0000:01:00,pcie=1,x-vga=1";
  };
  modprobe.vfio = ''
    options vfio-pci ids=10de:2c05,10de:22e9
    softdep nouveau pre: vfio-pci
    blacklist nouveau
  '';
};
```

## Kernel modules

Each `modprobe.<name>` is written to `/etc/modprobe.d` as a real file, not a link into the store, since `update-initramfs` copies that directory. When the set of files changes, `pve-modprobe-refresh` checks that every file is in place, runs `update-initramfs -u -k all` and touches `/run/reboot-required`. It keeps a stamp under `/var/lib/pve-modprobe-refresh`, so an unchanged set never rebuilds.
