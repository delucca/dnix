{ config, lib, pkgs, ... }:

let
  homeDir = config.home.homeDirectory;
  label = "com.chrome-devtools.browser";
  port = "9222";
  profile = "${homeDir}/.chrome-debug-profile";
  chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

  chromeUp = pkgs.writeShellApplication {
    name = "chrome_up";
    text = ''
      ready() { curl -sf --max-time 1 "http://127.0.0.1:${port}/json/version" >/dev/null 2>&1; }

      if ! ready; then
        launchctl kickstart "gui/$(id -u)/${label}"
        for _ in $(seq 30); do
          ready && break
          sleep 0.3
        done
        ready || { echo "chrome_up: Chrome did not come up on port ${port}" >&2; exit 1; }
      fi

      if [ -n "''${1:-}" ]; then
        "${chrome}" --user-data-dir="${profile}" --new-window "$1" >/dev/null 2>&1 &
      fi
      osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true
    '';
  };

  chromeDown = pkgs.writeShellApplication {
    name = "chrome_down";
    text = ''
      launchctl kill TERM "gui/$(id -u)/${label}" 2>/dev/null || true
      pkill -f "user-data-dir=${profile}" 2>/dev/null || true
      for _ in $(seq 30); do
        pgrep -f "user-data-dir=${profile}" >/dev/null 2>&1 || { echo "chrome_down: stopped"; exit 0; }
        sleep 0.3
      done
      echo "chrome_down: Chrome is still running" >&2
      exit 1
    '';
  };
in
{
  config = lib.mkIf (config.dnix.desktop.enable && pkgs.stdenv.hostPlatform.isDarwin) {
    home.packages = [ chromeUp chromeDown ];

    home.activation.chromeLogDir =
      lib.hm.dag.entryBetween [ "setupLaunchAgents" ] [ "writeBoundary" ] ''
        run mkdir -p "${homeDir}/.local/log"
      '';

    launchd.agents.chrome-devtools = {
      enable = true;
      config = {
        Label = label;
        ProgramArguments = [
          chrome
          "--remote-debugging-port=${port}"
          "--user-data-dir=${profile}"
          "--password-store=basic"
          "--no-first-run"
          "--no-default-browser-check"
        ];
        EnvironmentVariables.PATH =
          "${homeDir}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin";
        StandardOutPath = "${homeDir}/.local/log/chrome-devtools-browser.log";
        StandardErrorPath = "${homeDir}/.local/log/chrome-devtools-browser.log";
      };
    };
  };
}
