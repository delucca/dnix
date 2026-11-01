# notebooks

The home-manager module that renders `~/Notebooks/AGENTS.md` and links `~/Notebooks/CLAUDE.md` to it, so a notebook session that gets the tree as an added directory reads its rules. A flake takes it as `dnix.homeManagerModules.notebooks` and a host sets `dnix.notebooks.enable = true`.

`CLAUDE.md` is a symlink to `AGENTS.md`, not a file that imports it: a notebook session's working directory is `~/Developer`, and an `@AGENTS.md` import is skipped when the tree arrives as an added directory, while a symlinked `CLAUDE.md` there loads.

## Files

```
default.nix      the options and the two home.file entries
backup.nix       dnix.notebooks.backup: hourly restic snapshots of every notebook.org, from launchd
AGENTS.md        the rules rendered at the root of the tree
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.notebooks.enable` | `false` | Turns the module on. |
| `dnix.notebooks.root` | `~/Notebooks` | Where the tree lives. |
| `dnix.notebooks.scopes` | `[ "personal" ]` | The scopes this machine holds, lowercase slugs. A notebook folder ends in `__<scope>`; the first is the default for a new notebook. |
| `dnix.notebooks.backup.enable` | `false` | Snapshots every `notebook.org` under `root` with restic, hourly, from a launchd agent. Needs darwin. |
| `dnix.notebooks.backup.repository` | | The restic repository, as `restic -r` takes it. |
| `dnix.notebooks.backup.passwordCommand` | | A command that prints the repository password. |
| `dnix.notebooks.backup.credentialCommands` | `{ }` | Environment variable to command; each command's output becomes that variable for restic, such as `AWS_ACCESS_KEY_ID` for an S3 repository. Commands run at backup time, so no secret lands in the store. |
| `dnix.notebooks.backup.extraPaths` | `[ ]` | More paths to snapshot with the notebooks. |

## Backup

Every hour, and at login, the agent initializes the repository if it is missing, snapshots the `notebook.org` files (skipping `node_modules`) and `extraPaths`, then forgets this host's snapshots down to 48 hourly, 30 daily and 12 monthly. It prunes at most once a day. `restic-notebooks` is restic with the repository and credentials already set, for restores. The log is `~/.local/log/notebooks-backup.log`.

The agent's `PATH` is the home-manager profile plus `/usr/bin:/bin`, so the password and credential commands must resolve there.
