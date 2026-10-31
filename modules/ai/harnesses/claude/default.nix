# ~/.claude/settings.json belongs to the CLI: it writes runtime state there and
# deletes the file when a write fails, which a read-only store link provokes
# (home-manager issue 9831). So policy goes to the managed file, which
# darwinModules.ai installs from dnix.ai.claude.settings.
{ config, lib, pkgs, ... }:

let
  ai = config.dnix.ai;
  cfg = ai.claude;
  jsonFormat = pkgs.formats.json { };
  hook = command: { hooks = [{ type = "command"; inherit command; }]; };
in
{
  options.dnix.ai.claude = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Install the skills, agents and instructions for Claude Code.";
    };

    settings = lib.mkOption {
      inherit (jsonFormat) type;
      default = { };
      description = "managed-settings.json; lists from several definitions are concatenated.";
    };

    managedSettings = lib.mkOption {
      type = lib.types.package;
      readOnly = true;
      description = "A directory holding the rendered managed-settings.json.";
    };
  };

  config = lib.mkIf (ai.enable && cfg.enable) {
    dnix.ai.claude.settings = {
      managedSourcesBehavior = "merge";
      preferredNotifChannel = "notifications_disabled";
      env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = "1";
      hooks.PreToolUse = [
        ((hook "~/.config/ai/common/hooks/check-pinned-versions.sh") // { matcher = "Edit|Write"; })
      ];
    } // lib.optionalAttrs ai.skipPermissions.enable {
      permissions.defaultMode = "bypassPermissions";
      skipDangerousModePermissionPrompt = true;
    };

    # Its own directory: Claude Code watches the settings file's parent, and a
    # bare store file would have it watch /nix/store.
    dnix.ai.claude.managedSettings = pkgs.runCommand "claude-managed-settings" { } ''
      install -Dm444 ${jsonFormat.generate "managed-settings.json" cfg.settings} $out/managed-settings.json
    '';

    home.file = {
      ".claude/CLAUDE.md".text = ai.instructionsText;
    }
    // lib.mapAttrs' (name: src: lib.nameValuePair ".claude/skills/${name}" { source = src; }) ai.resolved.skills
    // lib.mapAttrs' (name: src: lib.nameValuePair ".claude/agents/${name}.md" { source = src; }) ai.resolved.agents;

    # ~/.claude.json has no declarative layer; this keeps its mcpServers empty.
    home.activation.claudeJsonNoMcp = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if [ -f "$HOME/.claude.json" ] && [ "$(${pkgs.jq}/bin/jq -r '.mcpServers // {} | length' "$HOME/.claude.json" 2>/dev/null)" != "0" ]; then
        if ${pkgs.jq}/bin/jq '.mcpServers = {}' "$HOME/.claude.json" > "$HOME/.claude.json.tmp"; then
          run mv "$HOME/.claude.json.tmp" "$HOME/.claude.json"
        else
          rm -f "$HOME/.claude.json.tmp"
          warnEcho "claude: could not strip mcpServers from ~/.claude.json"
        fi
      fi
    '';
  };
}
