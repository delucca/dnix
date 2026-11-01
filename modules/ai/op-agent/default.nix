{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.ai.opAgent;
in
{
  options.dnix.ai.opAgent = {
    enable = lib.mkEnableOption "op-agent, a 1Password CLI wrapper that runs as a read-only service account";
    tokenFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/run/user/1000/secrets/op_agent_token";
      description = "A file holding the service account token, read at each call. A string, so the token never enters the store.";
    };
    vault = lib.mkOption {
      type = lib.types.str;
      default = "Agents";
      description = "The one vault the service account can read, named in the SECRETS instruction.";
    };
  };

  config = lib.mkIf (config.dnix.ai.enable && cfg.enable) {
    assertions = [{
      assertion = cfg.tokenFile != null;
      message = "dnix.ai.opAgent: enable needs tokenFile.";
    }];

    home.packages = [
      (pkgs.writeShellScriptBin "op-agent" ''
        OP_SERVICE_ACCOUNT_TOKEN="$(cat ${lib.escapeShellArg cfg.tokenFile})" exec ${pkgs._1password-cli}/bin/op "$@"
      '')
    ];

    dnix.ai.instructions.secrets = {
      order = 95;
      text = builtins.replaceStrings [ "@vault@" ] [ cfg.vault ] (builtins.readFile ./secrets.md);
    };
  };
}
