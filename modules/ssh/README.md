# ssh

The home-manager module that renders `~/.ssh/config`: a host reachable both on the LAN and over tailscale is reached through whichever answers, under one alias, and a tailnet-only host gets two aliases, one per user. A flake takes it as `dnix.homeManagerModules.ssh` and a host sets `dnix.ssh.enable = true`.

## Files

```
default.nix          the options and the `programs.ssh` settings built from them
fallback-helper.sh   the ProxyCommand behind every `hosts` alias
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.ssh.enable` | `false` | Turns the module on. |
| `dnix.ssh.tailnet` | required once `hosts` or `guests` is set | The tailnet domain appended to every `tailscale` name. |
| `dnix.ssh.identityFile` | `null` | The key the `guests` aliases use. While it is `null` no guest alias is rendered. |
| `dnix.ssh.agentSocket` | `null` | The ssh agent socket, such as 1Password's. Sets `IdentityAgent` for every host and `SSH_AUTH_SOCK` for the session. |
| `dnix.ssh.githubOver443` | `false` | Reaches `github.com` through `ssh.github.com` on port 443, for networks that block port 22. |
| `dnix.ssh.hosts.<alias>` | none | A host reached LAN first, tailscale second. |
| `dnix.ssh.guests.<alias>` | none | A host reached over tailscale only, with a service and an admin user. |

A `hosts` entry:

| Field | Default | Meaning |
|---|---|---|
| `tailscale` | required | the machine name on the tailnet |
| `lan` | required | its LAN address or name |
| `user` | required | the login |
| `mux` | `true` | multiplex connections under `~/.ssh/sockets` for an hour |
| `forwardAgent` | `false` | forward the ssh agent |
| `forwards` | none | `LocalForward` values |

A `guests` entry takes `tailscale`, `service` and `admin`.

```nix
dnix.ssh = {
  enable = true;
  tailnet = "example.ts.net";
  identityFile = "~/.ssh/id_ed25519";
  agentSocket = "/Users/me/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock";
  githubOver443 = true;
  hosts.nas = { tailscale = "nas"; lan = "192.168.1.10"; user = "me"; forwardAgent = true; };
  guests.web = { tailscale = "web"; service = "web"; admin = "root"; };
};
```

## What it renders

- **A `hosts` alias** connects through `ssh-fallback-helper <tailscale fqdn> <lan> 22`. `HostKeyAlias` is the alias, so both routes share one `known_hosts` entry. First contact records the host key (`StrictHostKeyChecking accept-new`), so a job with no terminal can reach a new host; only a changed key refuses.
- **A `guests` alias** `<alias>` logs in as `service` and `<alias>-admin` as `admin`, both straight to the tailscale name with `identityFile`.
- `AddKeysToAgent` for every host, `IdentityAgent` too when `agentSocket` is set, and an include of `config.d/*`, for config the module does not own.
- `~/.ssh` and `~/.ssh/sockets`, mode 700.

Anything else goes in `programs.ssh.settings` and `programs.ssh.includes` next to it.

## The fallback helper

It probes the LAN address for two seconds and uses it only when the port answers with an SSH banner, so a foreign network that happens to route the same address does not capture the connection. Otherwise it connects to the tailscale name, resolved to its IPv4 through `tailscale ip` when the CLI is there. It uses `nc`, picking the connect-timeout flag by flavour (ncat, macOS, OpenBSD), and falls back to bash's `/dev/tcp` without it.

`SSH_FALLBACK_DEBUG=1 ssh <alias>` prints the route it chose.
