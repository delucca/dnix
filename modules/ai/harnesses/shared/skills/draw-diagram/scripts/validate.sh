#!/usr/bin/env bash
# Validate (and optionally render) a Mermaid diagram with mermaid-cli (mmdc).
#
# Usage:
#   validate.sh INPUT.mmd                 # validate only (render to temp, discard)
#   validate.sh --png OUT.png INPUT.mmd   # validate AND save a PNG you can view
#
# Exit codes:
#   0  diagram parses (PNG written if --png given)
#   1  parse/render error — details printed to stderr
#   2  mmdc not installed — validation skipped (NOT a failure; fall back to a
#      manual pass over the syntax-safety checklist)
set -uo pipefail

png_out=""
input=""
while [ $# -gt 0 ]; do
  case "$1" in
    # Guard the shift: when --png is the last arg, `shift 2` with $#=1 does not
    # shift at all (returns non-zero, leaves $@ unchanged), and without `set -e`
    # the loop re-reads --png forever, pegging a CPU core.
    --png)
      [ $# -ge 2 ] || { echo "validate.sh: --png requires a value" >&2; exit 1; }
      png_out="$2"; shift 2 ;;
    -h|--help)
      echo "usage: validate.sh [--png OUT.png] INPUT.mmd"; exit 0 ;;
    *) input="$1"; shift ;;
  esac
done

if [ -z "$input" ] || [ ! -f "$input" ]; then
  echo "validate.sh: missing or unreadable input .mmd file: '${input:-}'" >&2
  exit 1
fi

# Resolve a renderer. Prefer an installed mmdc; never auto-download silently.
# Opt into npx (which may fetch the package) with MERMAID_USE_NPX=1.
if command -v mmdc >/dev/null 2>&1; then
  runner=(mmdc)
elif command -v npx >/dev/null 2>&1 && [ "${MERMAID_USE_NPX:-0}" = "1" ]; then
  runner=(npx -y @mermaid-js/mermaid-cli)
else
  echo "validate.sh: mmdc not found — skipping validation." >&2
  echo "  install: npm install -g @mermaid-js/mermaid-cli   (or set MERMAID_USE_NPX=1)" >&2
  exit 2
fi

# --no-sandbox lets headless Chrome run in containers / devpods / CI.
puppet_cfg="$(mktemp "${TMPDIR:-/tmp}/draw-diagram-puppeteer.XXXXXX.json")"
printf '{ "args": ["--no-sandbox", "--disable-setuid-sandbox"] }\n' >"$puppet_cfg"

if [ -n "$png_out" ]; then out="$png_out"; else out="$(mktemp "${TMPDIR:-/tmp}/draw-diagram-out.XXXXXX.svg")"; fi
err="$(mktemp "${TMPDIR:-/tmp}/draw-diagram-err.XXXXXX.log")"

args=(-q --puppeteerConfigFile "$puppet_cfg" -i "$input" -o "$out")
[ -n "$png_out" ] && args+=(-s 2 -b white)

if "${runner[@]}" "${args[@]}" 2>"$err"; then
  status=0
  if [ -n "$png_out" ]; then echo "valid — PNG written to $png_out"; else echo "valid"; rm -f "$out"; fi
else
  status=1
  echo "INVALID — mermaid failed to parse/render:" >&2
  cat "$err" >&2
fi

rm -f "$puppet_cfg" "$err"
# Validate-only runs render to a throwaway SVG that mktemp already created; the
# success branch removed it, but the failure branch did not — drop it here so a
# parse error doesn't leak a temp file each run.
[ -z "$png_out" ] && rm -f "$out"
exit "$status"
