# observability

Publish service health to Home Assistant through MQTT discovery with the `ha-mqtt` CLI.
The module works with NixOS or system-manager. Services compute and publish their own state; systemd remains their supervisor.

## Use

Provide a reachable MQTT broker and a runtime password file readable by the calling service.
With [the dnix input available](../../README.md#use-a-module), add:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.nixosModules.observability ];
  dnix.observability = {
    enable = true;
    broker = {
      host = "mqtt.example.net";
      user = "publisher";
      passwordFile = "/run/credentials/mqtt-password";
    };
  };
}
```

The module installs the CLI; it does not create the password file, configure a broker or schedule reports. See [the option definitions](default.nix) for broker, device and discovery settings. The default broker port is 1883.

## Publish a heartbeat

After activation, register an entity and publish its current state:

```sh
ha-mqtt discover sensor heartbeat --device backup --name Heartbeat \
  --device-class timestamp --expire-after 93600 --attrs
ha-mqtt state heartbeat --device backup --now --attr duration_s=42
```

`discover` publishes a retained discovery configuration. `state` publishes a value, JSON attributes or both. `undiscover <component> <object> --device <device>` clears the discovery, state and attributes topics. See [the CLI source](ha-mqtt.sh) for supported flags.

Configuration defaults can be overridden per call through `HA_MQTT_HOST`, `HA_MQTT_PORT`, `HA_MQTT_USER`, `HA_MQTT_PASSWORD_FILE`, `HA_MQTT_DISCOVERY_PREFIX` and the `HA_MQTT_DEVICE_*` manufacturer/model variables. `HA_MQTT_DEVICE` sets the default device; otherwise both device and broker username default to the calling user's name.

## Service behavior and credentials

Retained state survives a stopped publisher. Use a heartbeat with `--expire-after` and alert on `unavailable` to detect missing runs.
Call reporting best effort, for example `ha-mqtt ... || true` or a `-` prefix on a systemd command, when reporting failure must not fail the service itself.

The password is read from its file on each invocation, then passed on `mosquitto_pub`'s command line. Local users able to inspect that process can see it while publication runs. The wrapper does not configure MQTT TLS.
