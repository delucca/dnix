{ config, lib, ... }:

let
  cfg = config.dnix.secrets;
in
{
  options.dnix.secrets = {
    dir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/dnix/secrets";
    };
    files = lib.mkOption {
      default = { };
      type = lib.types.attrsOf (lib.types.submodule ({ name, ... }: {
        options = {
          template = lib.mkOption {
            type = lib.types.str;
            description = "The file's text with references in place of values, rendered by the deploying machine's renderSecret.";
          };
          owner = lib.mkOption {
            type = lib.types.str;
            default = "root";
          };
          group = lib.mkOption {
            type = lib.types.str;
            default = "root";
          };
          mode = lib.mkOption {
            type = lib.types.str;
            default = "0400";
          };
          path = lib.mkOption {
            type = lib.types.str;
            readOnly = true;
            default = "${cfg.dir}/${name}";
          };
        };
      }));
    };
  };

  config.assertions = lib.mapAttrsToList (name: _: {
    assertion = builtins.match "[A-Za-z0-9._-]+" name != null;
    message = "dnix.secrets.files.${name}: a file name holds only letters, digits, dot, dash and underscore.";
  }) cfg.files;
}
