{ stdenvNoCC, fetchurl, nodejs, makeWrapper }:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "chrome-devtools-mcp";
  version = "1.2.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/chrome-devtools-mcp/-/chrome-devtools-mcp-${finalAttrs.version}.tgz";
    hash = "sha256-r2qGlCRLSzDbSAM8sOClDBO7cIZkSEcJn571zHYgigU=";
  };

  nativeBuildInputs = [ makeWrapper ];

  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out/lib/node_modules/chrome-devtools-mcp $out/bin
    cp -r build package.json $out/lib/node_modules/chrome-devtools-mcp/
    makeWrapper ${nodejs}/bin/node $out/bin/chrome-devtools-mcp \
      --add-flags $out/lib/node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js
    runHook postInstall
  '';
})
