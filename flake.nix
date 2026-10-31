{
  description = "Daniel's shared nix modules";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";

  outputs = { self, nixpkgs }: {
    homeManagerModules = {
      ai = ./modules/ai;
      desktop = ./modules/desktop;
      developer = ./modules/developer;
      notebooks = ./modules/notebooks;
      shell = ./modules/shell;
      ssh = ./modules/ssh;
    };
    darwinModules = {
      ai = ./modules/ai/darwin.nix;
      nix = ./modules/nix;
    };
    nixosModules = { };
    checks.aarch64-darwin = nixpkgs.lib.mapAttrs' (name: nixpkgs.lib.nameValuePair "ai-${name}") (import ./modules/ai/tests { pkgs = nixpkgs.legacyPackages.aarch64-darwin; });
  };
}
