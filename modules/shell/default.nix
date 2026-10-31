{ config, lib, pkgs, ... }:

let
  isDarwin = pkgs.stdenv.hostPlatform.isDarwin;
in
{
  options.dnix.shell.enable = lib.mkEnableOption "the zsh shell";

  config = lib.mkIf config.dnix.shell.enable {
    home.packages = with pkgs; [ eza tree bat neovim shellcheck ];

    home.sessionPath = [ "$HOME/.local/bin" ];

    home.sessionVariables = {
      EDITOR = "nvim";
      EZA_COLORS = "di=38;2;137;180;250:ln=38;2;148;226;213:ex=38;2;166;227;161:"
        + "ur=38;2;249;226;175:uw=38;2;250;179;135:ux=38;2;166;227;161:"
        + "gr=38;2;249;226;175:gw=38;2;250;179;135:gx=38;2;166;227;161:"
        + "tr=38;2;249;226;175:tw=38;2;250;179;135:tx=38;2;166;227;161:"
        + "sn=38;2;166;227;161:sb=38;2;166;227;161:uu=38;2;203;166;247:"
        + "da=38;2;147;153;178";
    };

    programs.zsh = {
      enable = true;
      defaultKeymap = "viins";
      localVariables.COMPLETION_WAITING_DOTS = "true";
      oh-my-zsh = {
        enable = true;
        plugins = [ "git" ];
      };
      autosuggestion.enable = true;
      syntaxHighlighting = {
        enable = true;
        styles = {
          command = "fg=#CBA6F7";
          builtin = "fg=#CBA6F7";
          alias = "fg=#CBA6F7";
        };
      };
      historySubstringSearch = {
        enable = true;
        searchUpKey = [ "^[[A" "$terminfo[kcuu1]" ];
        searchDownKey = [ "^[[B" "$terminfo[kcud1]" ];
      };
      history = {
        size = 50000;
        save = 10000;
        extended = true;
        expireDuplicatesFirst = true;
        ignoreDups = true;
        ignoreSpace = true;
        share = true;
      };
      shellAliases = {
        l = "eza -lah --group-directories-first --git";
        nv = "nvim";
      } // lib.optionalAttrs isDarwin {
        c = "pbcopy";
        v = "pbpaste";
      };
      initContent = lib.mkMerge [
        (lib.mkOrder 550 "zmodload -i zsh/terminfo")
        (lib.mkOrder 950 "source ${pkgs.zsh-fzf-tab}/share/fzf-tab/fzf-tab.plugin.zsh")
        (builtins.readFile ./functions.zsh)
        ''
          zstyle ':fzf-tab:*' fzf-preview 'if [[ -f $realpath ]]; then; bat --color=always --style=numbers $realpath; else; tree -L 2 $realpath; fi'
          zstyle ':fzf-tab:complete:cd:*' fzf-preview 'tree -L 2 $realpath'
        ''
        (lib.mkAfter ''
          if [[ -o interactive ]]; then
            eval "$(${lib.getExe config.programs.zoxide.package} init zsh --cmd cd)"
          fi
        '')
      ];
    };

    programs.starship.enable = true;
    xdg.configFile."starship.toml".source = ./starship.toml;

    programs.zoxide = {
      enable = true;
      enableZshIntegration = false;
    };

    programs.fzf.enable = true;
  };
}
