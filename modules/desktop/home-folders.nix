{ config, lib, pkgs, ... }:

let
  cfg = config.dnix.homeFolders;
  home = config.home.homeDirectory;
  icloud = "${home}/Library/Mobile Documents/com~apple~CloudDocs";
in
{
  options.dnix.homeFolders = {
    create = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
    };
    hidden = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
    };
    icloudLinks = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
    };
  };

  config = lib.mkIf (config.dnix.desktop.enable && pkgs.stdenv.hostPlatform.isDarwin) {
    home.activation.homeFolders = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      for name in ${lib.escapeShellArgs cfg.create}; do
        run mkdir -p "${home}/$name"
      done

      for name in ${lib.escapeShellArgs cfg.hidden}; do
        dir="${home}/$name"
        [ -d "$dir" ] || continue
        case "$(/usr/bin/stat -f %Sf "$dir")" in
          *hidden*) ;;
          *) run /usr/bin/chflags hidden "$dir" || warnEcho "home-folders: could not hide $dir" ;;
        esac
      done

      for name in ${lib.escapeShellArgs cfg.icloudLinks}; do
        link="${home}/$name"
        target="${icloud}/$name"
        if [ -L "$link" ]; then
          [ "$(readlink "$link")" = "$target" ] \
            || warnEcho "home-folders: $link points at $(readlink "$link"), not $target"
        elif [ ! -e "$link" ] && [ -d "$target" ]; then
          run ln -s "$target" "$link"
        else
          warnEcho "home-folders: $link is not a symlink into iCloud Drive -- left alone, link it by hand once it is empty"
        fi
      done
    '';
  };
}
