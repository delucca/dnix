{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.dsession;
in
{
  options.dnix.dsession = {
    enable = lib.mkEnableOption "the dsession launcher";
    wrappers = lib.mkOption {
      type = lib.types.listOf (lib.types.listOf lib.types.str);
      default = [ ];
    };
    script = lib.mkOption {
      type = lib.types.package;
      readOnly = true;
      default = pkgs.runCommand "dsession-script" { } ''
        { echo '#!/usr/bin/env python3'; cat ${./dsession.py}; } > $out
        chmod +x $out
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ (pkgs.writers.writePython3Bin "dsession" { flakeIgnore = [ "E501" ]; } (builtins.readFile ./dsession.py)) ];
    xdg.configFile."dsession/config.json" = lib.mkIf (cfg.wrappers != [ ]) {
      text = builtins.toJSON { inherit (cfg) wrappers; };
    };
  };
}
