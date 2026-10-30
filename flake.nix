{
  description = "Daniel's shared nix modules";

  outputs = { self }: {
    homeManagerModules = {
      developer = ./modules/developer;
    };
    darwinModules = {
      nix = ./modules/nix;
    };
    nixosModules = { };
  };
}
