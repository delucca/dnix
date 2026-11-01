# node

The system-manager base of a Proxmox node: the `dnix.node` block the deploy scripts reach the node through, and sops-nix set up to work under system-manager. A flake takes it as `dnix.nixosModules.node` in a `system-manager.lib.makeSystemConfig`, next to sops-nix's NixOS module. It turns userborn off, so it is not for a NixOS host.

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.node.ssh` | required | The ssh destination of the node. |
| `dnix.node.sudoPasswordRef` | required | The reference `readSecret` resolves to the node's sudo password. |
