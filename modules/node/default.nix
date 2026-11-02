{ config, lib, pkgs, utils, ... }:

let
  cfg = config.dnix.node;
  inherit (lib) mkOption mkEnableOption mkIf types;

  haMqtt = lib.getExe config.dnix.observability.package;
  common = [ pkgs.coreutils pkgs.findutils pkgs.gawk pkgs.gnugrep pkgs.gnused ];

  vars = attrs: lib.concatStrings (lib.mapAttrsToList (k: v: "${k}=${lib.escapeShellArg v}\n") attrs);

  script = { name, file, prelude, inputs ? common, strict ? false }: pkgs.writeShellApplication {
    inherit name;
    runtimeInputs = inputs;
    bashOptions = [ "nounset" "pipefail" ] ++ lib.optional strict "errexit";
    text = prelude + builtins.readFile file;
  };

  disk = cfg.backup.disk;
  diskMount = "${utils.escapeSystemdPath disk.mount}.mount";

  obsHook = script {
    name = "pve-backup-obs-hook";
    file = ./backup/obs-hook;
    inputs = common ++ [ pkgs.jq ];
    prelude = vars { HA_MQTT = haMqtt; EXTERNAL_STORAGE = disk.storage; LOCAL_STORAGE = cfg.backup.localStorage; };
  };
  obsRegister = script {
    name = "pve-backup-obs-register";
    file = ./backup/obs-register;
    strict = true;
    prelude = vars {
      HA_MQTT = haMqtt;
      EXPIRE_AFTER = toString cfg.backup.observability.expireAfter;
      EXTERNAL_DUMP = "${disk.mount}/dump";
      AREA = cfg.area;
    };
  };
  offsiteHook = name: o: script {
    name = "vzdump-hook-${name}";
    file = ./backup/offsite;
    prelude = vars {
      NAME = name;
      VMID_EXPECTED = toString o.vmid;
      CRYPT_REMOTE = o.remote;
      OFFSITE_STOREID = o.storage;
      OFFSITE_WEEKDAY = toString o.weekday;
      RCLONE = lib.getExe pkgs.rclone;
      RCLONE_CONF = o.rcloneConfig;
    };
  };
  hooks = lib.optional cfg.backup.observability.enable obsHook
    ++ lib.mapAttrsToList offsiteHook cfg.backup.offsite
    ++ cfg.backup.hooks;
  dispatcher = script {
    name = "pve-vzdump-hook";
    file = ./backup/vzdump-hook;
    inputs = [ ];
    # vzdump clears the environment, so nix's bash falls back to PATH=/no-such-path
    # and the children lose hostname and lxc-attach: restore what `path = [ "/usr" ]`
    # gives the units. Children still prepend their own runtimeInputs.
    prelude = ''
      export PATH="/usr/bin:/usr/sbin:$PATH"
      CHILDREN=(${lib.concatMapStringsSep " " lib.getExe hooks})
    '';
  };

  healthReport = script {
    name = "pve-health-report";
    file = ./health/report;
    prelude = vars { HA_MQTT = haMqtt; NIC = cfg.health.nic; };
  };
  healthRegister = script {
    name = "pve-health-register";
    file = ./health/register;
    strict = true;
    prelude = vars { HA_MQTT = haMqtt; EXPIRE_AFTER = toString cfg.health.expireAfter; AREA = cfg.area; };
  };

  powerPin = script {
    name = "pve-power-pin";
    file = ./power/pin;
    prelude = vars { NIC = toString cfg.power.nic; BACKUP_UUID = toString cfg.power.diskUuid; };
  };

  gpuAllocate = import ./gpu/allocate.nix { inherit pkgs; inherit (cfg.gpu) vms hostpci; };
  # qm and update-initramfs run Debian's own scripts: keep nix's tools off their PATH.
  gpuReprime = script {
    name = "pve-gpu-reprime";
    file = ./gpu/reprime;
    inputs = [ ];
    prelude = "";
  };
  gpuAssign = script {
    name = "pve-gpu-hookscript";
    file = ./gpu/assign;
    inputs = [ ];
    prelude = ''
      HOOKSCRIPT=local:snippets/gpu-allocate.pl
      VMS=(${toString cfg.gpu.vms})
    '';
  };

  modprobeFiles = lib.mapAttrs (name: text: pkgs.writeText "${name}.conf" text) cfg.modprobe;
  modprobeRefresh = script {
    name = "pve-modprobe-refresh";
    file = ./modprobe/refresh;
    strict = true;
    inputs = [ ];
    prelude = "FILES=(${toString (lib.mapAttrsToList (name: f: lib.escapeShellArg "/etc/modprobe.d/${name}.conf=${f}") modprobeFiles)})\n";
  };

  activation = package: extra: lib.recursiveUpdate {
    wantedBy = [ "system-manager.target" ];
    path = [ "/usr" ];
    restartTriggers = [ package ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = lib.getExe package;
    };
  } extra;

  registrar = after: package: {
    wantedBy = [ "multi-user.target" ];
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ] ++ after;
    path = [ "/usr" ];
    restartTriggers = [ package ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = "-${lib.getExe package}";
    };
  };
in
{
  options.dnix.node = {
    ssh = mkOption { type = types.str; };
    sudoPasswordRef = mkOption { type = types.str; };

    area = mkOption { type = types.str; };

    backup = {
      disk = mkOption {
        type = types.nullOr (types.submodule {
          options = {
            uuid = mkOption { type = types.str; };
            mount = mkOption { type = types.str; };
            storage = mkOption { type = types.str; };
          };
        });
        default = null;
      };
      localStorage = mkOption {
        type = types.str;
        default = "local";
      };
      observability = {
        enable = mkEnableOption "the backup sensors in Home Assistant";
        expireAfter = mkOption {
          type = types.ints.positive;
          default = 108000;
        };
      };
      hooks = mkOption {
        type = types.listOf types.package;
        default = [ ];
      };
      offsite = mkOption {
        type = types.attrsOf (types.submodule {
          options = {
            vmid = mkOption { type = types.ints.positive; };
            remote = mkOption { type = types.str; };
            rcloneConfig = mkOption { type = types.str; };
            storage = mkOption {
              type = types.str;
              default = disk.storage;
              defaultText = lib.literalExpression "config.dnix.node.backup.disk.storage";
            };
            weekday = mkOption { type = types.ints.between 1 7; };
          };
        });
        default = { };
      };
    };

    health = {
      enable = mkEnableOption "the NIC hang and heartbeat sensors in Home Assistant";
      nic = mkOption { type = types.str; };
      expireAfter = mkOption {
        type = types.ints.positive;
        default = 1200;
      };
    };

    power = {
      enable = mkEnableOption "powertop autotune and the powersave governor once the guests are up";
      nic = mkOption {
        type = types.nullOr types.str;
        default = null;
      };
      diskUuid = mkOption {
        type = types.nullOr types.str;
        default = null;
      };
    };

    gpu = {
      vms = mkOption {
        type = types.listOf types.ints.positive;
        default = [ ];
      };
      hostpci = mkOption { type = types.str; };
    };

    modprobe = mkOption {
      type = types.attrsOf types.lines;
      default = { };
    };
  };

  config = lib.mkMerge [
    {
      nixpkgs.hostPlatform = "x86_64-linux";
      services.userborn.enable = false;
    }

    (mkIf (disk != null) {
      environment.etc."udev/rules.d/99-pve-backup-disk.rules" = {
        text = ''ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_UUID}=="${disk.uuid}", TAG+="systemd", ENV{SYSTEMD_WANTS}="${diskMount}"'' + "\n";
        mode = "0644";
        replaceExisting = true;
      };
    })

    (mkIf (hooks != [ ]) {
      environment.etc."vzdump-hook".source = lib.getExe dispatcher;
    })

    (mkIf cfg.backup.observability.enable {
      assertions = [{
        assertion = disk != null;
        message = "dnix.node.backup.observability needs dnix.node.backup.disk.";
      }];
      environment.systemPackages = [ obsRegister ];
      systemd.services.pve-backup-obs-register = registrar [ diskMount ] obsRegister;
    })

    (mkIf cfg.health.enable {
      environment.systemPackages = [ healthRegister healthReport ];
      systemd.services.pve-health-register = registrar [ ] healthRegister;
      systemd.services.pve-health-report = {
        wants = [ "network-online.target" ];
        after = [ "network-online.target" ];
        path = [ "/usr" ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = lib.getExe healthReport;
        };
      };
      systemd.timers.pve-health-report = {
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "2min";
          OnUnitActiveSec = "5min";
          AccuracySec = "30s";
          Persistent = false;
        };
      };
    })

    (mkIf cfg.power.enable {
      systemd.services.powertop-autotune = {
        wantedBy = [ "multi-user.target" ];
        after = [ "pve-guests.service" ];
        path = [ "/usr" ];
        restartTriggers = [ powerPin ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = "${pkgs.powertop}/bin/powertop --auto-tune";
          ExecStartPost = [
            "${pkgs.bash}/bin/sh -c 'for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo powersave > \"$g\"; done'"
            (lib.getExe powerPin)
          ];
        };
      };
    })

    (mkIf (cfg.gpu.vms != [ ]) {
      systemd.tmpfiles.settings."10-pve-gpu" = {
        "/var/lib/vz/snippets/gpu-allocate.pl"."L+".argument = "${gpuAllocate}";
        "/var/lib/vz/snippets/gpu-reprime.sh"."L+".argument = lib.getExe gpuReprime;
      };
      systemd.services.pve-gpu-hookscript = activation gpuAssign {
        requires = [ "pve-cluster.service" ];
        after = [ "pve-cluster.service" ];
      };
    })

    (mkIf (cfg.modprobe != { }) {
      environment.etc = lib.mapAttrs' (name: f: lib.nameValuePair "modprobe.d/${name}.conf" {
        source = f;
        mode = "0644";
        replaceExisting = true;
      }) modprobeFiles;
      systemd.services.pve-modprobe-refresh = activation modprobeRefresh {
        serviceConfig.StateDirectory = "pve-modprobe-refresh";
      };
    })
  ];
}
