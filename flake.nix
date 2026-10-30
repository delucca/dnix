{
  description = "Daniel's shared nix modules";

  outputs = { self }: {
    homeManagerModules = { };
    darwinModules = {
      nix = ./modules/nix;
    };
    nixosModules = { };
  };
}
