#!/usr/bin/env bash
# Update Homebrew packages, mise tools, npm and pnpm globals, Mac App Store
# apps and Ollama models. Each component runs even if an earlier one fails;
# the summary lists every result and the exit status is 1 on any failure.
set -uo pipefail

# Tools come from the shell's PATH, which the bootstrap shell files configure.
mise=${MISE_BIN:-mise}
results=()
failures=()

run() {
  local name=$1
  shift
  printf '==> %s\n' "$name"
  if "$@"; then
    results+=("$name: completed")
  else
    results+=("$name: failed")
    failures+=("$name")
  fi
}

skip() {
  printf '%s: skipped (%s)\n' "$1" "$2"
  results+=("$1: skipped")
}

if command -v brew >/dev/null 2>&1; then
  run "brew update" brew update
  export HOMEBREW_NO_AUTO_UPDATE=1
  run "brew upgrade" brew upgrade
  run "brew cleanup" brew cleanup -s
else
  for name in "brew update" "brew upgrade" "brew cleanup"; do skip "$name" "brew not found"; done
fi

if command -v "$mise" >/dev/null 2>&1; then
  run "mise upgrade" "$mise" upgrade --no-prune
  if "$mise" which npm >/dev/null 2>&1; then
    run "npm update" "$mise" exec -- npm update -g
  else
    skip "npm update" "npm is not installed by mise"
  fi
  if ! "$mise" which pnpm >/dev/null 2>&1; then
    skip "pnpm update" "pnpm is not installed by mise"
  elif [ -z "${PNPM_HOME:-}" ]; then
    skip "pnpm update" "PNPM_HOME is not set"
  else
    run "pnpm update" "$mise" exec -- pnpm update -g
  fi
else
  for name in "mise upgrade" "npm update" "pnpm update"; do skip "$name" "mise not found"; done
fi

if [ "$(uname -s)" != Darwin ]; then
  skip "mas upgrade" "not macOS"
elif command -v mas >/dev/null 2>&1; then
  run "mas upgrade" mas upgrade
else
  skip "mas upgrade" "mas not found"
fi

if command -v ollama >/dev/null 2>&1; then
  while read -r model _; do
    [ -n "$model" ] && run "ollama pull $model" ollama pull "$model"
  done < <(ollama list | tail -n +2)
else
  skip "ollama pull" "ollama not found"
fi

printf 'Update summary:\n'
printf '  %s\n' "${results[@]}"
[ "${#failures[@]}" -eq 0 ]
