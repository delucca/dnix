{ lib, buildNpmPackage, fetchurl }:

buildNpmPackage (finalAttrs: {
  pname = "pdf-reader-mcp";
  version = "2.1.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/@sylphx/pdf-reader-mcp/-/pdf-reader-mcp-${finalAttrs.version}.tgz";
    hash = "sha256-Mp8yREjsfIdc7uWJlBZ5JpGaJyqCW4t4XjYLvcnbNRU=";
  };

  postPatch = ''
    cp ${./package-lock.json} package-lock.json
  '';

  npmDepsHash = "sha256-aTslO3IWmse5lTln6Wb/cidBgSypXe9ShRlhzRKiFfA=";

  dontNpmBuild = true;
  npmFlags = [ "--ignore-scripts" ];
  npmRebuildFlags = [ "--ignore-scripts" ];
})
