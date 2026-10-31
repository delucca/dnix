# desktop

The home-manager module for a Mac with a screen: `.app` bundles copied into `/Applications`, home folders kept in shape, a Chrome with the DevTools port open, ghostty, and git. A flake takes it as `dnix.homeManagerModules.desktop` and a host sets `dnix.desktop.enable = true`. The `.app` copier, the home folders and the Chrome agent only act on darwin; git applies on any platform.

## Files

```
default.nix        the imports and `dnix.desktop.enable`
mac-apps.nix       `dnix.macApps.apps`: `.app` bundles copied from the store into `/Applications`
home-folders.nix   `dnix.homeFolders`: home folders created, hidden from Finder, or asserted as iCloud symlinks
chrome.nix         a launchd agent for a Chrome with the DevTools port 9222 open, on its own profile, and `chrome_up`/`chrome_down`
ghostty/           the ghostty bundle, through `dnix.macApps`, and its config
git.nix            git config and aliases, lfs, difftastic as the diff renderer
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.desktop.enable` | `false` | Turns the module on. |
| `dnix.macApps.apps` | `[ ]` | Every `<pkg>/Applications/*.app` is copied into `/Applications`, swapped in through a staged copy, and registered with LaunchServices. A stamp under `~/.local/state/mac-apps` skips a bundle that has not changed. |
| `dnix.homeFolders.create` | `[ ]` | Names created under `$HOME`. |
| `dnix.homeFolders.hidden` | `[ ]` | Names hidden from Finder. |
| `dnix.homeFolders.icloudLinks` | `[ ]` | Names asserted as symlinks into iCloud Drive. A real folder is left alone with a warning. |

```nix
dnix.desktop.enable = true;
dnix.macApps.apps = [ pkgs.appcleaner ];
dnix.homeFolders.icloudLinks = [ "Desktop" "Downloads" ];
```

## Notes

- Copying into `/Applications` needs the user in the admin group; without it the bundle is skipped with a warning.
- The Chrome agent runs `/Applications/Google Chrome.app` on `~/.chrome-debug-profile` and logs to `~/.local/log/chrome-devtools-browser.log`. Chrome itself is not installed by this module. `chrome_up [url]` starts it and waits for the port, optionally opening `url`; `chrome_down` stops it.
- The ghostty config sets `font-family = MonoLisaCode` and does not install the font: the consumer provides it.
- git sets no identity, signing or merge tool: the host sets them in its own `programs.git`. A key this module already sets takes `lib.mkForce` to change.
- `git diff` renders through difftastic. Use `git diff --no-ext-diff` for a patch.
