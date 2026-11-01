{ pkgs }:

{
  create-vm = pkgs.runCommand "create-vm"
    { nativeBuildInputs = [ pkgs.gnugrep pkgs.coreutils ]; }
    "${pkgs.bash}/bin/bash ${./create-vm.sh} ${../create-vm.sh} | tee $out";
}
