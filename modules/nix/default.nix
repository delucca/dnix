{ config, lib, ... }:

{
  options.dnix.nix.enable = lib.mkEnableOption "store garbage collection, optimisation and free-space limits";

  config = lib.mkIf config.dnix.nix.enable {
    nix.gc = {
      automatic = lib.mkDefault true;
      options = lib.mkDefault "--delete-older-than 14d";
    };

    # nix-darwin refuses auto-optimise-store: it corrupts the store on macOS.
    nix.optimise.automatic = lib.mkDefault true;

    nix.settings = {
      min-free = lib.mkDefault (10 * 1024 * 1024 * 1024);
      max-free = lib.mkDefault (30 * 1024 * 1024 * 1024);
    };
  };
}
