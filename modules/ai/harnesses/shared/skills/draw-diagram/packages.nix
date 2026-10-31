# mermaid-cli renders through a headless Chrome; on darwin that is the
# Google Chrome cask, so the wrapper pins puppeteer to it.
{ pkgs }:

let
  chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  mmdc = pkgs.runCommand "mermaid-cli-${pkgs.mermaid-cli.version}" { nativeBuildInputs = [ pkgs.makeWrapper ]; } ''
    makeWrapper ${pkgs.mermaid-cli}/bin/mmdc $out/bin/mmdc --set-default PUPPETEER_EXECUTABLE_PATH "${chrome}"
  '';
in
[ (if pkgs.stdenv.hostPlatform.isDarwin then mmdc else pkgs.mermaid-cli) ]
