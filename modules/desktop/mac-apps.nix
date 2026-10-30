{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.macApps;
  stampDir = "${config.home.homeDirectory}/.local/state/mac-apps";
  lsregister = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister";
in
{
  options.dnix.macApps.apps = lib.mkOption {
    type = lib.types.listOf lib.types.package;
    default = [ ];
  };

  config = lib.mkIf (config.dnix.desktop.enable && pkgs.stdenv.hostPlatform.isDarwin && cfg.apps != [ ]) {
    home.activation.macApps = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      run mkdir -p "${stampDir}"
      for pkgApps in ${lib.escapeShellArgs (map (p: "${p}/Applications") cfg.apps)}; do
        for src in "$pkgApps"/*.app; do
          [ -d "$src" ] || continue
          name="''${src##*/}"
          dst="/Applications/$name"
          stamp="${stampDir}/$name"
          if [ -d "$dst" ] && [ ! -L "$dst" ] \
             && [ "$(readlink "$stamp" 2>/dev/null || true)" = "$src" ]; then
            continue
          fi
          if [ ! -w /Applications ]; then
            warnEcho "mac-apps: /Applications is not writable by $USER -- $name not installed. Add this user to the admin group, or install the bundle by hand from $src."
            continue
          fi
          stage="/Applications/.$name.mac-apps-staged"
          prev="/Applications/.$name.mac-apps-previous"
          if ! { run rm -rf "$stage" "$prev" \
                 && run cp -R "$src" "$stage" \
                 && run chmod -R u+w "$stage" \
                 && { { [ ! -e "$dst" ] && [ ! -L "$dst" ]; } || run mv "$dst" "$prev"; } \
                 && run mv "$stage" "$dst"; }; then
            warnEcho "mac-apps: installing $name failed -- re-run the switch. If /Applications/$name is missing, $prev holds the copy that was there."
            run rm -rf "$stage" || true
            if [ ! -e "$dst" ] && [ -e "$prev" ]; then
              run mv "$prev" "$dst" \
                || warnEcho "mac-apps: could not restore $name -- the previous bundle is at $prev."
            fi
            continue
          fi
          run rm -rf "$prev" \
            || warnEcho "mac-apps: $name is installed, but its previous bundle is still at $prev -- remove it by hand."
          run ln -sfn "$src" "$stamp" \
            || warnEcho "mac-apps: could not stamp $name -- it is installed, but the next switch will copy it again."
          run ${lsregister} -f "$dst" \
            || warnEcho "mac-apps: lsregister failed for $name -- the copy is in place, but Spotlight may not see it until macOS rescans."
        done
      done
    '';
  };
}
