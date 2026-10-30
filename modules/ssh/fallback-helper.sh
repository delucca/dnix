#!/usr/bin/env bash
# SSH Fallback Helper
# Tries local IP first (faster when on LAN), falls back to Tailscale hostname/IP
#
# Usage: ssh-fallback-helper.sh <tailscale_hostname> <local_ip> <port>
#
# Supports two transport backends:
#   1. nc (netcat) — preferred on macOS/Linux
#   2. Bash /dev/tcp — built-in fallback for environments without nc

set -e

if [[ -z "$1" || -z "$2" ]]; then
  echo "usage: ssh-fallback-helper.sh <tailscale_hostname> <local_ip> [port]" >&2
  exit 2
fi

TAILSCALE_HOST="$1"
LOCAL_IP="$2"
PORT="${3:-22}"

# Timeouts in seconds:
# - PROBE_TIMEOUT: how long we wait when deciding LAN vs Tailscale
# - CONNECT_TIMEOUT: how long we allow the ProxyCommand TCP connect to take
PROBE_TIMEOUT=2
CONNECT_TIMEOUT=10

_dbg() {
  [[ -n "${SSH_FALLBACK_DEBUG:-}" ]] && echo "ssh-fallback: $*" >&2
  return 0
}

# ---------------------------------------------------------------------------
# Transport backend selection
# ---------------------------------------------------------------------------
HAS_NC=false
NC_CONNECT_ARGS=()
NC_PROBE_ARGS=()

if command -v nc >/dev/null 2>&1; then
  HAS_NC=true
  # Determine the connect-timeout flag for this nc variant. The flag spelling
  # differs and, worse, *collides* across implementations:
  #   - nmap ncat:    -w <sec> is the connect timeout. -G means "source-route
  #                   hop pointer" (NOT a timeout) -- passing -G <sec> aborts
  #                   with "Invalid source-route hop pointer". Must use -w.
  #   - macOS/BSD nc: -G <sec> is the connect timeout; -w <sec> is total/idle.
  #   - OpenBSD/GNU:  -w <sec> covers connect + idle.
  # So detect ncat FIRST (its -G would otherwise match the macOS probe below).
  if nc --version 2>&1 | grep -qiE 'ncat|nmap'; then
    NC_CONNECT_ARGS=(-w "$CONNECT_TIMEOUT")
    NC_PROBE_ARGS=(-w "$PROBE_TIMEOUT")
  elif [ "$(uname -s)" = "Darwin" ] && nc -h 2>&1 | grep -qE '(^|[[:space:]])-G[[:space:]]'; then
    # Darwin-only on purpose: netcat-openbsd also lists -G in its help, but
    # there it is the source-route hop pointer. Linux always takes -w.
    NC_CONNECT_ARGS=(-G "$CONNECT_TIMEOUT")
    NC_PROBE_ARGS=(-G "$PROBE_TIMEOUT" -w "$PROBE_TIMEOUT")
  else
    NC_CONNECT_ARGS=(-w "$CONNECT_TIMEOUT")
    NC_PROBE_ARGS=(-w "$PROBE_TIMEOUT")
  fi
fi

# Bash /dev/tcp relay: bidirectionally pipes stdin/stdout through a TCP socket.
# Used as the exec transport when nc is unavailable.
_bash_tcp_relay() {
  local host="$1"
  local port="$2"
  exec 3<>/dev/tcp/"$host"/"$port"
  # Shovel data in both directions; when either side closes, the script exits.
  cat <&3 &
  local cat_pid=$!
  cat >&3
  kill "$cat_pid" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Probing helpers
# ---------------------------------------------------------------------------

# Test whether a TCP port is reachable.
_probe_port() {
  local host="$1"
  local port="$2"

  if $HAS_NC; then
    nc -z "${NC_PROBE_ARGS[@]}" "$host" "$port" 2>/dev/null
  else
    # /dev/tcp probe with timeout
    timeout "$PROBE_TIMEOUT" bash -c "echo >/dev/tcp/$host/$port" 2>/dev/null
  fi
}

# Test whether a TCP port responds with an SSH banner.
_probe_ssh_banner() {
  local host="$1"
  local port="$2"

  local prefix=""
  if $HAS_NC; then
    prefix="$( (nc "${NC_PROBE_ARGS[@]}" "$host" "$port" </dev/null 2>/dev/null || true) | LC_ALL=C head -c 4 )"
  else
    prefix="$( (timeout "$PROBE_TIMEOUT" bash -c 'exec 3</dev/tcp/'"$host"'/'"$port"'; LC_ALL=C head -c 4 <&3' 2>/dev/null) || true )"
  fi
  [[ "$prefix" == "SSH-" ]]
}

# Connect stdin/stdout to a remote host:port (used as ProxyCommand transport).
_connect() {
  local host="$1"
  local port="$2"

  if $HAS_NC; then
    exec nc "${NC_CONNECT_ARGS[@]}" "$host" "$port"
  else
    _bash_tcp_relay "$host" "$port"
  fi
}

# ---------------------------------------------------------------------------
# Optional: prefer a concrete Tailscale IP (avoids DNS weirdness)
# ---------------------------------------------------------------------------
TS_TARGET="$TAILSCALE_HOST"
if command -v tailscale >/dev/null 2>&1; then
  TS_IP="$(tailscale ip -4 "$TAILSCALE_HOST" 2>/dev/null | head -n 1 || true)"
  if [[ -n "${TS_IP:-}" ]]; then
    TS_TARGET="$TS_IP"
  fi
fi

# ---------------------------------------------------------------------------
# Main: try LAN first, fall back to Tailscale
# ---------------------------------------------------------------------------
if _probe_port "$LOCAL_IP" "$PORT"; then
  if _probe_ssh_banner "$LOCAL_IP" "$PORT"; then
    _dbg "using LAN $LOCAL_IP:$PORT"
    _connect "$LOCAL_IP" "$PORT"
  else
    _dbg "LAN $LOCAL_IP:$PORT open but not SSH; falling back"
  fi
else
  _dbg "LAN $LOCAL_IP:$PORT not reachable; falling back"
fi

_dbg "using Tailscale $TS_TARGET:$PORT"
_connect "$TS_TARGET" "$PORT"
