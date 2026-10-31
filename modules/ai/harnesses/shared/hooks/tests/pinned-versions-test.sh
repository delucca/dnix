#!/usr/bin/env sh
set -u

test_dir=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
hook="${1:-$test_dir/../check-pinned-versions.sh}"

pass=0
fail=0
deny='{"decision":"deny","reason":"Floating version detected. Pin exact versions only (no ^, ~, >=, >, latest, or *)."}'

check() {
  name=$1 want_code=$2 want_out=$3 payload=$4
  out=$(printf '%s' "$payload" | bash "$hook" 2>/dev/null)
  code=$?
  if [ "$code" = "$want_code" ] && [ "$out" = "$want_out" ]; then
    pass=$((pass + 1))
    printf 'PASS: %s\n' "$name"
  else
    fail=$((fail + 1))
    printf 'FAIL: %s\n  expected: %s %s\n  actual:   %s %s\n' "$name" "$want_code" "$want_out" "$code" "$out"
  fi
}

check "claude write blocks a caret" 2 "" \
  '{"tool_input":{"file_path":"/r/package.json","content":"{\"a\":\"^1.2.3\"}"}}'
check "claude write passes a pin" 0 "" \
  '{"tool_input":{"file_path":"/r/package.json","content":"{\"a\":\"1.2.3\"}"}}'
check "claude ignores other files" 0 "" \
  '{"tool_input":{"file_path":"/r/a.ts","content":"\"^1\""}}'
check "agy write denies a tilde" 0 "$deny" \
  '{"toolCall":{"name":"write_to_file","args":{"TargetFile":"/r/package.json","CodeContent":"{\"a\":\"~1.2.3\"}"}}}'
check "agy write passes a pin" 0 "" \
  '{"toolCall":{"name":"write_to_file","args":{"TargetFile":"/r/package.json","CodeContent":"{\"a\":\"1.2.3\"}"}}}'
check "agy edit removing a caret passes" 0 "" \
  '{"toolCall":{"name":"replace_file_content","args":{"TargetFile":"/r/package.json","ReplacementChunks":[{"TargetContent":"\"a\": \"^1.2.3\"","ReplacementContent":"\"a\": \"1.2.3\""}]}}}'
check "agy edit adding a range denies" 0 "$deny" \
  '{"toolCall":{"name":"replace_file_content","args":{"TargetFile":"/r/package.json","ReplacementChunks":[{"TargetContent":"\"a\": \"1.2.3\"","ReplacementContent":"\"a\": \">=1.2.3\""}]}}}'
check "agy prose arguments do not count" 0 "" \
  '{"toolCall":{"name":"replace_file_content","args":{"TargetFile":"/r/package.json","Description":"bump to >= 2","Instruction":"use ^2 later","TargetContent":"\"a\": \"1.0.0\"","ReplacementContent":"\"a\": \"2.0.0\""}}}'
check "agy single replace adding a caret denies" 0 "$deny" \
  '{"toolCall":{"name":"replace_file_content","args":{"TargetFile":"/r/package.json","Description":"pin","TargetContent":"\"a\": \"1.0.0\"","ReplacementContent":"\"a\": \"^2.0.0\""}}}'
check "agy read is ignored" 0 "" \
  '{"toolCall":{"name":"view_file","args":{"AbsolutePath":"/r/package.json"}}}'

printf '%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
