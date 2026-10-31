{ lib, ... }:

{
  imports = [ ./dsession ];

  options.dnix.ai.enable = lib.mkEnableOption "the agent stack";
}
