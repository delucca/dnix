{
  description = "Daniel's shared nix modules";

  outputs = { self }: {
    homeManagerModules = {
      developer = ./modules/developer;
      ssh = ./modules/ssh;
    };
    darwinModules = {
      nix = ./modules/nix;
    };
    nixosModules = { };
  };
}
