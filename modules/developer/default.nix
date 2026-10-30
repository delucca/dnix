# The Developer tree: one plain clone per roster repo under
# <root>/<group>/<repo>, a .worktrees directory per group, and the
# AGENTS.md that tells an agent how to work in it.
{ config, lib, ... }:

let
  cfg = config.dnix.developer;

  # AGENTS.md is the concatenation of dnix.developer.instructions sorted by
  # order: the NN-name.md sections of ./instructions and of every
  # instructionDirs entry, plus whatever other modules add. CLAUDE.md only
  # imports the result: Claude Code reads CLAUDE.md and follows @imports,
  # Codex reads AGENTS.md and has no import, so the one real file has to be
  # AGENTS.md.
  sectionsOf = dir:
    lib.concatMap (f:
      let m = builtins.match "([0-9]+)-([a-z0-9-]+)\\.md" f;
      in lib.optional (m != null) (lib.nameValuePair (builtins.elemAt m 1) {
        order = lib.toInt (builtins.elemAt m 0);
        source = dir + "/${f}";
      }))
    (builtins.attrNames (builtins.readDir dir));
  agentsText = lib.concatMapStringsSep "\n\n" (s: lib.removeSuffix "\n" s.text)
    (lib.sortOn (s: s.order) (lib.attrValues cfg.instructions)) + "\n";

  # home.file keys are taken verbatim; only the submodule's own `target` is
  # home-relativized. An absolute key renders under $HOME/<absolute path>.
  relRoot = lib.removePrefix (config.home.homeDirectory + "/") cfg.root;

  cloneOf = r: "${cfg.root}/${r.dir}";
  cloneDirs = map (r: r.dir) cfg.repositories;
  groups = lib.unique (map (r: lib.head (lib.splitString "/" r.dir)) cfg.repositories);

  # A group folder that is itself a clone gets its .worktrees only once that
  # clone is there: git refuses to clone into a directory that already exists.
  worktreesDir = g:
    let mk = ''run mkdir -p "${cfg.root}/${g}/.worktrees"'';
    in if lib.elem g cloneDirs
       then ''if [ -d "${cfg.root}/${g}/.git" ]; then ${mk}; fi''
       else mk;
in
{
  options.dnix.developer = {
    enable = lib.mkEnableOption "the Developer tree";

    root = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/Developer";
    };

    repositories = lib.mkOption {
      type = lib.types.listOf (lib.types.submodule ({ config, ... }: {
        options = {
          path = lib.mkOption { type = lib.types.str; };
          # Where the clone lands, relative to the root. Its first segment is
          # the group whose .worktrees the task worktrees are cut into.
          dir = lib.mkOption {
            type = lib.types.str;
            default = config.path;
          };
          name = lib.mkOption {
            type = lib.types.str;
            default = baseNameOf config.path;
          };
          url = lib.mkOption { type = lib.types.str; };
          # A second remote on the clone, for a fork whose public repo the
          # work reads from.
          upstream = lib.mkOption { type = lib.types.nullOr lib.types.str; default = null; };
          addDirs = lib.mkOption { type = lib.types.listOf lib.types.str; default = [ "." ]; };
        };
      }));
      default = [ ];
    };

    # The activation PATH carries no git, so the clones run on this one.
    gitPath = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin";
    };

    instructionDirs = lib.mkOption {
      type = lib.types.listOf lib.types.path;
      default = [ ];
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
    };

    # For a harness that never walks up past the repo root to this file.
    agentsText = lib.mkOption {
      type = lib.types.str;
      readOnly = true;
      description = "The composed AGENTS.md at the root.";
    };
  };

  config = lib.mkIf cfg.enable {
    dnix.developer.agentsText = agentsText;

    dnix.developer.instructions = lib.listToAttrs (lib.concatMap sectionsOf ([ ./instructions ] ++ cfg.instructionDirs));

    home.file = {
      "${relRoot}/AGENTS.md".text = cfg.agentsText;
      "${relRoot}/CLAUDE.md".text = "@AGENTS.md\n";
    };

    home.activation = {
      # One plain clone per row, at <root>/<dir>. The remotes are reconciled
      # on every switch, so a renamed repo or a new upstream needs only its
      # row changed. Sorted by dir: a clone nested under another must not land
      # before its parent, or the parent's own clone is blocked.
      developerClone = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
        run mkdir -p "${cfg.root}"
        ${lib.concatMapStrings (r: ''
          if [ ! -e "${cloneOf r}" ]; then
            # BatchMode/ConnectTimeout so a sleeping remote's row fails fast
            # and warns, rather than hanging the whole switch on a password
            # prompt or a dead connection.
            run env PATH="${cfg.gitPath}" GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10" \
                 git clone ${lib.escapeShellArg r.url} "${cloneOf r}" \
              || warnEcho "developer: clone failed for ${r.name} -- re-run the switch once auth works"
          elif [ ! -e "${cloneOf r}/.git" ]; then
            warnEcho "developer: ${cloneOf r} exists but is not a git checkout -- leaving it alone"
          fi
          if [ -e "${cloneOf r}/.git" ]; then
            run env PATH="${cfg.gitPath}" git -C "${cloneOf r}" remote set-url origin ${lib.escapeShellArg r.url}
            ${lib.optionalString (r.upstream != null) ''
              if env PATH="${cfg.gitPath}" git -C "${cloneOf r}" remote get-url upstream >/dev/null 2>&1; then
                run env PATH="${cfg.gitPath}" git -C "${cloneOf r}" remote set-url upstream ${lib.escapeShellArg r.upstream}
              else
                run env PATH="${cfg.gitPath}" git -C "${cloneOf r}" remote add upstream ${lib.escapeShellArg r.upstream}
              fi
            ''}
          fi
        '') (lib.sortOn (r: r.dir) cfg.repositories)}
        ${lib.concatMapStringsSep "\n" worktreesDir groups}
      '';
    };
  };
}
