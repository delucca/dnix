{ config, lib, ... }:

{
  config = lib.mkIf config.dnix.desktop.enable {
    programs.git = {
      enable = true;
      lfs.enable = true;
      ignores = [
        ".DS_Store"
        ".DS_Store?"
        "._*"
        ".Spotlight-V100"
        ".Trashes"
        "*.swp"
        "*.swo"
        "*~"
        ".direnv/"
      ];
      settings = {
        alias = {
          br = "branch";
          ci = "commit -a";
          co = "checkout";
          d = "diff --color-words";
          who = "shortlog -s --";
          lg = "log --graph --all --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr)%Creset' --abbrev-commit --date=relative";
          lpo = "log --pretty=oneline --abbrev-commit --graph --decorate --all";
          scrub = "!git reset --hard && git clean -fd";
          re = "remote -v";
          st = "status";
          blg = "log --graph --decorate --all --abbrev-commit --pretty=oneline";
          slog = "log --graph --simplify-by-decoration --all --abbrev-commit --pretty=oneline";
          pushnotes = "!sh -c 'git push $1 refs/notes/*' -";
          fetchnotes = "!sh -c 'git fetch $1 refs/notes/*:refs/notes/*' -";
          showignored = "ls-files --others --ignored --exclude-standard";
          showuntracked = "ls-files --others --exclude-standard";
          rmmissing = "!git rm $(git ls-files --deleted)";
          busythisweek = "shortlog --since=one.week.ago -n";
          aliases = "!git config --get-regexp 'alias.*' | colrm 1 6 | sed 's/[ ]/ = /'";
          whitespaceviolations = "!git diff --check $(git empty-tree-sha1)";
          app = "commit -a --amend --no-edit";
          cia = "commit -a --amend";
          up = "remote update --prune";
          dft = "difftool";
        };
        core = {
          quotepath = false;
          autocrlf = "input";
          safecrlf = "warn";
        };
        apply.whitespace = "nowarn";
        rerere.enabled = true;
        difftool.prompt = false;
        pager.difftool = true;
        mergetool = {
          prompt = false;
          keepBackup = false;
        };
        fetch.prune = true;
        pull.rebase = false;
        push.default = "current";
        color.ui = true;
        init.defaultBranch = "main";
      };
    };

    programs.difftastic = {
      enable = true;
      git = {
        enable = true;
        diffToolMode = true;
      };
      options.background = "dark";
    };
  };
}
