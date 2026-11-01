#!/usr/bin/env bash
# Drives push-secrets.sh with ssh and remote running locally and a fake
# renderer that writes a sentinel, which must reach the files and never the
# script's output.
set -euo pipefail

body=$1
fail=0
work=""
rc=0
sentinel=s3ntinel-value

setup() {
  work=$(mktemp -d)
  mkdir -p "$work/bin" "$work/tmp"
  export TMPDIR="$work/tmp"
  export PATH="$work/bin:$PATH"
  printf '#!%s\nshift\nexec bash -c "$*"\n' "$(command -v bash)" > "$work/bin/ssh"
  chmod +x "$work/bin/ssh"
  local owner group
  owner=$(id -un)
  group=$(id -gn)
  cat > "$work/secrets.json" <<JSON
{
  "alpha": { "template": "password = {{ op://Vault/alpha/password }}", "owner": "$owner", "group": "$group", "mode": "0400", "path": "$work/dir/alpha" },
  "beta": { "template": "{{ op://Vault/beta/key }}", "owner": "$owner", "group": "$group", "mode": "0440", "path": "$work/dir/beta" }
}
JSON
}

run() {
  cat > "$work/script" <<PREAMBLE
set -euo pipefail
secrets_dir=$work/dir
secrets_json=$work/secrets.json
ssh_target=host
remote() { bash -c "\$1"; }
render() { $1; }
PREAMBLE
  cat "$body" >> "$work/script"
  rc=0
  bash "$work/script" > "$work/out" 2>&1 || rc=$?
}

check() {
  if [ "$2" = "$3" ]; then
    printf '  ok   %s\n' "$1"
  else
    printf '  FAIL %s\n    want: %s\n    got:  %s\n' "$1" "$2" "$3" >&2
    fail=1
  fi
}

mode() { stat -c %a "$1" 2>/dev/null || stat -f %Lp "$1"; }
renderer="sed -E 's/\\{\\{ *op:[^ ]+ *\\}\\}/$sentinel/g'"

echo "a fresh host gets every file"
setup
run "$renderer"
check "exit 0" "0" "$rc"
check "alpha rendered" "password = $sentinel" "$(cat "$work/dir/alpha")"
check "alpha mode" "400" "$(mode "$work/dir/alpha")"
check "beta mode" "440" "$(mode "$work/dir/beta")"
check "dir mode" "700" "$(mode "$work/dir")"
check "it says what it pushed" "secrets: pushed alpha beta" "$(cat "$work/out")"
check "no staged file left" "" "$(ls -A "$work/tmp")"

echo "a host with every file is left alone"
chmod 600 "$work/dir/alpha"; echo old > "$work/dir/alpha"
run "false"
check "exit 0 without rendering" "0" "$rc"
check "alpha untouched" "old" "$(cat "$work/dir/alpha")"
check "silent" "" "$(cat "$work/out")"

echo "refresh re-renders every file"
DNIX_SECRETS_REFRESH=1 run "$renderer"
check "exit 0" "0" "$rc"
check "alpha re-rendered" "password = $sentinel" "$(cat "$work/dir/alpha")"

echo "an undeclared file is removed"
touch "$work/dir/stale"
run "$renderer"
check "stale gone" "no" "$([ -e "$work/dir/stale" ] && echo yes || echo no)"
check "it says so" "secrets: removed undeclared stale" "$(cat "$work/out")"

echo "a failed render stops before anything is installed"
setup
run "false"
check "exit 1" "1" "$rc"
check "nothing installed" "no" "$([ -e "$work/dir/alpha" ] && echo yes || echo no)"
check "it says which" "secrets: could not render alpha; nothing was activated" "$(cat "$work/out")"
check "no staged file left" "" "$(ls -A "$work/tmp")"

echo "an empty render is refused"
setup
run "cat /dev/null"
check "exit 1" "1" "$rc"
check "nothing installed" "no" "$([ -e "$work/dir/alpha" ] && echo yes || echo no)"
check "no staged file left" "" "$(ls -A "$work/tmp")"

echo "the value never reaches the output"
setup
run "$renderer"
check "no sentinel in output" "0" "$(grep -c "$sentinel" "$work/out" || true)"

exit "$fail"
