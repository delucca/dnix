# guest

The module every Proxmox guest composes. `default.nix` holds what a guest is regardless of how Proxmox runs it: ssh with the given keys, the admin user, and the `dnix.guest` block a deploy script turns into a create command. The other two files are the platform halves, one of which `dnix.guest.platform` selects.

A flake takes it as `dnix.nixosModules.guest`. Importing it makes the host a guest; there is no `enable`.

## Files

```
default.nix   the guest options and what both platforms share
lxc.nix       the Proxmox LXC platform
vm.nix        the QEMU VM platform
```

Both platform files are imported unconditionally and switch themselves off on `dnix.guest.platform`. Picking `imports` from a config value is infinite recursion, so the choice has to happen in `config`.

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.guest.platform` | `lxc` | Which platform half applies, `lxc` or `vm`. |
| `dnix.guest.node` | required | The Proxmox node that runs the guest, a `systemConfigs` name in the same flake. |
| `dnix.guest.vmid` | required | The Proxmox id, unique across the nodes. |
| `dnix.guest.cores` | `1` | Cores handed to the guest. |
| `dnix.guest.memory` | `1024` | Memory in MiB. |
| `dnix.guest.swap` | `512` | Swap in MiB. LXC only. |
| `dnix.guest.rootfs` | `local-lvm:8` | Root storage and its size in GiB. |
| `dnix.guest.extraDisks` | `[ ]` | Further disks in the same form, attached in order after the root one. VM only. |
| `dnix.guest.devices` | `[ ]` | Host devices passed into the container, each as `pct set --devN` takes it, after the `/dev/net/tun` every container gets. LXC only. |
| `dnix.guest.mounts` | `[ ]` | Further mount point volumes, each as `pct set --mpN` takes it (`storage:size,mp=/path,backup=1`). LXC only, applied once at create. |
| `dnix.guest.hwaddr` | required | The NIC's MAC. |
| `dnix.guest.description` | `""` | The note Proxmox shows next to the guest. |
| `dnix.guest.adminUser` | `null` | A wheel user with passwordless sudo and the same keys as root. None while `null`. |
| `dnix.guest.authorizedKeyFiles` | `[ ]` | Public key files that may ssh in as root and as the admin user. |

Nothing reads the sizing options at build time. They exist so the create command and the configuration the guest boots come from one file.

```nix
dnix.guest = {
  node = "pve";
  vmid = 105;
  hwaddr = "BC:24:11:00:00:01";
  adminUser = "me";
  authorizedKeyFiles = [ ./laptop.pub ];
};
```

## The platforms

- **lxc** imports nixpkgs' `proxmox-lxc` module, which brings the container boot path, networkd and the getty Proxmox expects on tty1. The hostname is managed here rather than picked up from `/etc/hostname`, and `eth0` takes its address over DHCP.
- **vm** declares what a QEMU guest needs and an LXC gets from its host: systemd-boot on the EFI partition, the virtio and scsi modules in the initrd, a console on both the virtual display and the serial port, the root filesystem by label with the partition grown to fill a resized disk, and the qemu guest agent so Proxmox can read the guest's address and shut it down cleanly.
