# Pushes the host's declared dnix.secrets files before activation: the missing
# ones, or all of them with DNIX_SECRETS_REFRESH=1. The preamble sets
# secrets_dir, secrets_json, ssh_target and defines render (template on stdin,
# file on stdout) and remote (runs its one argument as root on the host).
# Values only travel through pipes: never argv, a variable or stdout.

declared=$(jq -r 'keys[]' "$secrets_json")
existing=$(remote "mkdir -p -m 0700 $secrets_dir && ls -1A $secrets_dir")
pushed=()

for name in $declared; do
  if [ -z "${DNIX_SECRETS_REFRESH:-}" ] && grep -qxF "$name" <<<"$existing"; then
    continue
  fi
  field() { jq -j --arg n "$name" --arg f "$1" '.[$n][$f]' "$secrets_json"; }
  path=$(field path)
  staged=$(ssh "$ssh_target" 'umask 077; mktemp')
  if ! field template | render | ssh "$ssh_target" "cat > $staged"; then
    ssh "$ssh_target" "rm -f $staged"
    echo "secrets: could not render $name; nothing was activated" >&2
    exit 1
  fi
  if ! remote "test -s $staged && install -o $(field owner) -g $(field group) -m $(field mode) $staged $path.new && mv -f $path.new $path; rc=\$?; rm -f $staged; exit \$rc"; then
    echo "secrets: could not install $name (empty render?); nothing was activated" >&2
    exit 1
  fi
  pushed+=("$name")
done

for name in $existing; do
  grep -qxF "$name" <<<"$declared" || { remote "rm -f $secrets_dir/$name"; echo "secrets: removed undeclared $name"; }
done

if [ ${#pushed[@]} -gt 0 ]; then echo "secrets: pushed ${pushed[*]}"; fi
