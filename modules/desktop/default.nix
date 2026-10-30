{ lib, ... }:

{
  imports = [ ./mac-apps.nix ./home-folders.nix ./chrome.nix ./ghostty ];

  options.dnix.desktop.enable = lib.mkEnableOption "a machine with a screen";
}
