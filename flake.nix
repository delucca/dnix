{
  description = "Daniel's shared nix modules";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";

  outputs = { self, nixpkgs }: {
    homeManagerModules = {
      desktop = ./modules/desktop;
      developer = ./modules/developer;
      dsession = ./modules/dsession;
      notebooks = ./modules/notebooks;
      shell = ./modules/shell;
      ssh = ./modules/ssh;
    };
    darwinModules = {
      nix = ./modules/nix;
    };
    nixosModules = { };
    checks.aarch64-darwin = import ./modules/dsession/tests { pkgs = nixpkgs.legacyPackages.aarch64-darwin; };
  };
}
