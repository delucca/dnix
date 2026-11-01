# lib

Functions that turn a flake's hosts into the scripts that check, build, switch and bootstrap them. Each returns an attrset of derivations named `<verb>-<host>`; a flake maps them to `apps` and adds them to `checks`, so a broken script fails `nix flake check`. Every script runs from the flake's root.

```nix
scripts = dnix.lib.darwinScripts { inherit self pkgs; }
  // dnix.lib.estateScripts {
    inherit self pkgs;
    builder = "builder";
    readSecret = "op read";
    templateNode = "pve";
  };
apps.aarch64-darwin = builtins.mapAttrs (_: drv: { type = "app"; program = lib.getExe drv; }) scripts;
```

## darwinScripts

For every `darwinConfigurations` host: `check-` evaluates it, `build-` builds it, `switch-` builds it as the user then runs `darwin-rebuild switch` under sudo, `bootstrap-` runs `bootstrap host` (default `hosts/<host>/bootstrap`).

| Argument | Default | What it is |
|---|---|---|
| `self`, `pkgs` | required | The flake and the pkgs the scripts are built with. |
| `bootstrap` | `host: "hosts/${host}/bootstrap"` | The script `bootstrap-<host>` runs. |

## estateScripts

For every `nixosConfigurations` host, a guest built with [the guest module](../modules/guest/README.md), and every `systemConfigs` host, a node built with [the node module](../modules/node/README.md). Builds run on `builder`: the derivation is copied there, built, and the result copied on.

- A guest: `switch-` is `nixos-rebuild` with `--build-host builder`, onto `root@<host>` or the first argument. `bootstrap-` creates the guest on its node with `pct create` from the staged template or `qm create` from the staged disk image, starts it and prints its address and age recipient.
- A node: `switch-` copies the closure to the node and activates it under sudo, with the password `readSecret` returns. `bootstrap-` runs `bootstrap host`.
- `template` and `vm-image` build the flake's `packages.x86_64-linux.lxc-template` and `vm-image` and stage them in `/tmp` on `templateNode` and `imageNode`, where `bootstrap-` picks them up.

| Argument | Default | What it is |
|---|---|---|
| `self`, `pkgs` | required | The flake and the pkgs the scripts are built with. |
| `builder` | required | The ssh destination that builds every Linux closure. |
| `readSecret` | required | A command that prints the secret its one argument names, such as `op read`. |
| `bootstrap` | `host: "hosts/${host}/bootstrap"` | The script a node's `bootstrap-<host>` runs. |
| `guestSecrets` | `host: node: "hosts/${node}/guests/secrets/${host}.yaml"` | The sops file `bootstrap-` tells you to re-key for a new guest. |
| `template` | `nixos-dnix.tar.xz` | The LXC template's file name on the node. |
| `vmImage` | `nixos-dnix.qcow2` | The disk image's file name on the node. |
| `vmStaging` | `/var/lib/vz/dnix` | Where a VM's disk image waits on the node before `qm` imports it. |
| `templateNode` | `null` | The node `template` stages onto. No `template` script while `null`. |
| `imageNode` | `null` | The node `vm-image` stages onto. No `vm-image` script while `null`. |

## Files

```
default.nix     the two functions
create-lxc.sh   the body of a container's bootstrap, after the preamble estateScripts writes
create-vm.sh    the body of a VM's bootstrap
tests/          create-vm.sh's refusal paths against stubbed ssh, sudo and qm
```
