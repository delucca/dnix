{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.ai.opAgent;
  op = "${pkgs._1password-cli}/bin/op";
  security = "/usr/bin/security";
  kc = cfg.keychain;

  readToken =
    if kc != null
    then "${security} find-generic-password -s ${lib.escapeShellArg kc.service} -w 2>/dev/null || true"
    else "cat ${lib.escapeShellArg cfg.tokenFile} 2>/dev/null || true";
  source = if kc != null then "the ${kc.service} keychain item" else cfg.tokenFile;
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
    keychain = lib.mkOption {
      default = null;
      description = "Keep the token in the macOS login keychain instead of a file. Activation fills the item from `ref` with a prompted `op read` when it is missing.";
      type = lib.types.nullOr (lib.types.submodule {
        options = {
          service = lib.mkOption {
            type = lib.types.str;
            default = "op-agent";
          };
          ref = lib.mkOption {
            type = lib.types.str;
            example = "op://Private/op-agent/credential";
          };
        };
      });
    };
    vault = lib.mkOption {
      type = lib.types.str;
      default = "Agents";
      description = "The one vault the service account can read, named in the SECRETS instruction.";
    };
  };

  config = lib.mkIf (config.dnix.ai.enable && cfg.enable) (lib.mkMerge [
    {
      assertions = [
        {
          assertion = (cfg.tokenFile != null) != (kc != null);
          message = "dnix.ai.opAgent: set exactly one of tokenFile or keychain.";
        }
        {
          assertion = kc == null || pkgs.stdenv.hostPlatform.isDarwin;
          message = "dnix.ai.opAgent.keychain is macOS only.";
        }
      ];

      # An empty token would make op fall back to the desktop app and prompt.
      home.packages = [
        (pkgs.writeShellScriptBin "op-agent" ''
          token=$(${readToken})
          if [ -z "$token" ]; then
            echo "op-agent: no service account token in ${source}" >&2
            exit 1
          fi
          OP_SERVICE_ACCOUNT_TOKEN="$token" exec ${op} "$@"
        '')
      ];

      dnix.ai.instructions.secrets = {
        order = 95;
        text = builtins.replaceStrings [ "@vault@" ] [ cfg.vault ] (builtins.readFile ./secrets.md);
      };
    }

    (lib.mkIf (kc != null) {
      # `security add-generic-password -w` from stdin truncates to 128 characters;
      # its interactive mode keeps the whole token and off argv.
      home.activation.opAgentToken = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
        if ! ${security} find-generic-password -s ${lib.escapeShellArg kc.service} >/dev/null 2>&1; then
          echo "op-agent: filling the ${kc.service} keychain item from ${kc.ref}"
          if token=$(${op} read ${lib.escapeShellArg kc.ref}) && [ -n "$token" ]; then
            if [ -z "''${DRY_RUN:-}" ]; then
              printf 'add-generic-password -U -a "%s" -s "%s" -w "%s"\n' "$(id -un)" ${lib.escapeShellArg kc.service} "$token" | ${security} -i || true
              stored=$(${security} find-generic-password -s ${lib.escapeShellArg kc.service} -w 2>/dev/null || true)
              [ "''${#stored}" = "''${#token}" ] || echo "op-agent: the keychain item does not match ${kc.ref}; delete it and switch again" >&2
              unset stored
            fi
          else
            echo "op-agent: could not read ${kc.ref}; unlock 1Password and switch again" >&2
          fi
          unset token
        fi
      '';
    })
  ]);
}
