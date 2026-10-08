#!/usr/bin/env bats
load helpers

setup() {
  setup_sandbox
  # The sandbox PATH holds only TEST_BIN and the system directories, so the
  # fakes below are the only brew, mise, mas and ollama the script can reach.
  LOG="$TEST_ROOT/calls.log"
  export LOG PNPM_HOME="$HOME/.local/share/pnpm" MISE_BIN="$TEST_BIN/mise"
  : > "$TEST_ROOT/has-npm"
  : > "$TEST_ROOT/has-pnpm"
  for tool in brew mas npm pnpm; do
    stub_command "$tool" <<'SH'
#!/bin/sh
printf '%s %s\n' "$(basename "$0")" "$*" >> "$LOG"
SH
  done
  stub_command mise <<'SH'
#!/bin/sh
printf 'mise %s\n' "$*" >> "$LOG"
case "$1:$2" in
  which:npm) [ -e "$TEST_ROOT/has-npm" ] ;;
  which:pnpm) [ -e "$TEST_ROOT/has-pnpm" ] ;;
  exec:--) shift 2; "$@" ;;
esac
SH
  stub_command ollama <<'SH'
#!/bin/sh
printf 'ollama %s\n' "$*" >> "$LOG"
[ "$1" != list ] || printf 'NAME ID SIZE\nllama3:latest abc 4GB\nqwen:7b def 5GB\n'
SH
  stub_command uname <<'SH'
#!/bin/sh
printf '%s\n' "${FAKE_UNAME:-Darwin}"
SH
}

assert_no_host_effects() {
  [ ! -e "$TEST_ROOT/bootstrap-attempted" ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
}

@test "every component runs and the summary reports completed" {
  run bash "$TEST_REPO/scripts/update.sh"
  [ "$status" -eq 0 ]
  grep -q '^brew update$' "$LOG"
  grep -q '^brew upgrade$' "$LOG"
  grep -q '^brew cleanup' "$LOG"
  grep -q '^mise upgrade' "$LOG"
  grep -q '^npm update -g$' "$LOG"
  grep -q '^pnpm update -g$' "$LOG"
  grep -q '^mas upgrade$' "$LOG"
  grep -q '^ollama pull llama3:latest$' "$LOG"
  grep -q '^ollama pull qwen:7b$' "$LOG"
  ! grep -q 'ollama pull NAME' "$LOG"
  [[ "$output" == *"Update summary:"* ]]
  [[ "$output" != *"failed"* ]]
  [[ "$output" != *"skipped"* ]]
  [[ "$output" == *"  ollama pull qwen:7b: completed"* ]]
  assert_no_host_effects
}

@test "a failing component does not stop later components and exits 1" {
  stub_command brew <<'SH'
#!/bin/sh
printf 'brew %s\n' "$*" >> "$LOG"
[ "$1" != upgrade ]
SH
  run bash "$TEST_REPO/scripts/update.sh"
  [ "$status" -eq 1 ]
  grep -q '^brew cleanup' "$LOG"
  grep -q '^mise upgrade' "$LOG"
  grep -q '^mas upgrade$' "$LOG"
  grep -q '^ollama pull' "$LOG"
  [[ "$output" == *"  brew upgrade: failed"* ]]
  [[ "$output" == *"  brew cleanup: completed"* ]]
  assert_no_host_effects
}

@test "missing tools are reported as skipped, not failed" {
  rm "$TEST_BIN/ollama" "$TEST_BIN/mas" "$TEST_ROOT/has-npm"
  unset PNPM_HOME
  run bash "$TEST_REPO/scripts/update.sh"
  [ "$status" -eq 0 ]
  ! grep -q '^npm update' "$LOG"
  ! grep -q '^pnpm update' "$LOG"
  [[ "$output" == *"pnpm update: skipped (PNPM_HOME is not set)"* ]]
  [[ "$output" == *"  npm update: skipped"* ]]
  [[ "$output" == *"  mas upgrade: skipped"* ]]
  [[ "$output" == *"  ollama pull: skipped"* ]]
  [[ "$output" != *"failed"* ]]
  assert_no_host_effects
}

@test "mas is skipped on non-Darwin hosts" {
  export FAKE_UNAME=Linux
  run bash "$TEST_REPO/scripts/update.sh"
  [ "$status" -eq 0 ]
  ! grep -q '^mas' "$LOG"
  [[ "$output" == *"mas upgrade: skipped (not macOS)"* ]]
  assert_no_host_effects
}
