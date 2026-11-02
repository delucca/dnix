# dnix

dnix provides shared Nix modules for developer environments, agent tools and Proxmox services.
Import the modules into your own Home Manager, nix-darwin or system-manager configuration and supply the machine-specific settings there.

## Use a module

You need Nix with flakes enabled and a consumer configuration for the relevant module system.
This minimal flake exports a Home Manager module with dnix's shell enabled:

```nix
{
  inputs.dnix.url = "github:delucca/dnix";

  outputs = { dnix, ... }: {
    homeManagerModules.default = {
      imports = [ dnix.homeManagerModules.shell ];
      dnix.shell.enable = true;
    };
  };
}
```

Import that module into your Home Manager configuration and keep the consumer's `flake.lock` in version control.
The module README examples use an `inputs` argument: pass it through Home Manager's `extraSpecialArgs`, or your system configuration's `specialArgs`.
Your consumer owns host definitions, credentials and activation or deployment commands.

## Modules

The [flake outputs](flake.nix) export these modules individually; there is no combined default module.

| Export | Purpose and documentation |
|---|---|
| `homeManagerModules.ai` | [Agent harnesses, shared skills and instructions](modules/ai/README.md) |
| `homeManagerModules.aws` | [AWS profiles with runtime credentials](modules/aws/README.md) |
| `homeManagerModules.desktop` | [Desktop apps, Chrome, Ghostty and Git](modules/desktop/README.md) |
| `homeManagerModules.developer` | [Repository roster and Developer tree](modules/developer/README.md) |
| `homeManagerModules.notebooks` | [Notebook instructions and optional backups](modules/notebooks/README.md) |
| `homeManagerModules.shell` | [Zsh, completion and prompt defaults](modules/shell/README.md) |
| `homeManagerModules.ssh` | [SSH aliases with LAN and Tailscale routing](modules/ssh/README.md) |
| `darwinModules.ai` | [System policy files for the primary user's agent harnesses](modules/ai/README.md) |
| `darwinModules.nix` | [Flakes, garbage collection, store optimisation and free-space limits](modules/nix/default.nix) |
| `nixosModules.guest` | [NixOS LXC guest base for Proxmox](modules/guest/README.md) |
| `nixosModules.node` | [Proxmox node services through system-manager](modules/node/README.md) |
| `nixosModules.observability` | [Home Assistant MQTT publisher for NixOS or system-manager](modules/observability/README.md) |

The Darwin `nix` module uses `dnix.nix.enable = true`. The guest and node modules take effect on import; other enable switches and prerequisites are documented in their READMEs.

## Packages and checks

`packages.aarch64-darwin.setup-s3` prepares an offsite backup domain; see the [node README](modules/node/README.md#backups).
`checks.aarch64-darwin` covers the agent tools, AWS, node helpers and observability.
These package and check outputs are exported only for `aarch64-darwin`; that does not describe the platform support of every module.

## Project policies

This repository does not declare a contribution policy or a license.
