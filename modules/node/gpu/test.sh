#!/usr/bin/env bash
# Drives gpu-allocate.pl against a stub `qm`, a stub `systemd-run` and throwaway
# configs. The stub records every call so the assertions pin the exact ones.
set -euo pipefail

hook=$1
fail=0
work=""
rc=0

setup() {
  work=$(mktemp -d)
  export GPU_ALLOCATE_CONF_DIR="$work/conf"
  export GPU_ALLOCATE_LOG="$work/log"
  export GPU_ALLOCATE_REPRIME="$work/reprime.sh"
  export GPU_ALLOCATE_FLAG_DIR="$work/run"
  export GPU_ALLOCATE_QM="$work/bin/qm"
  export QM_CALLS="$work/calls"
  export QM_STATE="$work/state"
  mkdir -p "$GPU_ALLOCATE_CONF_DIR" "$GPU_ALLOCATE_FLAG_DIR" "$QM_STATE" "$work/bin"
  : > "$QM_CALLS"
  PATH="$work/bin:$PATH"

  printf '#!%s\n' "$(command -v bash)" > "$GPU_ALLOCATE_QM"
  cat >> "$GPU_ALLOCATE_QM" <<'STUB'
echo "$*" >> "$QM_CALLS"
case "$1" in
  status)
    f="$QM_STATE/$2"
    s=stopped
    [ -f "$f" ] && s=$(cat "$f")
    echo "status: $s"
    ;;
  config)
    # As qm does: the main section with the pending block merged over it, and
    # no snapshot sections at all.
    perl -ne 'if (/^\[PENDING\]/) { $m=1; $p=1; next }
              if (/^\[/)          { $m=1; $p=0; next }
              print if !$m || $p' "$GPU_ALLOCATE_CONF_DIR/$2.conf" 2>/dev/null || true
    ;;
  set)
    if [ "$3" = "--delete" ] && [ "$4" = "hostpci0" ]; then
      sed -i '/^hostpci0:/d' "$GPU_ALLOCATE_CONF_DIR/$2.conf"
    fi
    ;;
esac
exit 0
STUB
  chmod +x "$GPU_ALLOCATE_QM"

  printf '#!%s\necho "$*" >> "$QM_CALLS.systemd-run"\nexit 0\n' "$(command -v bash)" > "$work/bin/systemd-run"
  chmod +x "$work/bin/systemd-run"
  : > "$QM_CALLS.systemd-run"
}

conf() { printf '%s\n' "$2" > "$GPU_ALLOCATE_CONF_DIR/$1.conf"; }
state() { printf '%s\n' "$2" > "$QM_STATE/$1"; }
snapshot() { for f in "$GPU_ALLOCATE_CONF_DIR"/*.conf; do printf '== %s\n' "$(basename "$f")"; cat "$f"; done; }

run() {
  rc=0
  perl "$hook" "$@" > "$work/out" 2>&1 || rc=$?
}

check() {
  if [ "$2" = "$3" ]; then
    printf '  ok   %s\n' "$1"
  else
    printf '  FAIL %s\n    want: %s\n    got:  %s\n' "$1" "$2" "$3" >&2
    fail=1
  fi
}

gpu_line='hostpci0: 0000:01:00,pcie=1,x-vga=1'

echo "the defaults the node runs with"
defaults=$(perl -ne 'print "$1=" . (defined $2 ? $2 : $3) . "\n"
  if /\$ENV\{(GPU_ALLOCATE_\w+)\}\s*\/\/\s*(?:"([^"]*)"|(\d+))\s*;/' "$hook")
check "every default pinned" "GPU_ALLOCATE_QM=/usr/sbin/qm
GPU_ALLOCATE_CONF_DIR=/etc/pve/qemu-server
GPU_ALLOCATE_LOG=/var/log/gpu-allocate.log
GPU_ALLOCATE_REPRIME=/var/lib/vz/snippets/gpu-reprime.sh
GPU_ALLOCATE_FLAG_DIR=/run" "$defaults"

echo "same-VM restart of 100"
setup
conf 100 "name: vm100
$gpu_line"
conf 101 "name: vm101"
before=$(snapshot)
run 100 pre-start
check "exit 0" "0" "$rc"
check "configs untouched" "$before" "$(snapshot)"
check "no config writes" "" "$(grep -E '^(set|shutdown) ' "$QM_CALLS" || true)"
check "no reprime scheduled" "0" "$(ls "$GPU_ALLOCATE_FLAG_DIR" | wc -l | tr -d ' ')"

echo "101 started while 100 holds the card"
setup
conf 100 "name: vm100
$gpu_line"
conf 101 "name: vm101"
run 101 pre-start
check "exit 0" "0" "$rc"
check "100 released the card" "" "$(grep '^hostpci0:' "$GPU_ALLOCATE_CONF_DIR/100.conf" || true)"
check "101 gets the x-vga line" "$gpu_line" "$(grep '^hostpci0:' "$GPU_ALLOCATE_CONF_DIR/101.conf")"
check "reprime scheduled for 101" "gpu-reprime-101" "$(ls "$GPU_ALLOCATE_FLAG_DIR")"

echo "100 started while 101 is running"
setup
conf 100 "name: vm100"
conf 101 "name: vm101
$gpu_line"
state 101 running
before=$(snapshot)
run 100 pre-start
check "exit 1" "1" "$rc"
check "configs byte-identical" "$before" "$(snapshot)"
check "no shutdown issued" "" "$(grep '^shutdown ' "$QM_CALLS" || true)"
check "no stop issued" "" "$(grep '^stop ' "$QM_CALLS" || true)"
check "no reprime scheduled" "0" "$(ls "$GPU_ALLOCATE_FLAG_DIR" | wc -l | tr -d ' ')"

for peer_state in paused suspended prelaunch; do
  echo "100 started while 101 is $peer_state"
  setup
  conf 100 "name: vm100"
  conf 101 "name: vm101
$gpu_line"
  state 101 "$peer_state"
  before=$(snapshot)
  run 100 pre-start
  check "exit 1" "1" "$rc"
  check "configs byte-identical" "$before" "$(snapshot)"
done

echo "the starting VM carries snapshot and pending sections"
setup
conf 100 "name: vm100
cores: 8
[PENDING]
memory: 4096
[snap1]
name: vm100
$gpu_line"
conf 101 "name: vm101
$gpu_line"
run 100 pre-start
check "exit 0" "0" "$rc"
check "the line lands in the main section" "name: vm100
cores: 8
$gpu_line
[PENDING]
memory: 4096
[snap1]
name: vm100
$gpu_line" "$(cat "$GPU_ALLOCATE_CONF_DIR/100.conf")"
check "no stray temp file" "100.conf 101.conf" "$(ls "$GPU_ALLOCATE_CONF_DIR" | tr '\n' ' ' | sed 's/ $//')"

echo "the starting VM holds the card only inside a snapshot"
setup
conf 100 "name: vm100
[snap1]
$gpu_line"
conf 101 "name: vm101"
run 100 pre-start
check "exit 0" "0" "$rc"
no_holder="same-VM boot (last='')"
check "the snapshot is not the record" "1" "$(grep -cF "$no_holder" "$GPU_ALLOCATE_LOG")"

echo "a peer's hostpci0 is a pending add"
setup
conf 100 "name: vm100"
conf 101 "name: vm101
[PENDING]
$gpu_line"
run 100 pre-start
check "exit 0" "0" "$rc"
check "the pending holder is released" "set 101 --delete hostpci0" "$(grep '^set ' "$QM_CALLS")"
check "reprime scheduled for 100" "gpu-reprime-100" "$(ls "$GPU_ALLOCATE_FLAG_DIR")"

echo "the config cannot be written"
setup
conf 100 "name: vm100"
conf 101 "name: vm101"
chmod 0555 "$GPU_ALLOCATE_CONF_DIR"
run 100 pre-start
chmod 0755 "$GPU_ALLOCATE_CONF_DIR"
check "exit 1" "1" "$rc"
check "the failure is an ABORT" "1" "$(grep -c 'ABORT: could not write hostpci0' "$GPU_ALLOCATE_LOG")"
check "it never claims success" "0" "$(grep -c 'assigned GPU' "$GPU_ALLOCATE_LOG" || true)"

echo "a peer holds the card only inside a snapshot"
setup
conf 100 "name: vm100"
conf 101 "name: vm101
[snap1]
$gpu_line"
run 100 pre-start
check "exit 0" "0" "$rc"
check "101 is not a holder" "" "$(grep '^set 101' "$QM_CALLS" || true)"
check "101 untouched" "name: vm101
[snap1]
$gpu_line" "$(cat "$GPU_ALLOCATE_CONF_DIR/101.conf")"
check "no reprime scheduled" "0" "$(ls "$GPU_ALLOCATE_FLAG_DIR" | wc -l | tr -d ' ')"

echo "pre-start clears a stale reprime flag"
setup
conf 100 "name: vm100
$gpu_line"
conf 101 "name: vm101"
touch "$GPU_ALLOCATE_FLAG_DIR/gpu-reprime-100"
run 100 pre-start
check "exit 0" "0" "$rc"
check "the stale flag is gone" "0" "$(ls "$GPU_ALLOCATE_FLAG_DIR" | wc -l | tr -d ' ')"

echo "post-start with a flag"
setup
conf 100 "name: vm100
$gpu_line"
touch "$GPU_ALLOCATE_FLAG_DIR/gpu-reprime-100"
run 100 post-start
check "exit 0" "0" "$rc"
check "the reprime was launched once" "1" "$(grep -c -- '--collect --unit=gpu-reprime-100-' "$QM_CALLS.systemd-run")"
check "it passes the vmid and the helper" "1" "$(grep -c -- "$GPU_ALLOCATE_REPRIME 100\$" "$QM_CALLS.systemd-run")"
check "the flag is consumed" "0" "$(ls "$GPU_ALLOCATE_FLAG_DIR" | wc -l | tr -d ' ')"

echo "post-start without a flag"
setup
conf 100 "name: vm100
$gpu_line"
run 100 post-start
check "exit 0" "0" "$rc"
check "nothing was launched" "0" "$(wc -l < "$QM_CALLS.systemd-run" | tr -d ' ')"

echo "a vmid outside the table"
setup
conf 100 "name: vm100
$gpu_line"
conf 101 "name: vm101"
conf 102 "name: something-else"
before=$(snapshot)
run 102 pre-start
check "exit 0" "0" "$rc"
check "configs untouched" "$before" "$(snapshot)"
check "no qm calls" "" "$(cat "$QM_CALLS")"

echo "a non-table VM carrying an unrelated hostpci0"
setup
conf 100 "name: vm100"
conf 101 "name: vm101"
conf 102 "name: something-else
hostpci0: 0000:02:00,pcie=1"
run 100 pre-start
check "exit 0" "0" "$rc"
check "102 not a phantom holder" "0" "$(ls "$GPU_ALLOCATE_FLAG_DIR" | wc -l | tr -d ' ')"
check "102 untouched" "name: something-else
hostpci0: 0000:02:00,pcie=1" "$(cat "$GPU_ALLOCATE_CONF_DIR/102.conf")"
check "102 never addressed" "" "$(grep ' 102' "$QM_CALLS" || true)"
check "100 holds the card" "$gpu_line" "$(grep '^hostpci0:' "$GPU_ALLOCATE_CONF_DIR/100.conf")"

[ "$fail" -eq 0 ] || { echo "gpu-allocate: failures above" >&2; exit 1; }
echo "gpu-allocate: all cases pass"
