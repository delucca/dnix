{ config, lib, ... }:

let
  cfg = config.dnix.notebooks;
  relRoot = lib.removePrefix (config.home.homeDirectory + "/") cfg.root;
in
{
  imports = [ ./backup.nix ];

  options.dnix.notebooks = {
    enable = lib.mkEnableOption "the Notebooks tree";
    root = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/Notebooks";
    };
    scopes = lib.mkOption {
      type = lib.types.listOf (lib.types.strMatching "[a-z]+");
      default = [ "personal" ];
    };
  };

  config = lib.mkIf cfg.enable {
    home.file = {
      "${relRoot}/AGENTS.md".source = ./AGENTS.md;
      "${relRoot}/CLAUDE.md".source = config.lib.file.mkOutOfStoreSymlink "${cfg.root}/AGENTS.md";
    };
  };
}
