{ lib, ... }:

{
  imports = [ ./mac-apps.nix ./home-folders.nix ./chrome.nix ];

  options.dnix.desktop.enable = lib.mkEnableOption "a machine with a screen";
}
