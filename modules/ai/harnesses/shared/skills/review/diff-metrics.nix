{ lib, runCommand, makeWrapper, python3, scc }:

let
  py = python3.withPackages (ps: [ ps.lizard ]);
in
runCommand "diff-metrics" { nativeBuildInputs = [ makeWrapper ]; } ''
  install -Dm644 ${./scripts/diff_metrics.py} $out/libexec/diff-metrics/diff_metrics.py
  install -Dm644 ${./scripts/cross_audit.py} $out/libexec/diff-metrics/cross_audit.py
  makeWrapper ${py}/bin/python3 $out/bin/diff-metrics \
    --add-flags "-I $out/libexec/diff-metrics/diff_metrics.py" \
    --prefix PATH : ${lib.makeBinPath [ scc ]}
  makeWrapper ${python3}/bin/python3 $out/bin/cross-audit \
    --add-flags "-I $out/libexec/diff-metrics/cross_audit.py"
''
