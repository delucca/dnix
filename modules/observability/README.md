# observability

The module that lets a host's services show up in Home Assistant through MQTT discovery. It installs `ha-mqtt`, a CLI that publishes retained discovery configs and states to the broker, then exits: a service computes its own health and pushes it, Home Assistant displays it, watches it and alerts on it. systemd stays the supervisor; call `ha-mqtt` from a unit's hooks or from the service at the end of a run.

A flake takes it as `dnix.nixosModules.observability`. It sets only `environment.systemPackages`, so it works under NixOS and system-manager alike.

## Files

```
default.nix   the options and the ha-mqtt package built from them
ha-mqtt.sh    the CLI
test.nix      the check: the built CLI against a throwaway local broker
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.observability.enable` | `false` | Turns the module on and installs `ha-mqtt`. |
| `dnix.observability.broker.host` | required | The broker's address. |
| `dnix.observability.broker.port` | `1883` | The broker's port. |
| `dnix.observability.broker.user` | `null` | The broker login. `null` logs in as the calling user. |
| `dnix.observability.broker.passwordFile` | required | The file holding the broker password, read at each run, such as a sops secret's `path`. |
| `dnix.observability.discoveryPrefix` | `homeassistant` | Home Assistant's discovery prefix. |
| `dnix.observability.device.manufacturer` | `null` | The manufacturer shown on every device. Left out of the payload while `null`. |
| `dnix.observability.device.model` | `null` | The model shown on every device. Left out of the payload while `null`. |
| `dnix.observability.package` | read-only | The built CLI, for scripts that need its path: `lib.getExe config.dnix.observability.package`. |

```nix
dnix.observability = {
  enable = true;
  broker = { host = "192.168.1.20"; user = "nas"; passwordFile = config.sops.secrets.mqtt_password.path; };
  device.manufacturer = "me";
};
```

The options become environment defaults inside the wrapper, so a caller can override any of them for one run: `HA_MQTT_HOST`, `HA_MQTT_PORT`, `HA_MQTT_USER`, `HA_MQTT_PASSWORD_FILE`, `HA_MQTT_DISCOVERY_PREFIX`, `HA_MQTT_DEVICE_MANUFACTURER`, `HA_MQTT_DEVICE_MODEL`. `HA_MQTT_DEVICE` sets the default `--device`, which is otherwise the calling user's name.

## The CLI

```
ha-mqtt discover <component> <object> [options]   publish a retained discovery config
ha-mqtt state <object> [value] [options]          publish a state value and/or attributes
ha-mqtt undiscover <component> <object>           blank the config, state and attributes
```

Topics, for device `<d>` and object `<o>`:

| Topic | Retained | Holds |
|---|---|---|
| `<prefix>/<component>/<d>/<o>/config` | yes | the discovery config |
| `<d>/<o>/state` | yes | the state value |
| `<d>/<o>/attrs` | yes | the JSON attributes |
| `<d>/<o>/command` | | what Home Assistant sends a `switch` when toggled |

`discover` takes `--name`, `--device`, `--device-name`, `--device-id` (the device the entity groups under, when it differs from `--device`), `--suggested-area`, `--via-device`, `--device-class`, `--state-class`, `--unit`, `--icon`, `--entity-category`, `--value-template`, `--expire-after <seconds>` and `--attrs` (also publish an attributes topic). A `switch` gets a command topic.

`state` takes `--device`, `--value`, `--now` (the current UTC time as the value), `--attr k=v` (repeatable; numbers stay numbers) and `--attrs-json <object>` (published as is, and it wins over `--attr`).

```sh
ha-mqtt discover sensor heartbeat --device backup --name Heartbeat --device-class timestamp --expire-after 93600 --attrs
ha-mqtt state heartbeat --device backup --now --attr duration_s=42
ha-mqtt discover binary_sensor healthy --device backup --device-class problem
ha-mqtt state healthy OFF --device backup
```

## Using it from a service

- **Absence is the signal.** An entity that stops being published keeps its last state, so publish a heartbeat with `--expire-after` and alert when it goes `unavailable`.
- **A publish failure must never break the caller.** Call it best effort (`ha-mqtt ... || true`, or a `-` prefixed `ExecStartPost`). It still exits non-zero, so the failure shows in the journal.
- **The password is on `mosquitto_pub`'s command line**, so any local user can see it in `ps` while a publish runs, unless `/proc` is mounted with `hidepid`.
