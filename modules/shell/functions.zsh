up() {
  local arg="${1:-1}" target

  if [[ $arg == <-> ]]; then
    target=""
    repeat "$arg" target+="../"
    cd "${target:-.}" || return
    return
  fi

  target="$PWD"
  while [[ $target != / ]]; do
    target="${target:h}"
    if [[ ${target:t} == ${arg}* ]]; then
      cd "$target" || return
      return
    fi
  done

  echo "up: no ancestor matching '$arg'" >&2
  return 1
}
