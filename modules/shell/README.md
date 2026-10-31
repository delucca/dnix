# shell

The home-manager module for zsh: oh-my-zsh with its `git` plugin, autosuggestions, syntax highlighting and history substring search in vi insert mode, fzf with fzf-tab, zoxide as `cd`, and the starship prompt. A flake takes it as `dnix.homeManagerModules.shell` and a host sets `dnix.shell.enable = true`. It works on any platform; only the clipboard aliases are darwin-only.

## Files

```
default.nix      the option, the packages, and the zsh, starship, zoxide and fzf settings
functions.zsh    `up`, sourced into ~/.zshrc
starship.toml    the prompt
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.shell.enable` | `false` | Turns the module on. |

```nix
dnix.shell.enable = true;
```

## What it sets

- `eza`, `tree`, `bat`, `neovim` and `shellcheck` on the path, `~/.local/bin` ahead of them, and `EDITOR = nvim`.
- Aliases `l` (eza long listing), `nv` (nvim), and on darwin `c`/`v` for `pbcopy`/`pbpaste`; oh-my-zsh adds its git aliases.
- `up` climbs directories: `up` one level, `up 3` three, `up name` to the nearest ancestor whose name starts with `name`.
- Tab completion previews files with bat and directories with tree.

## Notes

- The zsh files go where home-manager puts them: `~/.zshrc` by default, `~/.config/zsh` on a host with `xdg.enable` and a `home.stateVersion` of 26.05 or later.
- Anything else goes in the host's own `programs.zsh` next to it; aliases, init and session variables merge.
- The prompt loads `starship.toml` into `programs.starship.settings`, so a host overrides one key there, such as `programs.starship.settings.character.success_symbol`, and keeps the rest.
