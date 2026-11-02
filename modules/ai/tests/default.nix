{ pkgs }:

let
  shared = ../harnesses/shared;
  agentMd = import ../harnesses/antigravity/agent-md.nix { inherit pkgs; };
  agentToml = import ../harnesses/codex/agent-toml.nix { inherit pkgs; };
  yaml = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
  craft = test: pkgs.runCommand "ai-${test}" { } ''
    ${pkgs.python3}/bin/python3 ${shared}/skills/use-${test}/tests/test_${test}.py ${shared} 2>&1 | tee $out
  '';
in
{
  ai-dsession = pkgs.runCommand "ai-dsession" { } ''
    ${pkgs.python3}/bin/python3 ${../dsession/tests/test_dsession.py} ${../dsession/dsession.py} 2>&1 | tee $out
  '';

  ai-codex-skill-budget = pkgs.runCommand "ai-codex-skill-budget" { } ''
    ${pkgs.python3}/bin/python3 ${../harnesses/codex/tests/codex-skill-budget.py} shared ${shared}/skills/* | tee $out
  '';

  ai-pinned-versions = pkgs.runCommand "ai-pinned-versions" { nativeBuildInputs = [ pkgs.jq ]; } ''
    sh ${shared}/hooks/tests/pinned-versions-test.sh ${shared}/hooks/check-pinned-versions.sh 2>&1 | tee $out
  '';

  ai-antigravity-agents = pkgs.runCommand "ai-antigravity-agents" { nativeBuildInputs = [ yaml ]; } ''
    mkdir rendered
    ${agentMd}/bin/agy-agent-md rendered ${shared}/agents/*.md
    python ${../harnesses/antigravity/tests/antigravity-agents.py} rendered 2>&1 | tee $out
  '';

  ai-antigravity-agent-md = pkgs.runCommand "ai-antigravity-agent-md" { } ''
    ${yaml}/bin/python3 ${../harnesses/antigravity/tests/test_agent_md.py} ${agentMd}/bin/agy-agent-md 2>&1 | tee $out
  '';

  ai-codex-agent-toml = pkgs.runCommand "ai-codex-agent-toml" { } ''
    ${pkgs.python3}/bin/python3 ${../harnesses/codex/tests/test_agent_toml.py} ${agentToml}/bin/codex-agent-toml 2>&1 | tee $out
  '';

  ai-review-diff-metrics =
    let diffMetrics = pkgs.callPackage "${shared}/skills/review/diff-metrics.nix" { };
    in pkgs.runCommand "ai-review-diff-metrics" { nativeBuildInputs = [ pkgs.git ]; } ''
      ${pkgs.python3}/bin/python3 ${shared}/skills/review/tests/test_diff_metrics.py ${diffMetrics}/bin/diff-metrics ${shared}/skills/review/scripts/diff_metrics.py ${pkgs.python3}/bin/python3 2>&1 | tee $out
    '';

  ai-review-cross-audit = pkgs.runCommand "ai-review-cross-audit" { nativeBuildInputs = [ pkgs.git ]; } ''
    ${pkgs.python3}/bin/python3 ${shared}/skills/review/tests/test_cross_audit.py ${shared}/skills/review/scripts 2>&1 | tee $out
  '';

  ai-credential = pkgs.runCommand "ai-credential" { } ''
    ${pkgs.python3}/bin/python3 ${shared}/lib/tests/test_credential.py ${shared}/lib 2>&1 | tee $out
  '';

  ai-vectorcraft = craft "vectorcraft";
  ai-figcraft = craft "figcraft";
  ai-glyphs = craft "glyphs";
}
