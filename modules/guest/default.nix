{ config, lib, modulesPath, ... }:

let
  cfg = config.dnix.guest;
in
{
  imports = [ "${modulesPath}/virtualisation/proxmox-lxc.nix" ];

  options.dnix.guest = {
    node = lib.mkOption { type = lib.types.str; };
    vmid = lib.mkOption { type = lib.types.int; };
    cores = lib.mkOption {
      type = lib.types.int;
      default = 1;
    };
    memory = lib.mkOption {
      type = lib.types.int;
      default = 1024;
    };
    swap = lib.mkOption {
      type = lib.types.int;
      default = 512;
    };
    rootfs = lib.mkOption {
      type = lib.types.str;
      default = "local-lvm:8";
    };
    mounts = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
    };
    devices = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
    };
    hwaddr = lib.mkOption { type = lib.types.str; };
    description = lib.mkOption {
      type = lib.types.str;
      default = "";
    };
    adminUser = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
    };
    authorizedKeyFiles = lib.mkOption {
      type = lib.types.listOf lib.types.path;
      default = [ ];
    };
  };

  config = {
    nixpkgs.hostPlatform = "x86_64-linux";
    nix.settings = {
      experimental-features = [ "nix-command" "flakes" ];
      min-free = lib.mkDefault (1024 * 1024 * 1024);
      max-free = lib.mkDefault (3 * 1024 * 1024 * 1024);
    };
    nix.gc = {
      automatic = true;
      dates = lib.mkDefault "weekly";
      options = lib.mkDefault "--delete-older-than 14d";
    };

    services.openssh = {
      enable = true;
      settings.PasswordAuthentication = false;
    };

    users.users = {
      root.openssh.authorizedKeys.keyFiles = cfg.authorizedKeyFiles;
    } // lib.optionalAttrs (cfg.adminUser != null) {
      ${cfg.adminUser} = {
        isNormalUser = true;
        extraGroups = [ "wheel" ];
        openssh.authorizedKeys.keyFiles = cfg.authorizedKeyFiles;
      };
    };
    security.sudo.wheelNeedsPassword = false;

    proxmoxLXC = {
      enable = true;
      manageHostName = true;
    };
    networking.interfaces.eth0.useDHCP = true;
    # The IPv6 router advertisement lands first, and network-online would
    # otherwise fire before the DHCPv4 lease that carries the route out.
    systemd.network.networks."40-eth0".linkConfig.RequiredFamilyForOnline = "ipv4";

    system.stateVersion = "26.05";
  };
}
