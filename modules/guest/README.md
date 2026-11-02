# guest

The module every Proxmox container guest composes: ssh with the given keys, the admin user, the LXC base, and the `dnix.guest` block a deploy script turns into a create command.

A flake takes it as `dnix.nixosModules.guest`. Importing it makes the host a guest; there is no `enable`.

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.guest.node` | required | The Proxmox node that runs the guest, a `systemConfigs` name in the same flake. |
| `dnix.guest.vmid` | required | The Proxmox id, unique across the nodes. |
| `dnix.guest.cores` | `1` | Cores handed to the guest. |
| `dnix.guest.memory` | `1024` | Memory in MiB. |
| `dnix.guest.swap` | `512` | Swap in MiB. |
| `dnix.guest.rootfs` | `local-lvm:8` | Root storage and its size in GiB. |
| `dnix.guest.devices` | `[ ]` | Host devices passed into the container, each as `pct set --devN` takes it, after the `/dev/net/tun` every container gets. |
| `dnix.guest.mounts` | `[ ]` | Further mount point volumes, each as `pct set --mpN` takes it (`storage:size,mp=/path,backup=1`), applied once at create. |
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

## The container

It imports nixpkgs' `proxmox-lxc` module, which brings the container boot path, networkd and the getty Proxmox expects on tty1. The hostname is managed here rather than picked up from `/etc/hostname`, and `eth0` takes its address over DHCP.
