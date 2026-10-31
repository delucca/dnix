{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.desktop;
  home = config.home.homeDirectory;
  logFile = "${home}/.local/log/siri-shortcut-guard.log";

  guard = pkgs.writeShellScript "siri-shortcut-guard" ''
    set -u

    domain=com.apple.Siri
    key=KeyboardShortcutSAE
    mode=''${1:-watch}

    note() { printf '%(%F %T)T %s: %s\n' -1 "$mode" "$1"; }

    current=$(defaults read "$domain" "$key" 2>/dev/null) || current=""

    if [ -z "$current" ]; then
      note "no $key on $domain -- nothing to reassert"
      exit 0
    fi

    case "$current" in
      *"enabled = 0;"*)
        if [ "$mode" != login ]; then
          note "already disabled -- skipping"
          exit 0
        fi
        note "already disabled -- reasserting, a macOS update leaves the daemons holding a Cmd listener with nothing on disk"
        ;;
      *)
        note "enabled flag is set -- disabling, keeping the stored value"
        ;;
    esac

    defaults write "$domain" "$key" \
      "$(printf '%s\n' "$current" | sed 's/enabled = [^;]*;/enabled = 0;/')"

    if [ "$mode" = login ]; then
      sleep 45
    fi

    killall assistantd Siri SiriNCService siriactionsd 2>/dev/null || true
    note "restarted the assistant daemons"
  '';

  agent = mode: extra: {
    enable = true;
    config = {
      ProgramArguments = [ "${guard}" mode ];
      EnvironmentVariables.PATH = "/usr/bin:/bin";
      StandardOutPath = logFile;
      StandardErrorPath = logFile;
    } // extra;
  };
in
{
  options.dnix.desktop.disableSiriShortcut =
    lib.mkEnableOption "keeping the Ask Siri keyboard shortcut off, for hyper keys that toggle Cmd";

  config = lib.mkIf (cfg.enable && cfg.disableSiriShortcut && pkgs.stdenv.hostPlatform.isDarwin) {
    home.activation.siriShortcutGuardLogDir =
      lib.hm.dag.entryBetween [ "setupLaunchAgents" ] [ "writeBoundary" ] ''
        run mkdir -p "${home}/.local/log"
      '';

    launchd.agents.siri-shortcut-guard = agent "watch" {
      WatchPaths = [ "${home}/Library/Preferences/com.apple.Siri.plist" ];
      StartInterval = 1800;
      RunAtLoad = false;
    };

    launchd.agents.siri-shortcut-guard-login = agent "login" {
      RunAtLoad = true;
    };
  };
}
