{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.notebooks;
  backup = cfg.backup;
  home = config.home.homeDirectory;
  name = "notebooks-backup";
  logFile = "${home}/.local/log/${name}.log";
  pruneStamp = "${config.xdg.stateHome}/${name}/last-prune";
  find = "${pkgs.findutils}/bin/find";

  credentials = pkgs.writeText "${name}-env" (lib.concatStrings
    (lib.mapAttrsToList (var: cmd: "${var}=\"$(${cmd})\"\n") backup.credentialCommands));

  run = pkgs.writeShellScript name ''
    set -euo pipefail
    printf '%(%F %T)T start\n' -1
    restic-notebooks cat config >/dev/null 2>&1 || restic-notebooks init
    ${find} ${lib.escapeShellArg cfg.root} -name notebook.org -not -path '*/node_modules/*' -print0 \
      | restic-notebooks backup --quiet --skip-if-unchanged --files-from-raw /dev/stdin ${lib.escapeShellArgs backup.extraPaths}
    restic-notebooks forget --quiet --host "$(/bin/hostname -s)" \
      --keep-hourly 48 --keep-daily 30 --keep-monthly 12
    if [ -z "$(${find} ${lib.escapeShellArg pruneStamp} -mmin -1440 2>/dev/null)" ]; then
      restic-notebooks prune --quiet
      mkdir -p ${lib.escapeShellArg (dirOf pruneStamp)}
      touch ${lib.escapeShellArg pruneStamp}
    fi
    printf '%(%F %T)T done\n' -1
  '';
in
{
  options.dnix.notebooks.backup = {
    enable = lib.mkEnableOption "hourly restic snapshots of every notebook.org";
    repository = lib.mkOption {
      type = lib.types.str;
      example = "s3:s3.amazonaws.com/my-bucket/notebooks";
    };
    passwordCommand = lib.mkOption {
      type = lib.types.str;
      example = "cat ~/.config/restic/password";
    };
    credentialCommands = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = { };
      example = { AWS_ACCESS_KEY_ID = "pass show restic/key-id"; AWS_SECRET_ACCESS_KEY = "pass show restic/secret"; };
    };
    extraPaths = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
    };
  };

  config = lib.mkIf (cfg.enable && backup.enable) {
    assertions = [{
      assertion = pkgs.stdenv.hostPlatform.isDarwin;
      message = "dnix.notebooks.backup schedules through launchd, so it needs a darwin host";
    }];

    services.restic = {
      enable = true;
      backups.notebooks = {
        inherit (backup) repository passwordCommand;
        environmentFile = lib.mkIf (backup.credentialCommands != { }) "${credentials}";
      };
    };

    home.activation.notebooksBackupLogDir =
      lib.hm.dag.entryBetween [ "setupLaunchAgents" ] [ "writeBoundary" ] ''
        run mkdir -p "${home}/.local/log"
      '';

    launchd.agents.${name} = {
      enable = true;
      config = {
        ProgramArguments = [ "${run}" ];
        EnvironmentVariables.PATH = "${config.home.profileDirectory}/bin:/usr/bin:/bin";
        StartInterval = 3600;
        RunAtLoad = true;
        StandardOutPath = logFile;
        StandardErrorPath = logFile;
      };
    };
  };
}
