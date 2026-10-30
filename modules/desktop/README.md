# desktop

The home-manager module for a Mac with a screen: `.app` bundles copied into `/Applications`, home folders kept in shape, a Chrome with the DevTools port open, and ghostty. A flake takes it as `dnix.homeManagerModules.desktop` and a host sets `dnix.desktop.enable = true`. Everything here only acts on darwin.

## Files

```
default.nix        the imports and `dnix.desktop.enable`
mac-apps.nix       `dnix.macApps.apps`: `.app` bundles copied from the store into `/Applications`
home-folders.nix   `dnix.homeFolders`: home folders created, hidden from Finder, or asserted as iCloud symlinks
chrome.nix         a launchd agent for a Chrome with the DevTools port 9222 open, on its own profile
ghostty/           the ghostty bundle, through `dnix.macApps`, and its config
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
- The Chrome agent runs `/Applications/Google Chrome.app` on `~/.chrome-debug-profile` and logs to `~/.local/log/chrome-devtools-browser.log`. Chrome itself is not installed by this module.
- The ghostty config sets `font-family = MonoLisaCode` and does not install the font: the consumer provides it.
