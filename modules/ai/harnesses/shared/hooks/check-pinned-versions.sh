#!/usr/bin/env bash
# Block floating/unpinned versions in dependency manifests.
# Exit 2 blocks the action in Claude Code and Cursor; Antigravity CLI blocks
# on a {"decision":"deny"} reply instead. Its write tools put the new text in
# CodeContent or ReplacementContent; the other string arguments are the old
# text or the model's own prose, which must not count.
# Accepts Claude, Cursor and Antigravity CLI input shapes.
set -euo pipefail

INPUT=""
if [ ! -t 0 ]; then INPUT=$(cat); fi
[ -z "$INPUT" ] && exit 0

FILE=$(printf '%s' "$INPUT" | jq -r '(.tool_input.file_path // .file_path // .tool_input.path // .toolCall.args.TargetFile // empty)' 2>/dev/null || true)

case "${FILE##*/}" in
  package.json|requirements*.txt|pyproject.toml|Cargo.toml|Gemfile) ;;
  *) exit 0 ;;
esac

CONTENT=$(printf '%s' "$INPUT" | jq -r '
  if .toolCall then
    [.toolCall.args | .. | objects | (.CodeContent, .ReplacementContent) | strings] | join("\n")
  else (.tool_input.content // .tool_input.new_string // .content // .new_string // empty) end' 2>/dev/null || true)
[ -z "$CONTENT" ] && exit 0

if echo "$CONTENT" | grep -qE '["'\''][[:space:]]*[~^][0-9]|["'\''][[:space:]]*(latest|\*)["'\'']|[>~]=[[:space:]]*[0-9]|(^|[^=])>[[:space:]]*[0-9]'; then
  REASON="Floating version detected. Pin exact versions only (no ^, ~, >=, >, latest, or *)."
  if printf '%s' "$INPUT" | jq -e '.toolCall' >/dev/null 2>&1; then
    jq -cn --arg reason "$REASON" '{decision: "deny", reason: $reason}'
    exit 0
  fi
  echo "$REASON" >&2
  exit 2
fi
