# notebooks

The home-manager module that renders `~/Notebooks/AGENTS.md` and links `~/Notebooks/CLAUDE.md` to it, so a notebook session that gets the tree as an added directory reads its rules. A flake takes it as `dnix.homeManagerModules.notebooks` and a host sets `dnix.notebooks.enable = true`.

`CLAUDE.md` is a symlink to `AGENTS.md`, not a file that imports it: a notebook session's working directory is `~/Developer`, and an `@AGENTS.md` import is skipped when the tree arrives as an added directory, while a symlinked `CLAUDE.md` there loads.

## Files

```
default.nix      the options and the two home.file entries
AGENTS.md        the rules rendered at the root of the tree
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.notebooks.enable` | `false` | Turns the module on. |
| `dnix.notebooks.root` | `~/Notebooks` | Where the tree lives. |
| `dnix.notebooks.scopes` | `[ "personal" ]` | The scopes this machine holds, lowercase slugs. A notebook folder ends in `__<scope>`; the first is the default for a new notebook. |
