{ pkgs }:

{
  dsession = pkgs.runCommand "ai-dsession" { } ''
    ${pkgs.python3}/bin/python3 ${../dsession/tests/test_dsession.py} ${../dsession/dsession.py} 2>&1 | tee $out
  '';
}
