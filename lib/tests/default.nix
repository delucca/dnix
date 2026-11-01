{ pkgs }:

{
  create-vm = pkgs.runCommand "create-vm"
    { nativeBuildInputs = [ pkgs.gnugrep pkgs.coreutils ]; }
    "${pkgs.bash}/bin/bash ${./create-vm.sh} ${../create-vm.sh} | tee $out";

  push-secrets = pkgs.runCommand "push-secrets"
    { nativeBuildInputs = [ pkgs.gnugrep pkgs.gnused pkgs.coreutils pkgs.findutils pkgs.jq ]; }
    "${pkgs.bash}/bin/bash ${./push-secrets.sh} ${../push-secrets.sh} | tee $out";
}
