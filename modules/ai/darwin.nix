# The policy files outside $HOME, rendered by the home-manager module of the
# primary user: set every dnix.ai option there, never here.
{ config, lib, ... }:

let
  ai = config.home-manager.users.${config.system.primaryUser}.dnix.ai;
  target = "/Library/Application Support/ClaudeCode/managed-settings.json";
in
{
  config = lib.mkIf ai.enable (lib.mkMerge [
    (lib.mkIf ai.claude.enable {
      system.activationScripts.postActivation.text = lib.mkAfter ''
        mkdir -p "${dirOf target}"
        install -m 644 "${ai.claude.managedSettings}/managed-settings.json" "${target}"
      '';
    })
    (lib.mkIf ai.codex.enable {
      environment.etc."codex/managed_config.toml".source = ai.codex.managedConfig;
    })
  ]);
}
