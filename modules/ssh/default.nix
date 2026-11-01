{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.ssh;
  helper = pkgs.writeShellScriptBin "ssh-fallback-helper" (builtins.readFile ./fallback-helper.sh);
  fqdn = host: "${host}.${cfg.tailnet}";
  mux = {
    ControlMaster = "auto";
    ControlPath = "~/.ssh/sockets/%r@%n-%p";
    ControlPersist = "1h";
    TCPKeepAlive = "no";
    ServerAliveInterval = 30;
    ServerAliveCountMax = 120;
    Compression = "yes";
  };
  homeHost = name: h: {
    HostName = "localhost";
    User = h.user;
    ProxyCommand = "${helper}/bin/ssh-fallback-helper ${fqdn h.tailscale} ${h.lan} 22";
    HostKeyAlias = name;
    StrictHostKeyChecking = "accept-new";
    ExitOnForwardFailure = "yes";
  } // lib.optionalAttrs h.forwardAgent { ForwardAgent = "yes"; }
    // lib.optionalAttrs (h.forwards != [ ]) { LocalForward = h.forwards; }
    // lib.optionalAttrs h.mux mux;
  guestRoute = g: user: {
    HostName = fqdn g.tailscale;
    User = user;
    IdentityFile = cfg.identityFile;
    StrictHostKeyChecking = "accept-new";
  };
in
{
  options.dnix.ssh = {
    enable = lib.mkEnableOption "the ssh config";
    tailnet = lib.mkOption { type = lib.types.str; };
    identityFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
    };
    agentSocket = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
    };
    githubOver443 = lib.mkEnableOption "GitHub through ssh.github.com:443";
    hosts = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule {
        options = {
          tailscale = lib.mkOption { type = lib.types.str; };
          lan = lib.mkOption { type = lib.types.str; };
          user = lib.mkOption { type = lib.types.str; };
          mux = lib.mkOption {
            type = lib.types.bool;
            default = true;
          };
          forwardAgent = lib.mkOption {
            type = lib.types.bool;
            default = false;
          };
          forwards = lib.mkOption {
            type = lib.types.listOf lib.types.str;
            default = [ ];
          };
        };
      });
      default = { };
    };
    guests = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule {
        options = {
          tailscale = lib.mkOption { type = lib.types.str; };
          service = lib.mkOption { type = lib.types.str; };
          admin = lib.mkOption { type = lib.types.str; };
        };
      });
      default = { };
    };
  };

  config = lib.mkIf cfg.enable {
    programs.ssh = {
      enable = true;
      enableDefaultConfig = false;
      includes = [ "config.d/*" ];
      settings = {
        "*" = { AddKeysToAgent = "yes"; }
          // lib.optionalAttrs (cfg.agentSocket != null) { IdentityAgent = ''"${cfg.agentSocket}"''; };
      } // lib.optionalAttrs cfg.githubOver443 {
        "github.com" = {
          HostName = "ssh.github.com";
          Port = 443;
          User = "git";
        };
      } // lib.mapAttrs homeHost cfg.hosts
        // lib.optionalAttrs (cfg.identityFile != null) (lib.concatMapAttrs (name: g: {
          ${name} = guestRoute g g.service;
          "${name}-admin" = guestRoute g g.admin;
        }) cfg.guests);
    };

    home.sessionVariables = lib.mkIf (cfg.agentSocket != null) { SSH_AUTH_SOCK = cfg.agentSocket; };

    home.activation.sshSocketsDir = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      run mkdir -p "$HOME/.ssh/sockets"
      run chmod 700 "$HOME/.ssh" "$HOME/.ssh/sockets"
    '';
  };
}
