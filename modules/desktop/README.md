# desktop

The home-manager module for a Mac with a screen: `.app` bundles copied into `/Applications`, home folders kept in shape, a Chrome with the DevTools port open, an optional guard that keeps the Ask Siri shortcut off, ghostty, and git. A flake takes it as `dnix.homeManagerModules.desktop` and a host sets `dnix.desktop.enable = true`. The `.app` copier, the home folders, the Chrome agent and the Siri guard only act on darwin; git applies on any platform.

## Files

```
default.nix        the imports and `dnix.desktop.enable`
mac-apps.nix       `dnix.macApps.apps`: `.app` bundles copied from the store into `/Applications`
home-folders.nix   `dnix.homeFolders`: home folders created, hidden from Finder, or asserted as iCloud symlinks
chrome.nix         a launchd agent for a Chrome with the DevTools port 9222 open, on its own profile, and `chrome_up`/`chrome_down`
siri-shortcut.nix  `dnix.desktop.disableSiriShortcut`: two launchd agents that keep the Ask Siri keyboard shortcut off
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
| `dnix.desktop.disableSiriShortcut` | `false` | Keeps the Ask Siri keyboard shortcut off and restarts the Siri daemons when it comes back. |

```nix
dnix.desktop.enable = true;
dnix.macApps.apps = [ pkgs.appcleaner ];
dnix.homeFolders.icloudLinks = [ "Desktop" "Downloads" ];
```

## Notes

- Copying into `/Applications` needs the user in the admin group; without it the bundle is skipped with a warning.
- The Chrome agent runs `/Applications/Google Chrome.app` on `~/.chrome-debug-profile` and logs to `~/.local/log/chrome-devtools-browser.log`. Chrome itself is not installed by this module. `chrome_up [url]` starts it and waits for the port, optionally opening `url`; `chrome_down` stops it.
- `dnix.desktop.disableSiriShortcut` is for hyper keys (Superkey) that press Cmd around every synthesized arrow: macOS reads that as the double-Cmd Ask Siri trigger and eats the keystroke. Only the enabled flag of `com.apple.Siri` `KeyboardShortcutSAE` is rewritten; the stored shortcut is kept. A host that uses a Siri shortcut should leave it off.
- The watch agent runs on a change to `~/Library/Preferences/com.apple.Siri.plist`, which System Settings writes when the shortcut dropdown is touched, and every 30 minutes in case the file is replaced and the watch is lost. It only writes when the flag is on, since its own write fires the watch again.
- The login agent always rewrites the flag and restarts the daemons, 45 seconds after login: after a macOS update the plist can be clean while the running daemons still listen for Cmd. Both log to `~/.local/log/siri-shortcut-guard.log`.
- The ghostty config sets `font-family = MonoLisaCode` and does not install the font: the consumer provides it.
- git sets no identity, signing or merge tool: the host sets them in its own `programs.git`. A key this module already sets takes `lib.mkForce` to change.
- `git diff` renders through difftastic. Use `git diff --no-ext-diff` for a patch.
