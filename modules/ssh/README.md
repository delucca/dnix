# ssh

Give a machine one SSH alias across LAN and Tailscale, with separate service and administrator aliases for tailnet-only guests.
The Home Manager module writes `~/.ssh/config` and includes `config.d/*` for additional configuration.

## Use

With [the dnix input available](../../README.md#use-a-module), add your routing names and login users:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.homeManagerModules.ssh ];
  dnix.ssh = {
    enable = true;
    tailnet = "example.ts.net";
    identityFile = "~/.ssh/id_ed25519";
    hosts.server = {
      tailscale = "server";
      lan = "server.local";
      user = "operator";
    };
    guests.web = { tailscale = "web"; service = "web"; admin = "root"; };
  };
}
```

You supply access to the tailnet and any keys or agent. See [the option definitions](default.nix) for forwarding, multiplexing, GitHub over port 443 and agent socket configuration.

## Routing and aliases

A `hosts` alias probes port 22 on the LAN destination and uses it only if it answers with an SSH banner. Otherwise the [fallback helper](fallback-helper.sh) connects to `<tailscale>.<tailnet>`, using the IPv4 returned by `tailscale ip` when that CLI is available. The banner check detects SSH service availability; it does not authenticate the destination.

Both routes share the alias's host-key record through `HostKeyAlias`. `StrictHostKeyChecking accept-new` records a first key automatically and rejects a changed key. Multiplexing is enabled by default, with connections retained for one hour.

A `guests` entry creates `<alias>` for its `service` user and `<alias>-admin` for its `admin` user. Both connect directly through Tailscale using `identityFile`. With `identityFile = null`, no guest aliases are rendered.

## Local configuration

`agentSocket` sets both `IdentityAgent` and the session's `SSH_AUTH_SOCK`; `AddKeysToAgent` applies to all hosts. Activation creates `~/.ssh/sockets` and sets it and `~/.ssh` to mode 700.

The helper uses `nc` when available, otherwise Bash's TCP support with `timeout` for probes. `SSH_FALLBACK_DEBUG=1 ssh server` prints its chosen route. Extend the generated settings through `programs.ssh.settings` or `programs.ssh.includes`.
