# developer

Maintain a repository roster under `~/Developer`, with one clone per entry and a worktree directory per group.
The Home Manager module also composes the instructions at the tree root.

## Use

Git and any transport credentials must be available during activation. `dnix.developer.gitPath` controls the activation PATH.
With [the dnix input available](../../README.md#use-a-module), add:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.homeManagerModules.developer ];
  dnix.developer = {
    enable = true;
    repositories = [
      { path = "delucca/dnix"; url = "https://github.com/delucca/dnix.git"; }
    ];
  };
}
```

See [the option definitions](default.nix) for the roster and root settings.
A row's `path` identifies it; `dir` defaults to that path and sets its location under the root. The first directory segment determines its group. `upstream` adds a fork's second remote, and `addDirs` supplies directories for agent sessions.

## Activation behavior

Activation clones missing rows in directory order, so a parent clone precedes nested members. A failed clone warns and lets activation continue; an existing non-checkout is left alone.
For existing checkouts it reconciles `origin` and any configured `upstream`, then creates `<root>/<group>/.worktrees`.
Removing a roster row does not delete its checkout, and removing `upstream` from a row does not delete that remote.

The module writes `<root>/AGENTS.md` and a `CLAUDE.md` containing `@AGENTS.md`. Task worktrees are created by the workflow described in those instructions, rather than by roster activation.

## Compose instructions

The shipped [instruction sections](instructions/) describe the tree, worktree workflow and repository registration.
Add consumer-specific sections through `dnix.developer.instructionDirs`, using files named `NN-name.md`, or through `dnix.developer.instructions.<name>` with an `order` and either `source` or `text`.
Sections are concatenated by numeric order. Use distinct names in instruction directories: duplicate names collapse to one attribute rather than producing a separate section.

`dnix.developer.agentsText` exposes the composed text to harnesses that do not walk up to the tree root. Keep machine, organisation and ticket policy in the consumer's sections.
