{
  description = "Daniel's shared nix modules";

  outputs = { self }: {
    homeManagerModules = {
      desktop = ./modules/desktop;
      developer = ./modules/developer;
      notebooks = ./modules/notebooks;
      shell = ./modules/shell;
      ssh = ./modules/ssh;
    };
    darwinModules = {
      nix = ./modules/nix;
    };
    nixosModules = { };
  };
}
