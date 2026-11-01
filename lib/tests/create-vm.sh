#!/usr/bin/env bash
# Drives create-vm.sh's refusal paths. The `node` helper is the seam: stubbing
# the secret reader, ssh, sudo and qm runs the real script body locally, with
# the preamble estateScripts renders written here.
set -euo pipefail

body=$1
fail=0
work=""
rc=0

setup() {
  work=$(mktemp -d)
  mkdir -p "$work/bin" "$work/staging"
  export PATH="$work/bin:$PATH"
  export QM_CALLS="$work/calls"
  export QM_EXISTS=""
  export QM_NAME=""
  : > "$QM_CALLS"

  local shell
  shell=$(command -v bash)

  printf '#!%s\nwhile [ "$1" = "-o" ]; do shift 2; done\nshift\nexec bash -c "$*"\n' "$shell" > "$work/bin/ssh"
  printf '#!%s\nread -r _ || true\nshift 3\nexec "$@"\n' "$shell" > "$work/bin/sudo"
  cat > "$work/bin/qm" <<STUB
#!$shell
echo "\$*" >> "\$QM_CALLS"
case "\$1" in
  status) [ -n "\$QM_EXISTS" ] || exit 2 ;;
  config) echo "name: \$QM_NAME" ;;
esac
exit 0
STUB
  chmod +x "$work/bin"/*

  cat > "$work/script" <<PREAMBLE
read_secret() { echo fake-sudo-password; }
host=testvm
node_ssh=pve
sudo_ref=op://Vault/fake/password
secrets=hosts/pve/guests/secrets/testvm.yaml
vmid=199
cores=16
memory=57344
rootfs=local-lvm:64
hwaddr=BC:24:11:4C:9D:67
description='testvm - a test guest'
image=nixos-dnix.qcow2
staging=$work/staging
extra_disks=(local-lvm:320)
PREAMBLE
  cat "$body" >> "$work/script"
}

run() {
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

echo "vmid exists but belongs to another guest"
setup
export QM_EXISTS=yes QM_NAME=other
run
check "exit 1" "1" "$rc"
check "it says which vmid" "vmid 199 on pve is not testvm" "$(cat "$work/out")"
check "nothing was created" "" "$(grep -E '^(create|set|resize|start) ' "$QM_CALLS" || true)"

echo "vmid exists and is this guest"
setup
export QM_EXISTS=yes QM_NAME=testvm
run
check "it does not refuse" "0" "$(grep -c 'is not testvm' "$work/out" || true)"
check "nothing was created" "" "$(grep -E '^(create|set) ' "$QM_CALLS" || true)"

echo "vmid absent and no image staged"
setup
run
check "exit 1" "1" "$rc"
check "it points at the image app" "no nixos-dnix.qcow2 on pve: nix run .#vm-image" "$(cat "$work/out")"
check "nothing was created" "" "$(grep -E '^(create|set) ' "$QM_CALLS" || true)"

[ "$fail" -eq 0 ] || { echo "create-vm: failures above" >&2; exit 1; }
echo "create-vm: all cases pass"
