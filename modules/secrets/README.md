# secrets

Files a host needs at runtime whose values must not enter the store: a broker password, an rclone config with its keys, a tailscale auth key. The host declares each file as a template holding references, and the switch on the deploying machine renders and pushes it (see [`estateScripts`](../../lib/README.md)). The host keeps the rendered file on disk, so a boot reads it locally and needs neither the network nor the deploying machine.

The guest and node modules import it; a flake can also take it alone as `dnix.nixosModules.secrets`.

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.secrets.dir` | `/var/lib/dnix/secrets` | Where the files live, created root `0700` by the first push. |
| `dnix.secrets.files.<name>.template` | required | The file's text, with references in place of values in the form the deploying machine's `renderSecret` resolves, such as `{{ op://Vault/item/field }}` for `op inject`. |
| `dnix.secrets.files.<name>.owner` | `root` | The file's owner. |
| `dnix.secrets.files.<name>.group` | `root` | The file's group. |
| `dnix.secrets.files.<name>.mode` | `0400` | The file's mode. |
| `dnix.secrets.files.<name>.path` | read-only | `<dir>/<name>`, what a consumer points at. |

```nix
dnix.secrets.files.mqtt_password.template = "{{ op://Vault/mqtt/password }}";
dnix.observability.broker.passwordFile = config.dnix.secrets.files.mqtt_password.path;
```

A changed value reaches the host only on a switch with `DNIX_SECRETS_REFRESH=1`. A unit that reads the file once at start needs a restart after it.
