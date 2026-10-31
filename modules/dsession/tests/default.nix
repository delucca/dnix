{ pkgs }:

{
  dsession = pkgs.runCommand "dsession" { } ''
    ${pkgs.python3}/bin/python3 ${./test_dsession.py} ${../dsession.py} 2>&1 | tee $out
  '';
}
