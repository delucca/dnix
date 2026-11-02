# node

Add backup hooks, health reporting, power tuning and GPU handoff to a Proxmox node managed through system-manager.
Although exported as `nixosModules.node`, this module targets Debian-based Proxmox: it disables userborn and sets `x86_64-linux`. It is not a NixOS host base.

## Use

Import the module into your consumer's `system-manager.lib.makeSystemConfig` module list. There is no top-level enable switch; services are opt-in.
With [the dnix input available](../../README.md#use-a-module), a minimal module is:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.nixosModules.node ];
  dnix.node = {
    ssh = "root@example-node";
    sudoPasswordRef = "consumer-defined-reference";
  };
}
```

The SSH destination and password reference are metadata for consumer deployment tooling. This repository does not resolve that reference or deploy the node.
See [the option definitions](default.nix) for service settings. Backup sensors and health reporting also need the [observability module](../observability/README.md), broker configuration and `dnix.node.area`.

## Backups

Configure each relevant vzdump job to use `/etc/vzdump-hook`. The module installs that dispatcher when at least one child hook is configured. It runs all children and exits successfully even when a child fails, so reporting or offsite errors do not abort a local backup.

`backup.observability.enable` requires `backup.disk`; the consumer must supply its systemd mount unit. Backup sensors report outcomes and archive sizes. Only a completed job advances `last_run`, so an abort eventually makes that heartbeat unavailable.

`backup.offsite.<name>` copies one guest's archive and log through rclone on the configured storage and ISO weekday. Supply the runtime `rcloneConfig` file yourself. Storage defaults to `backup.disk.storage`; set it explicitly when no backup disk is configured.

The [setup-s3 helper](backup/setup-s3), exported only for `aarch64-darwin`, prepares a scoped IAM user, access key, rclone crypt passwords in 1Password and a bucket lifecycle rule. It requires working AWS credentials and an authenticated `op` executable on PATH. This example uses placeholder resource names:

```sh
nix run github:delucca/dnix#setup-s3 -- \
  --bucket example-backups --region us-east-1 \
  --prefix example --op-vault Example
```

It is a dry run unless `--apply` is supplied, but still reads AWS and 1Password. The consumer provisions the node's rclone configuration from the resulting credentials.

## GPU and host changes

`gpu.vms` shares one GPU through `hostpci0`. Configure every VM that can hold it, set `gpu.hostpci`, and allow `snippets` on Proxmox's `local` storage. Activation assigns the hookscript to listed VMs, replacing an existing hookscript setting.

The hook refuses a start while another listed VM is active. A handoff from a different listed VM schedules a full stop and start after 90 seconds, forcing a stop if graceful shutdown does not finish within 45 seconds. VM configurations record the last holder; manually assigning the card outside the list bypasses that record. See the [allocation hook](gpu/allocate.pl) and [restart helper](gpu/reprime).

`power.enable` runs powertop autotuning and selects the powersave governor; NIC and USB disk exceptions are configurable. Changes to `modprobe` files rebuild the initramfs and mark `/run/reboot-required`.
