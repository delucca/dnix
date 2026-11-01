{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.observability;
  env = lib.filterAttrs (_: v: v != null) {
    HA_MQTT_HOST = cfg.broker.host;
    HA_MQTT_PORT = toString cfg.broker.port;
    HA_MQTT_USER = cfg.broker.user;
    HA_MQTT_PASSWORD_FILE = cfg.broker.passwordFile;
    HA_MQTT_DISCOVERY_PREFIX = cfg.discoveryPrefix;
    HA_MQTT_DEVICE_MANUFACTURER = cfg.device.manufacturer;
    HA_MQTT_DEVICE_MODEL = cfg.device.model;
  };
  package = pkgs.writeShellApplication {
    name = "ha-mqtt";
    runtimeInputs = [ pkgs.mosquitto pkgs.jq ];
    text = lib.concatStrings (lib.mapAttrsToList (k: v: "export ${k}=\${${k}:-${lib.escapeShellArg v}}\n") env)
      + builtins.readFile ./ha-mqtt.sh;
  };
in
{
  options.dnix.observability = {
    enable = lib.mkEnableOption "the ha-mqtt publisher";
    broker = {
      host = lib.mkOption { type = lib.types.str; };
      port = lib.mkOption {
        type = lib.types.port;
        default = 1883;
      };
      user = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
      };
      passwordFile = lib.mkOption { type = lib.types.str; };
    };
    discoveryPrefix = lib.mkOption {
      type = lib.types.str;
      default = "homeassistant";
    };
    device = {
      manufacturer = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
      };
      model = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
      };
    };
    package = lib.mkOption {
      type = lib.types.package;
      readOnly = true;
      default = package;
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
  };
}
