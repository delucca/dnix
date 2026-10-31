{ pkgs }:

pkgs.writers.writePython3Bin "agy-agent-md"
  {
    libraries = [ pkgs.python3Packages.pyyaml ];
    flakeIgnore = [ "E501" ];
  }
  (builtins.readFile ./agent-md.py)
