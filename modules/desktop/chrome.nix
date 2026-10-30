{ config, lib, pkgs, ... }:

let
  homeDir = config.home.homeDirectory;
in
{
  config = lib.mkIf (config.dnix.desktop.enable && pkgs.stdenv.hostPlatform.isDarwin) {
    home.activation.chromeLogDir =
      lib.hm.dag.entryBetween [ "setupLaunchAgents" ] [ "writeBoundary" ] ''
        run mkdir -p "${homeDir}/.local/log"
      '';

    launchd.agents.chrome-devtools = {
      enable = true;
      config = {
        Label = "com.chrome-devtools.browser";
        ProgramArguments = [
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
          "--remote-debugging-port=9222"
          "--user-data-dir=${homeDir}/.chrome-debug-profile"
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
