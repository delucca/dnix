{ pkgs }:

let
  eval = pkgs.lib.evalModules {
    modules = [
      ./default.nix
      {
        options.environment.systemPackages = pkgs.lib.mkOption { type = pkgs.lib.types.listOf pkgs.lib.types.package; };
        config._module.args = { inherit pkgs; };
        config.dnix.observability = {
          enable = true;
          broker = { host = "127.0.0.1"; port = 18830; user = "probe"; passwordFile = "/run/secrets/probe"; };
          device.manufacturer = "acme";
        };
      }
    ];
  };
  cli = pkgs.lib.getExe eval.config.dnix.observability.package;
in
pkgs.runCommand "observability" {
  nativeBuildInputs = [ pkgs.mosquitto pkgs.jq ];
  __darwinAllowLocalNetworking = true;
} ''
  set -euo pipefail
  [ "${toString (map (p: p.name) eval.config.environment.systemPackages)}" = ha-mqtt ]

  echo secret > password
  export HA_MQTT_PASSWORD_FILE="$PWD/password"
  printf 'listener 18830 127.0.0.1\nallow_anonymous true\nlog_dest none\n' > broker.conf
  mosquitto -c broker.conf & broker=$!
  trap 'kill $broker' EXIT
  for _ in $(seq 50); do mosquitto_pub -h 127.0.0.1 -p 18830 -t ping -m x 2>/dev/null && break; sleep 0.1; done

  retained() { mosquitto_sub -h 127.0.0.1 -p 18830 -t "$1" -W 1 2>/dev/null || true; }
  fail() { echo "FAIL: $*" >&2; exit 1; }

  ${cli} discover sensor heartbeat --device svc --name Heartbeat --device-class timestamp --expire-after 900 --attrs
  config="$(retained homeassistant/sensor/svc/heartbeat/config)"
  echo "$config" | jq -e '.unique_id == "svc_heartbeat" and .state_topic == "svc/heartbeat/state"
    and .json_attributes_topic == "svc/heartbeat/attrs" and .expire_after == 900
    and .device == {identifiers: ["svc"], name: "svc", manufacturer: "acme"}' >/dev/null || fail "discover payload: $config"

  HA_MQTT_DEVICE_MODEL=worker HA_MQTT_DEVICE_MANUFACTURER=other ${cli} discover switch run --device svc
  config="$(retained homeassistant/switch/svc/run/config)"
  echo "$config" | jq -e '.device.model == "worker" and .device.manufacturer == "other"
    and .command_topic == "svc/run/command"' >/dev/null || fail "env override: $config"

  ${cli} state heartbeat 2026-01-01T00:00:00+00:00 --device svc --attr count=3 --attr note=ok
  [ "$(retained svc/heartbeat/state)" = 2026-01-01T00:00:00+00:00 ] || fail "state value"
  [ "$(retained svc/heartbeat/attrs)" = '{"count":3,"note":"ok"}' ] || fail "attrs: $(retained svc/heartbeat/attrs)"

  ${cli} undiscover sensor heartbeat --device svc
  [ -z "$(retained 'homeassistant/sensor/svc/heartbeat/config')$(retained 'svc/heartbeat/#')" ] || fail "undiscover left retained topics"

  set +e
  HA_MQTT_PASSWORD_FILE=/nonexistent ${cli} state heartbeat x --device svc 2>/dev/null
  [ $? -eq 2 ] || fail "missing password file must exit 2"
  set -e

  echo ok > $out
''
