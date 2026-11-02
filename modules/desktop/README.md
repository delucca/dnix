# desktop

Configure a desktop with Ghostty and Git, plus macOS app copying, home folders and a Chrome debugging session.
The Home Manager module applies Git settings and Ghostty configuration on every platform; app copying, folder management, Chrome and the optional Siri shortcut guard run only on Darwin.

## Use

On macOS, install Google Chrome at `/Applications/Google Chrome.app` and provide the `MonoLisaCode` font used by the Ghostty configuration.
With [the dnix input available](../../README.md#use-a-module), add:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.homeManagerModules.desktop ];
  dnix.desktop.enable = true;
}
```

The module installs Ghostty's app bundle on Darwin. On other platforms it writes the configuration but does not install Ghostty.

## Desktop behavior

- [App copying](mac-apps.nix) installs `dnix.macApps.apps` bundles into `/Applications`. That directory must be writable by the user; otherwise activation warns and skips the bundle. Ghostty's self-updater is disabled, so update it through the consumer's flake lock.
- [Home folder settings](home-folders.nix) create directories, hide them in Finder or link them into iCloud Drive. Existing real directories are left in place with a warning.
- [Chrome](chrome.nix) uses a separate `~/.chrome-debug-profile` with DevTools on port 9222. `chrome_up [url]` starts it and waits for readiness; `chrome_down` stops that profile. Chrome itself is an external prerequisite.
- [The Siri guard](siri-shortcut.nix) is opt-in through `dnix.desktop.disableSiriShortcut`. It keeps Ask Siri's keyboard shortcut disabled while retaining the stored shortcut value, and restarts the Siri daemons.

## Git and terminal settings

[Git settings](git.nix) enable Git LFS, aliases and difftastic as a diff tool. Identity, signing and merge-tool selection belong in your own `programs.git` configuration. Conflicting settings may need `lib.mkForce`.

The [Ghostty configuration](ghostty/config) contains the font, theme, keybindings and clipboard behavior. The [module entry point](default.nix) links the imported components and their options.
