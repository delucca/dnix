# developer

The home-manager module that owns the `~/Developer` tree: the clones, the per-group worktree folders, and the `AGENTS.md` at the root. A flake takes it as `dnix.homeManagerModules.developer` and a host sets `dnix.developer.enable = true`.

## Files

```
default.nix      the options, the clone activation script, the AGENTS.md composition
instructions/    the module's own sections of AGENTS.md, one `NN-name.md` each
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.developer.enable` | `false` | Turns the module on. |
| `dnix.developer.root` | `~/Developer` | Where the tree lives. |
| `dnix.developer.repositories` | none | The roster, one row per repo. The host lists every row. |
| `dnix.developer.gitPath` | `~/.local/bin`, Homebrew and the system dirs | The `PATH` the clones run on, for a host whose git or ssh lives elsewhere. |
| `dnix.developer.instructionDirs` | none | More folders of `NN-name.md` sections, read like `instructions/`. |
| `dnix.developer.instructions` | `instructions/*.md` and `instructionDirs` | The sections `AGENTS.md` is composed from. |
| `dnix.developer.agentsText` | read-only | The composed `AGENTS.md`, for a harness that never reads it by walking up. |

A `repositories` row:

| Field | Default | Meaning |
|---|---|---|
| `path` | required | `<group>/<repo>`, the row's identity |
| `dir` | `path` | where the clone lands under the root; its first segment is the group |
| `name` | basename of `path` | the name in warnings and in a session label |
| `url` | required | `origin` |
| `upstream` | `null` | a second remote, for a fork |
| `addDirs` | `[ "." ]` | the directories an agent session adds, relative to the clone |

```nix
dnix.developer.repositories = [
  { path = "delucca/dnix"; url = "git@github.com:delucca/dnix.git"; }
  { path = "acme/core"; dir = "acme/repos/core"; url = "git@github.com:acme/core.git"; upstream = "https://github.com/vuejs/core.git"; }
];
```

## What a switch does

- Clones every row that is absent into `<root>/<dir>`, in `dir` order so a clone nested under another lands after its parent. A failed clone warns and the switch goes on; re-run it once auth works. A path that exists and is not a git checkout is left alone.
- Reconciles `origin` and `upstream` on every existing clone, so a renamed repo needs only its row changed.
- Creates `<root>/<group>/.worktrees` for every group.
- Writes `<root>/AGENTS.md`, and a `CLAUDE.md` beside it that only imports it: Codex reads `AGENTS.md` and has no import, so that is the real file.

## Composing AGENTS.md

The sections are concatenated by `order`. A file `NN-name.md` in `instructions/` or in an `instructionDirs` folder becomes the section `name` at order `NN`. The module's own sections sit at 10, 20 and 30, so a section can slot between them. Two sections with the same name are an error.

The module's sections describe only what it makes: the tree, the worktree workflow, and how to add a repo. Anything specific to a person or a company, such as ticket rules or where tests run, comes from the flake that imports it:

```nix
dnix.developer.instructionDirs = [ ./instructions ];
dnix.developer.instructions.<name> = { order = 50; source = ./<file>.md; };
```

`text` can be set in place of `source`.
