{ lib, ... }:

{
  options.dnix.node = {
    ssh = lib.mkOption { type = lib.types.str; };
    sudoPasswordRef = lib.mkOption { type = lib.types.str; };
  };

  config.nixpkgs.hostPlatform = "x86_64-linux";
  config.services.userborn.enable = false;
  # userborn off would flip sops-nix onto NixOS activation scripts, which
  # system-manager stubs out, so secrets would silently never install
  # (numtide/system-manager#533; #534 pending). This is the only valid
  # value here regardless of userborn.
  config.sops.useSystemdActivation = true;
  # No openssh.hostKeys under system-manager, so sops-nix's default key
  # discovery finds nothing; every node decrypts with its own host key.
  config.sops.age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ];
}
