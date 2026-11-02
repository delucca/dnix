# guest

Provide a NixOS base for an x86_64 Proxmox LXC container, with SSH, DHCP and optional administrator access.
Importing the module activates it; there is no `dnix.guest.enable` switch, and it does not configure a QEMU VM.

## Use

With [the dnix input available](../../README.md#use-a-module), add this module to your NixOS container configuration:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.nixosModules.guest ];
  dnix.guest = {
    node = "example-node";
    vmid = 105;
    hwaddr = "02:00:00:00:00:01";
  };
}
```

Supply `dnix.guest.authorizedKeyFiles` with your public key files before deployment. Root receives those keys; setting `adminUser` also creates a normal wheel user with the same keys and passwordless sudo. SSH password authentication is disabled.

## Container and deployment boundaries

The module imports nixpkgs' `proxmox-lxc` base, manages the hostname, and requests DHCP on `eth0`. Network-online waits for IPv4. It sets the platform to `x86_64-linux` and the NixOS state version to `26.05`.

`node`, `vmid`, `hwaddr`, resource sizing, devices and mounts are metadata for the consumer's deployment tooling. The module does not create the container or apply that metadata to Proxmox. The consumer owns provisioning and deployment.

See [the option definitions](default.nix) for the metadata fields, default sizing, Nix settings and container configuration.
