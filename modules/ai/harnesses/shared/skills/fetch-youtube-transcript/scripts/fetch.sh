#!/usr/bin/env bash
# Fetch a YouTube video transcript as clean plain text via yt-dlp.
#
# Usage: fetch.sh <youtube-url> [sub-langs]
#   sub-langs  yt-dlp --sub-langs value (default: "pt.*,en.*")
#
# Output (stdout):
#   TITLE: <video title>
#   DURATION: <hh:mm:ss>
#   SUBTITLES: manual|auto (<lang>)
#   ---
#   <transcript, one caption line per row>
#
# Manual subtitles are preferred over auto-generated captions: creators'
# own subs have punctuation and correct technical terms; auto-captions
# mangle both. --no-playlist everywhere because course URLs often carry
# a &list= param and yt-dlp would otherwise iterate the whole playlist.
set -euo pipefail

url="${1:?usage: fetch.sh <youtube-url> [sub-langs]}"
langs="${2:-pt.*,en.*}"

command -v yt-dlp >/dev/null 2>&1 || { echo "ERROR: yt-dlp not found (brew install yt-dlp)" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq not found (brew install jq)" >&2; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

yt-dlp --no-playlist --skip-download --no-warnings \
  --print "TITLE: %(title)s" --print "DURATION: %(duration_string)s" "$url"

# Pick the downloaded sub file whose language best matches the request, honoring
# the order of the comma-separated --sub-langs patterns (pt before en by
# default). Replaces `find | head -1`, which returned an arbitrary language when
# several langs downloaded at once.
pick_sub() {
  local pat prefix f
  local -a pats
  IFS=',' read -ra pats <<< "$langs"
  for pat in "${pats[@]}"; do
    prefix="${pat%.\*}"           # 'pt.*' -> 'pt'; plain codes left untouched
    for f in "$tmp"/sub."$prefix"*.json3; do
      [[ -e "$f" ]] || continue
      printf '%s\n' "$f"
      return 0
    done
  done
  return 0
}

fetch_subs() { # $1: --write-subs | --write-auto-subs
  yt-dlp --no-playlist --skip-download --no-warnings "$1" \
    --sub-langs "$langs" --sub-format json3 \
    -o "$tmp/sub" "$url" >/dev/null 2>&1 || true
  pick_sub
}

kind="manual"
file="$(fetch_subs --write-subs)"
if [[ -z "$file" ]]; then
  kind="auto"
  file="$(fetch_subs --write-auto-subs)"
fi

if [[ -z "$file" ]]; then
  echo "ERROR: no subtitles available for $url (langs: $langs)" >&2
  exit 3
fi

lang="$(basename "$file" .json3)"
lang="${lang#sub.}"
echo "SUBTITLES: $kind ($lang)"
echo "---"

# json3 = list of caption events, each with utf8 text segments. Join the
# segments of each event into one line, drop blank/whitespace-only events.
jq -r '.events[] | select(.segs) | [.segs[].utf8] | join("")' "$file" \
  | sed -e 's/[[:space:]]\{1,\}/ /g' -e 's/^ //' -e 's/ $//' \
  | sed '/^$/d'
