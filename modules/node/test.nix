{ pkgs }:

let
  hook = import ./gpu/allocate.nix {
    inherit pkgs;
    vms = [ 100 101 ];
    hostpci = "0000:01:00,pcie=1,x-vga=1";
  };
in
pkgs.runCommand "node" { nativeBuildInputs = [ pkgs.perl pkgs.gnused pkgs.gnugrep pkgs.coreutils ]; } ''
  ${pkgs.bash}/bin/bash ${./gpu/test.sh} ${hook} | tee $out
''
