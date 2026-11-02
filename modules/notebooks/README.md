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

Backups are off by default and require Darwin because scheduling uses launchd. Enable `dnix.notebooks.backup.enable` and provide `repository` and `passwordCommand`; [backup options](backup.nix) also accept `credentialCommands` and `extraPaths`.

At login and hourly, the agent snapshots every `notebook.org` under the root except paths inside `node_modules`, plus `extraPaths`. Other notebook contents, including `work/` and `assets/`, are outside the default coverage; include them explicitly if needed.

The agent initializes a missing restic repository, retains this host's snapshots at 48 hourly, 30 daily and 12 monthly, and prunes at most once a day. `restic-notebooks` runs restic with the repository and credentials configured for restore operations. Logs go to `~/.local/log/notebooks-backup.log`.

Password and credential commands run at backup time. Their command text enters the Nix store, so use commands that retrieve secrets rather than embedding secret values. Commands must resolve through the Home Manager profile and `/usr/bin:/bin`.
