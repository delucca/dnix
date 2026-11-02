{ pkgs }:

pkgs.writers.writePython3Bin "codex-agent-toml"
  {
    libraries = [ pkgs.python3Packages.pyyaml pkgs.python3Packages.tomli-w ];
    flakeIgnore = [ "E501" ];
  }
  (builtins.readFile ./agent-toml.py)
