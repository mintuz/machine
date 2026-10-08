#!/usr/bin/env bats
load helpers

setup() {
  setup_sandbox
  SCRIPT="$TEST_REPO/scripts/shell-block.sh"
  RC="$HOME/.testrc"
}

@test "adds the block once, keeping existing content" {
  printf 'export EXISTING=1\n' > "$RC"
  run bash "$SCRIPT" "$RC" "dev-machine test" 'eval "$(brew shellenv)"' 'alias ll="ls -l"'
  [ "$status" -eq 0 ]
  [ "$(head -n 1 "$RC")" = "export EXISTING=1" ]
  [ "$(grep -c '# BEGIN dev-machine test' "$RC")" -eq 1 ]
  grep -qxF 'eval "$(brew shellenv)"' "$RC"
  run bash "$SCRIPT" "$RC" "dev-machine test" 'eval "$(brew shellenv)"' 'alias ll="ls -l"'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ "$(grep -c '# BEGIN dev-machine test' "$RC")" -eq 1 ]
}

@test "creates a missing file" {
  run bash "$SCRIPT" "$RC" "dev-machine test" 'first line'
  [ "$status" -eq 0 ]
  [ "$(cat "$RC")" = "$(printf '# BEGIN dev-machine test\nfirst line\n# END dev-machine test')" ]
}

@test "replaces a changed block in place and keeps text after it" {
  printf 'before\n# BEGIN dev-machine test\nold line\n# END dev-machine test\nafter\n' > "$RC"
  run bash "$SCRIPT" "$RC" "dev-machine test" 'new line' 'second new line'
  [ "$status" -eq 0 ]
  [ "$(cat "$RC")" = "$(printf 'before\n# BEGIN dev-machine test\nnew line\nsecond new line\n# END dev-machine test\nafter')" ]
}

@test "leaves a symlinked file alone and says so" {
  printf 'external\n' > "$TEST_ROOT/external-rc"
  ln -s "$TEST_ROOT/external-rc" "$RC"
  run bash "$SCRIPT" "$RC" "dev-machine test" 'ignored'
  [ "$status" -eq 0 ]
  [[ "$output" == *"symlink"* ]]
  [ "$(cat "$TEST_ROOT/external-rc")" = "external" ]
  [ -L "$RC" ]
}
