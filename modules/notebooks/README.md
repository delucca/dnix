# notebooks

Install shared agent instructions for a notebook tree and optionally back up its Org files.
The Home Manager module defaults to `~/Notebooks`; each notebook is a directory containing `notebook.org`.

## Use

With [the dnix input available](../../README.md#use-a-module), add:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.homeManagerModules.notebooks ];
  dnix.notebooks.enable = true;
}
```

See [the option definitions](default.nix) for `root` and `scopes`. Scopes contain lowercase letters; the default list is `[ "personal" ]`.

## Agent instructions

The module places [the notebook rules](AGENTS.md) at `<root>/AGENTS.md` and makes `<root>/CLAUDE.md` a symlink to it.
The symlink lets Claude load those rules when the notebook tree is supplied as an added directory; a file containing only `@AGENTS.md` does not serve that workflow. Sessions use the Developer tree as their working directory.

## Backup coverage

Backups are off by default and require Darwin because scheduling uses launchd. Enable `dnix.notebooks.backup.enable` and provide `repository` and `passwordCommand`; [backup options](backup.nix) also accept `credentialCommands`, `extraPaths` and `autoInit`.

At login and hourly, the agent snapshots every `notebook.org` under the root except paths inside `node_modules`, plus `extraPaths`. Other notebook contents, including `work/` and `assets/`, are outside the default coverage; include them explicitly if needed.

Snapshots are recorded under the short hostname (`hostname -s`) and grouped by host alone, so adding, moving or archiving a notebook does not start a new group. Give the backup a repository of its own: other snapshots from this host in the same repository would be thinned and pruned with the notebooks. The agent retains this host's snapshots at 48 hourly, 30 daily and 12 monthly, across every path set it has backed up, and prunes at most once a day.

The agent initializes the repository only when restic reports that it does not exist. Any other failure, such as a wrong password, a failing credential command or an unreachable repository, stops the run with restic's error in the log. A repository in a synced folder, such as Google Drive, looks missing until the folder has synced; set `autoInit = false` for it and run `restic-notebooks init` once by hand.

`restic-notebooks` runs restic with the repository and credentials configured for restore operations. Logs go to `~/.local/log/notebooks-backup.log`.

Password and credential commands run at backup time. Their command text enters the Nix store, so use commands that retrieve secrets rather than embedding secret values. Commands must resolve through the Home Manager profile and `/usr/bin:/bin`.
