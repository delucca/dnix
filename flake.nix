{
  description = "Daniel's shared nix modules";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";

  outputs = { self, nixpkgs }: {
    lib = import ./lib;
    homeManagerModules = {
      ai = ./modules/ai;
      aws = ./modules/aws;
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
    nixosModules = {
      guest = ./modules/guest;
      node = ./modules/node;
      observability = ./modules/observability;
    };
    packages.aarch64-darwin.setup-s3 = let pkgs = nixpkgs.legacyPackages.aarch64-darwin; in pkgs.writeShellApplication {
      name = "setup-s3";
      runtimeInputs = [ pkgs.awscli2 pkgs.rclone pkgs.jq ];
      text = builtins.readFile ./modules/node/backup/setup-s3;
    };
    checks.aarch64-darwin = self.lib.testsIn { pkgs = nixpkgs.legacyPackages.aarch64-darwin; dir = ./modules; }
      // nixpkgs.lib.mapAttrs' (name: nixpkgs.lib.nameValuePair "lib-${name}") (import ./lib/tests { pkgs = nixpkgs.legacyPackages.aarch64-darwin; })
      // { observability = import ./modules/observability/test.nix { pkgs = nixpkgs.legacyPackages.aarch64-darwin; }; aws = import ./modules/aws/test.nix { pkgs = nixpkgs.legacyPackages.aarch64-darwin; }; };
  };
}
