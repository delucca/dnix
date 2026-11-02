# shell

Set up Zsh with completion previews, directory navigation and a Starship prompt.
The Home Manager module enables oh-my-zsh's Git plugin, autosuggestions, syntax highlighting, history substring search, fzf and fzf-tab.

## Use

With [the dnix input available](../../README.md#use-a-module), add:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.homeManagerModules.shell ];
  dnix.shell.enable = true;
}
```

## Shell defaults

- Zsh starts in vi insert mode, shares history between sessions and ignores history entries with a leading space.
- `eza`, `tree`, `bat`, `neovim` and `shellcheck` are installed; `~/.local/bin` is added to PATH and `EDITOR` is `nvim`.
- `l` runs an eza long listing and `nv` opens Neovim. Darwin also gets `c` and `v` for `pbcopy` and `pbpaste`. The Git plugin adds its own aliases.
- Zoxide handles interactive `cd`. The [up function](functions.zsh) climbs one directory with `up`, three with `up 3`, or to the nearest ancestor with a matching name prefix using `up name`.
- Tab completion previews files with bat and directories with tree.

## Customise

The [module settings](default.nix) are the reference for packages, aliases and history behavior. Add your own `programs.zsh` settings in the consumer configuration; Home Manager controls where the Zsh files are written.

The [Starship configuration](starship.toml) supplies defaults, so you can override individual `programs.starship.settings` keys while retaining the rest of the prompt.
