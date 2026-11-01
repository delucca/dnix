{ config, lib, ... }:

{
  config = lib.mkIf (config.dnix.guest.platform == "vm") {
    assertions = [
      {
        assertion = config.dnix.guest.devices == [ ];
        message = "dnix.guest.devices needs dnix.guest.platform = \"lxc\"; a VM guest drops it.";
      }
      {
        assertion = config.dnix.guest.mounts == [ ];
        message = "dnix.guest.mounts needs dnix.guest.platform = \"lxc\"; a VM guest drops it.";
      }
    ];

    boot.loader.systemd-boot.enable = true;
    boot.growPartition = true;
    boot.kernelParams = [ "console=tty0" "console=ttyS0" ];
    boot.initrd.availableKernelModules = [ "virtio_pci" "virtio_scsi" "virtio_blk" "sd_mod" ];

    fileSystems."/" = {
      device = "/dev/disk/by-label/nixos";
      fsType = "ext4";
      autoResize = true;
    };
    fileSystems."/boot" = {
      device = "/dev/disk/by-label/ESP";
      fsType = "vfat";
    };

    services.qemuGuest.enable = true;
  };
}
