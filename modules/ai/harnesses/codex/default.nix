# ~/.codex/config.toml belongs to Codex (project and hook trust live there),
# so policy goes to /etc/codex/managed_config.toml, which darwinModules.ai
# installs from dnix.ai.codex.settings. Codex ignores an invalid managed value
# without a word and falls back to prompts: run `codex doctor` after a change.
{ config, lib, pkgs, ... }:

let
  ai = config.dnix.ai;
  cfg = ai.codex;
  tomlFormat = pkgs.formats.toml { };
  jsonFormat = pkgs.formats.json { };

  # Charged to the same skill budget as the farm, and covered by it.
  disabledPlugins = [
    "documents@openai-primary-runtime"
    "pdf@openai-primary-runtime"
    "presentations@openai-primary-runtime"
    "spreadsheets@openai-primary-runtime"
    "template-creator@openai-primary-runtime"
    "visualize@openai-bundled"
  ];

  py = pkgs.python3.withPackages (ps: [ ps.pyyaml ps.tomli-w ]);
  agentsToml = pkgs.runCommand "codex-agents" { nativeBuildInputs = [ py ]; } ''
    mkdir -p $out
    python ${./agent-toml.py} $out ${lib.concatStringsSep " " (lib.attrValues ai.resolved.agentFiles)}
  '';

  hooksFile = ".codex/hooks.json";
  hooks = pkgs.writeText "codex-hooks.json" (builtins.toJSON cfg.hooks + "\n");
in
{
  options.dnix.ai.codex = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Install the skills, agents and instructions for Codex.";
    };

    settings = lib.mkOption {
      inherit (tomlFormat) type;
      default = { };
      description = "/etc/codex/managed_config.toml; tables merge key by key.";
    };

    hooks = lib.mkOption {
      inherit (jsonFormat) type;
      default = { };
      description = "The whole ~/.codex/hooks.json document; not written while empty.";
    };

    managedConfig = lib.mkOption {
      type = lib.types.package;
      readOnly = true;
      description = "The rendered managed_config.toml.";
    };
  };

  config = lib.mkIf (ai.enable && cfg.enable) {
    dnix.ai.codex.settings = {
      plugins = lib.genAttrs disabledPlugins (_: { enabled = false; });
    } // lib.optionalAttrs ai.skipPermissions.enable {
      # approval_policy alone turns every prompt into a silent sandbox failure.
      approval_policy = "never";
      sandbox_mode = "danger-full-access";
    };

    dnix.ai.codex.managedConfig = tomlFormat.generate "codex-managed_config.toml" cfg.settings;

    # ~/.codex/agents used to be one store link; home-manager backs up the
    # files it sees through it instead of replacing it, which fails read-only.
    home.activation.codexAgentsDir = lib.hm.dag.entryBefore [ "checkLinkTargets" ] ''
      if [ -L "$HOME/.codex/agents" ] && [[ "$(readlink "$HOME/.codex/agents")" == /nix/store/* ]]; then
        run rm "$HOME/.codex/agents"
      fi
    '';

    # Copied, not linked: a wrapper may merge its own hooks into this file and
    # write a .bak beside it, which a read-only link refuses. Codex keys hook
    # trust by this path, so it asks again only when the content changes.
    home.activation.codexHooks = lib.mkIf (cfg.hooks != { }) (lib.hm.dag.entryAfter [ "linkGeneration" ] ''
      run rm -f "$HOME/${hooksFile}"
      run install -m 0644 -D ${hooks} "$HOME/${hooksFile}"
    '');

    home.file = {
      ".codex/AGENTS.md".text = ai.instructionsText;
      # Per file, so a plugin's setup can write its own agents beside these.
      ".codex/agents" = { source = agentsToml; recursive = true; };
    }
    // lib.mapAttrs' (name: src: lib.nameValuePair ".codex/skills/${name}" { source = src; }) ai.resolved.skills;
  };
}
