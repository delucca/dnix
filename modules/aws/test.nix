{ pkgs }:

let
  inherit (pkgs) lib;
  fakeOp = pkgs.writeShellScriptBin "op" ''
    [ "$*" = "item get abc 123 --vault My Vault --fields label=key id,label=key secret --reveal --format json" ] || { echo "unexpected args: $*" >&2; exit 9; }
    echo '[{"label":"key id","value":"AKIDEXAMPLE"},{"label":"key secret","value":"s3cr\"et"}]'
  '';
  eval = profiles: lib.evalModules {
    modules = [
      ./default.nix
      {
        options.assertions = lib.mkOption { type = lib.types.listOf lib.types.attrs; };
        options.programs.awscli = {
          enable = lib.mkOption { type = lib.types.bool; };
          settings = lib.mkOption { type = lib.types.attrs; };
        };
        config._module.args = { inherit pkgs; };
        config.dnix.aws = {
          enable = true;
          op.package = fakeOp;
          inherit profiles;
        };
      }
    ];
  };
  good = (eval {
    default.region = "us-east-1";
    work = {
      region = "eu-west-1";
      op = { vault = "My Vault"; item = "abc 123"; fields = { accessKeyId = "key id"; secretAccessKey = "key secret"; }; };
    };
    custom = { region = "sa-east-1"; output = "text"; credentialProcess = "/bin/fetch --x"; };
    sso = { region = "us-east-2"; settings.sso_session = "corp"; };
  }).config;
  both = (eval {
    bad = { region = "us-east-1"; credentialProcess = "x"; op = { vault = "v"; item = "i"; }; };
  }).config;
  s = good.programs.awscli.settings;
in
assert lib.attrNames s == [ "default" "profile custom" "profile sso" "profile work" ];
assert s.default == { region = "us-east-1"; output = "json"; };
assert s."profile custom" == { region = "sa-east-1"; output = "text"; credential_process = "/bin/fetch --x"; };
assert s."profile sso" == { region = "us-east-2"; output = "json"; sso_session = "corp"; };
assert lib.all (a: a.assertion) good.assertions;
assert !(lib.head both.assertions).assertion;
pkgs.runCommand "aws" { nativeBuildInputs = [ pkgs.jq pkgs.python3 ]; } ''
  set -euo pipefail
  expected='{"Version":1,"AccessKeyId":"AKIDEXAMPLE","SecretAccessKey":"s3cr\"et"}'
  [ "$(sh -c ${lib.escapeShellArg s."profile work".credential_process} | jq -c .)" = "$expected" ]
  python3 -c 'import shlex, subprocess, sys; sys.stdout.write(subprocess.check_output(shlex.split(sys.argv[1])).decode())' \
    ${lib.escapeShellArg s."profile work".credential_process} | jq -c . | grep -qxF "$expected"
  echo ok > $out
''
