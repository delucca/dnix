{ lib, buildNpmPackage, fetchFromGitHub, nodejs, makeWrapper }:

buildNpmPackage (finalAttrs: {
  pname = "brightdata-mcp";
  version = "2.11.0";

  src = fetchFromGitHub {
    owner = "brightdata";
    repo = "brightdata-mcp";
    rev = "adbfdd49b8805136662a264490118c2688da3e29";
    hash = "sha256-HH+AyDbMv6LUsN4y1bdHKf0qDaT8IfU1CQnNhNFR5/A=";
  };

  npmDepsHash = "sha256-TKouy1I6RXWYlE83XUuSJ6eZ8uPEzcfdaCS6K/CvHaI=";

  nativeBuildInputs = [ makeWrapper ];

  dontNpmBuild = true;
  npmFlags = [ "--ignore-scripts" ];
  npmRebuildFlags = [ "--ignore-scripts" ];
  env.PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";

  postInstall = ''
    rm -rf $out/bin
    makeWrapper ${nodejs}/bin/node $out/bin/brightdata-mcp \
      --add-flags $out/lib/node_modules/@brightdata/mcp/server.js
  '';
})
