{ config, lib, pkgs, ... }:

{
  config = lib.mkIf config.dnix.desktop.enable {
    dnix.macApps.apps = lib.optionals pkgs.stdenv.hostPlatform.isDarwin [ pkgs.ghostty-bin ];
    xdg.configFile."ghostty/config".source = ./config;
  };
}
