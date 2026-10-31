# agy has no managed layer and rewrites its settings.json sparsely, so every
# switch merges dnix.ai.antigravity.settings in rather than owning the file. It
# deletes a key set to its default, so enableTerminalSandbox is never set. agy
# walks rules only up to the repo root, so the Developer tree's AGENTS.md rides
# in the global file.
{ config, lib, pkgs, ... }:

let
  ai = config.dnix.ai;
  cfg = ai.antigravity;
  jsonFormat = pkgs.formats.json { };
  jq = "${pkgs.jq}/bin/jq";
  agentMd = import ./agent-md.nix { inherit pkgs; };
  agents = pkgs.runCommand "agy-agents" { } ''
    mkdir -p $out
    ${agentMd}/bin/agy-agent-md $out ${lib.concatStringsSep " " (lib.attrValues ai.resolved.agentFiles)}
  '';
  settings = jsonFormat.generate "agy-settings.json" cfg.settings;
  empty = pkgs.writeText "empty.json" "{}";
in
{
  options.dnix.ai.antigravity = {
    enable = lib.mkEnableOption "the skills, agents and instructions for Antigravity CLI (agy)";

    settings = lib.mkOption {
      inherit (jsonFormat) type;
      default = { };
      description = "Keys merged into ~/.gemini/antigravity-cli/settings.json on every switch.";
    };

    hooks = lib.mkOption {
      inherit (jsonFormat) type;
      default = { };
      description = "~/.gemini/config/hooks.json, by group name.";
    };
  };

  config = lib.mkIf (ai.enable && cfg.enable) {
    dnix.ai.antigravity.settings = lib.mkIf ai.skipPermissions.enable {
      toolPermission = "always-proceed";
      artifactReviewPolicy = "always-proceed";
      allowNonWorkspaceAccess = true;
    };

    dnix.ai.antigravity.hooks.pinned-versions.PreToolUse = [{
      matcher = "write_to_file|replace_file_content|multi_replace_file_content";
      hooks = [{ command = "~/.config/ai/common/hooks/check-pinned-versions.sh"; timeout = 5; }];
    }];

    # On PATH for dsession, which renders linked directories' agents with it.
    home.packages = [ agentMd ];

    home.file = {
      ".gemini/AGENTS.md".text = ai.instructionsText
        + lib.optionalString config.dnix.developer.enable ("\n" + config.dnix.developer.agentsText);
      ".gemini/config/agents".source = agents;
      ".gemini/config/hooks.json".text = builtins.toJSON cfg.hooks + "\n";
    }
    // lib.mapAttrs' (name: src: lib.nameValuePair ".gemini/config/skills/${name}" { source = src; }) ai.resolved.skills;

    # mcp_config.json is agy's too; the guard keeps its mcpServers empty.
    home.activation.agySettings = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      f="$HOME/.gemini/antigravity-cli/settings.json"
      src="$f"; [ -s "$f" ] || src=${empty}
      tmp="$(mktemp)"
      if ${jq} -s '.[0] * .[1]' "$src" ${settings} > "$tmp"; then
        if ! cmp -s "$tmp" "$f"; then
          run mkdir -p "$(dirname "$f")"
          run mv "$tmp" "$f"
        fi
      else
        warnEcho "agy: could not merge the managed keys into $f"
      fi
      rm -f "$tmp"

      m="$HOME/.gemini/config/mcp_config.json"
      if [ -s "$m" ] && [ "$(${jq} -r '.mcpServers // {} | length' "$m" 2>/dev/null)" != "0" ]; then
        if ${jq} '.mcpServers = {}' "$m" > "$m.tmp"; then
          run mv "$m.tmp" "$m"
        else
          rm -f "$m.tmp"
          warnEcho "agy: could not strip mcpServers from $m"
        fi
      fi
    '';
  };
}
