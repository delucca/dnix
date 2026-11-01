{ config, lib, modulesPath, ... }:

let
  lxc = config.dnix.guest.platform == "lxc";
in
{
  imports = [ "${modulesPath}/virtualisation/proxmox-lxc.nix" ];

  config = lib.mkMerge [
    { proxmoxLXC.enable = lxc; }
    (lib.mkIf lxc {
      assertions = [{
        assertion = config.dnix.guest.extraDisks == [ ];
        message = "dnix.guest.extraDisks needs dnix.guest.platform = \"vm\"; an LXC guest drops it.";
      }];

      proxmoxLXC.manageHostName = true;
      networking.interfaces.eth0.useDHCP = true;
      # The IPv6 router advertisement lands first, and network-online would
      # otherwise fire before the DHCPv4 lease that carries the route out.
      systemd.network.networks."40-eth0".linkConfig.RequiredFamilyForOnline = "ipv4";
    })
  ];
}
