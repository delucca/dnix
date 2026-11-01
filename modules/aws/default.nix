{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.aws;
  helper = pkgs.writeShellApplication {
    name = "aws-credentials-op";
    runtimeInputs = [ pkgs.jq ];
    text = "op=${lib.escapeShellArg "${cfg.op.package}/bin/op"}\n" + builtins.readFile ./credentials-op.sh;
  };
  # The SDKs split credential_process with shlex or run it under sh, so shell quoting suits both.
  process = p:
    if p.op != null then
      lib.escapeShellArgs [ (lib.getExe helper) p.op.vault p.op.item p.op.fields.accessKeyId p.op.fields.secretAccessKey ]
    else
      p.credentialProcess;
  section = name: p:
    lib.nameValuePair (if name == "default" then name else "profile ${name}") (
      { inherit (p) region output; }
      // lib.optionalAttrs (process p != null) { credential_process = process p; }
      // p.settings
    );
in
{
  options.dnix.aws = {
    enable = lib.mkEnableOption "AWS CLI profiles in ~/.aws/config";
    op.package = lib.mkPackageOption pkgs "_1password-cli" { };
    profiles = lib.mkOption {
      default = { };
      type = lib.types.attrsOf (lib.types.submodule {
        options = {
          region = lib.mkOption { type = lib.types.str; };
          output = lib.mkOption {
            type = lib.types.str;
            default = "json";
          };
          credentialProcess = lib.mkOption {
            type = lib.types.nullOr lib.types.str;
            default = null;
          };
          op = lib.mkOption {
            default = null;
            type = lib.types.nullOr (lib.types.submodule {
              options = {
                vault = lib.mkOption { type = lib.types.str; };
                item = lib.mkOption { type = lib.types.str; };
                fields.accessKeyId = lib.mkOption {
                  type = lib.types.str;
                  default = "access key";
                };
                fields.secretAccessKey = lib.mkOption {
                  type = lib.types.str;
                  default = "secret access key";
                };
              };
            });
          };
          settings = lib.mkOption {
            type = lib.types.attrsOf (lib.types.oneOf [ lib.types.str lib.types.int lib.types.bool ]);
            default = { };
          };
        };
      });
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = lib.mapAttrsToList (name: p: {
      assertion = p.op == null || p.credentialProcess == null;
      message = "dnix.aws.profiles.${name}: set op or credentialProcess, not both.";
    }) cfg.profiles;

    programs.awscli = {
      enable = true;
      settings = lib.mapAttrs' section cfg.profiles;
    };
  };
}
