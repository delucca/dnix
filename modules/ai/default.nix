{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.ai;
  json = pkgs.formats.json { };

  # One store copy: skill scripts find ../../lib by resolving their own path,
  # so every skill must sit inside this tree, never in a store path of its own.
  shared = builtins.path { path = ./harnesses/shared; name = "ai-shared"; };
  sharedLink = if cfg.devTree == null then "${shared}" else config.lib.file.mkOutOfStoreSymlink cfg.devTree;

  entries = kind: dir: lib.attrNames (lib.filterAttrs (_: t: t == kind) (builtins.readDir dir));

  entryType = description: lib.types.submodule {
    options = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Whether to install this ${description}.";
      };
      source = lib.mkOption {
        type = lib.types.nullOr (lib.types.either lib.types.path lib.types.str);
        default = null;
        description = "The ${description}'s directory or file. A path outside the store is linked live.";
      };
      settings = lib.mkOption {
        inherit (json) type;
        default = { };
        description = "Rendered to ~/.config/ai/settings/<name>.json for the ${description} to read.";
      };
      packages = lib.mkOption {
        type = lib.types.listOf lib.types.package;
        default = [ ];
        description = "Packages the ${description} needs, installed only while it is enabled.";
      };
    };
  };

  enabled = lib.filterAttrs (_: e: e.enable);
  link = src:
    let s = toString src;
    in if lib.hasPrefix builtins.storeDir s then s else config.lib.file.mkOutOfStoreSymlink s;

  sectionsOf = dir:
    lib.concatMap (f:
      let m = builtins.match "([0-9]+)-([a-z0-9-]+)\\.md" f;
      in lib.optional (m != null) (lib.nameValuePair (builtins.elemAt m 1) {
        order = lib.toInt (builtins.elemAt m 0);
        source = dir + "/${f}";
      }))
    (builtins.attrNames (builtins.readDir dir));

  skillPackages = name:
    let f = ./harnesses/shared/skills + "/${name}/packages.nix";
    in lib.optionals (builtins.pathExists f) (import f { inherit pkgs; });

  secretsFile = name: ./harnesses/shared/skills + "/${name}/secrets.nix";
  readsSecrets = name: builtins.pathExists (secretsFile name);
in
{
  imports = [ ./dsession ./op-agent ./harnesses/claude ./harnesses/codex ./harnesses/antigravity ];

  options.dnix.ai = {
    enable = lib.mkEnableOption "the agent stack";

    skills = lib.mkOption {
      type = lib.types.attrsOf (entryType "skill");
      default = { };
      description = "Skills every enabled harness loads, by name. A consumer adds its own, overrides a shipped one's source, or sets enable = false.";
    };

    agents = lib.mkOption {
      type = lib.types.attrsOf (entryType "agent");
      default = { };
      description = "Agents every enabled harness loads, by name, each a Claude-format markdown file.";
    };

    instructionDirs = lib.mkOption {
      type = lib.types.listOf lib.types.path;
      default = [ ];
      description = "Folders of NN-name.md sections added to the instructions.";
    };

    instructions = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule ({ config, ... }: {
        options = {
          order = lib.mkOption { type = lib.types.int; };
          source = lib.mkOption { type = lib.types.nullOr lib.types.path; default = null; };
          text = lib.mkOption { type = lib.types.str; default = builtins.readFile config.source; };
        };
      }));
      default = { };
      description = "The global instructions every harness loads, concatenated by order.";
    };

    instructionsText = lib.mkOption {
      type = lib.types.str;
      readOnly = true;
      description = "The composed instructions.";
    };

    reviewLenses = lib.mkOption {
      type = lib.types.listOf lib.types.path;
      default = [ ];
      description = "Extra lens briefs for the review skill, linked under ~/.config/ai/review-lenses/.";
    };

    secrets.readCommand = lib.mkOption {
      type = lib.types.nullOr (lib.types.listOf lib.types.str);
      default = if cfg.opAgent.enable then [ "op-agent" "read" ] else null;
      defaultText = lib.literalExpression ''if dnix.ai.opAgent.enable then [ "op-agent" "read" ] else null'';
      example = [ "op" "read" ];
      description = "The command a skill runs, with a secret's reference appended, to read it at use time. A skill that reads secrets needs it set.";
    };

    skipPermissions.enable = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Run every harness without permission prompts or a sandbox.";
    };

    devTree = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/home/me/src/dnix/modules/ai/harnesses/shared";
      description = "A live checkout of harnesses/shared to link the shipped skills and ~/.config/ai/common from. Agents are rendered per harness, so they always come from the store.";
    };

    resolved = lib.mkOption {
      type = lib.types.attrs;
      readOnly = true;
      internal = true;
      description = "The enabled skills and agents, name to link target, as the harnesses install them.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = lib.mapAttrsToList (name: e: {
      assertion = e.source != null;
      message = "dnix.ai: '${name}' has no source; a typo in a skill or agent name?";
    }) (cfg.skills // cfg.agents)
    ++ lib.mapAttrsToList (name: _: {
      assertion = cfg.secrets.readCommand != null;
      message = "dnix.ai: '${name}' reads secrets; set dnix.ai.secrets.readCommand or enable dnix.ai.opAgent.";
    }) (lib.filterAttrs (name: _: readsSecrets name) (enabled cfg.skills));

    dnix.ai.skills = lib.genAttrs (entries "directory" ./harnesses/shared/skills) (name: {
      source = lib.mkDefault (if cfg.devTree == null then "${shared}/skills/${name}" else "${cfg.devTree}/skills/${name}");
      packages = skillPackages name;
    } // lib.optionalAttrs (readsSecrets name) {
      enable = lib.mkDefault false;
      settings.secrets = lib.mapAttrs (_: lib.mkDefault) (import (secretsFile name) { inherit (cfg.opAgent) vault; });
    });

    dnix.ai.agents = lib.listToAttrs (map (f: lib.nameValuePair (lib.removeSuffix ".md" f) {
      source = lib.mkDefault "${shared}/agents/${f}";
    }) (lib.filter (lib.hasSuffix ".md") (entries "regular" ./harnesses/shared/agents)));

    dnix.ai.instructions = lib.listToAttrs (lib.concatMap sectionsOf ([ ./harnesses/shared/instructions ] ++ cfg.instructionDirs));
    dnix.ai.instructionsText = lib.concatMapStrings (s: s.text) (lib.sortOn (s: s.order) (lib.attrValues cfg.instructions));

    dnix.ai.resolved = {
      skills = lib.mapAttrs (_: e: link e.source) (enabled cfg.skills);
      agents = lib.mapAttrs (_: e: link e.source) (enabled cfg.agents);
      agentFiles = lib.mapAttrs (_: e: e.source) (enabled cfg.agents);
    };

    # ~/.config/ai used to be one link into the store; home-manager cannot
    # turn that into the directory below in place.
    home.activation.aiConfigDir = lib.hm.dag.entryBefore [ "checkLinkTargets" ] ''
      if [ -L "$HOME/.config/ai" ]; then
        run rm "$HOME/.config/ai"
      fi
    '';

    home.file = {
      ".config/ai/common".source = sharedLink;
    }
    // lib.mapAttrs' (name: e: lib.nameValuePair ".config/ai/settings/${name}.json" {
      source = json.generate "${name}.json" e.settings;
    }) (lib.filterAttrs (_: e: e.settings != { }) (enabled cfg.skills // enabled cfg.agents))
    // lib.listToAttrs (map (p: lib.nameValuePair ".config/ai/review-lenses/${baseNameOf p}" { source = p; }) cfg.reviewLenses)
    // lib.optionalAttrs (cfg.secrets.readCommand != null) {
      ".config/ai/secrets.json".source = json.generate "secrets.json" { inherit (cfg.secrets) readCommand; };
    };

    home.packages = lib.concatMap (e: e.packages) (lib.attrValues (enabled cfg.skills // enabled cfg.agents))
      ++ [ pkgs.uv pkgs.pandoc pkgs.ghostscript pkgs.poppler-utils ];
  };
}
