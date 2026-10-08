#!/usr/bin/env bats
load helpers

setup() {
  setup_sandbox
  mkdir -p "$HOME/.ssh"
  printf 'keep these keys\n' > "$HOME/.ssh/authorized_keys"
  cp "$HOME/.ssh/authorized_keys" "$TEST_ROOT/original-keys"
}

assert_access_unchanged() {
  cmp "$TEST_ROOT/original-keys" "$HOME/.ssh/authorized_keys"
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/brew-attempted" ]
  [ ! -e "$HOME/.ssh/config" ]
}

use_real_python() {
  stub_command mise <<'SH'
#!/bin/sh
printf '%s\n' "$TEST_PYTHON"
SH
}

@test "missing mise fails without changing user access files" {
  run bash "$TEST_REPO/remote-login.sh" --check
  [ "$status" -eq 1 ]
  assert_access_unchanged
}

@test "locked interpreter lookup failure does not launch a command" {
  stub_command mise <<'SH'
#!/bin/sh
exit 37
SH
  run bash "$TEST_REPO/remote-login.sh" --check
  [ "$status" -eq 37 ]
  assert_access_unchanged
}

@test "selected executable runs and its failure status survives the launcher" {
  stub_command selected-python <<'SH'
#!/bin/sh
printf 'executed\n' > "$TEST_ROOT/selected-command-ran"
exit 42
SH
  stub_command mise <<'SH'
#!/bin/sh
printf '%s\n' "$TEST_BIN/selected-python"
SH
  run bash "$TEST_REPO/remote-login.sh" --check
  [ "$status" -eq 42 ]
  [ "$(cat "$TEST_ROOT/selected-command-ran")" = executed ]
  assert_access_unchanged
}

@test "real CLI is found from another directory and a repository path containing spaces" {
  use_real_python
  mv "$TEST_REPO" "$TEST_ROOT/repo with spaces"
  TEST_REPO="$TEST_ROOT/repo with spaces"
  mkdir "$TEST_ROOT/caller"
  cd "$TEST_ROOT/caller"
  run bash "$TEST_REPO/remote-login.sh" --help
  [ "$status" -eq 0 ]
  run bash "$TEST_REPO/remote-login.sh" --not-a-real-option
  [ "$status" -eq 2 ]
  assert_access_unchanged
}

@test "home-local mise fallback launches the real CLI outside the repository" {
  use_real_python
  mkdir -p "$HOME/.local/bin"
  mv "$TEST_BIN/mise" "$HOME/.local/bin/mise"
  cd "$HOME"
  run bash "$TEST_REPO/remote-login.sh" --help
  [ "$status" -eq 0 ]
  assert_access_unchanged
}

@test "relative configuration selects the caller file including mise original cwd" {
  [ "$EUID" -ne 0 ] || skip "real config loading requires a normal user"
  case "$(uname -s):$(uname -m)" in
    Darwin:arm64) ;;
    Linux:aarch64|Linux:arm64)
      [ -r /etc/os-release ] || skip "requires Ubuntu"
      . /etc/os-release
      [ "$ID" = ubuntu ] || skip "requires Ubuntu"
      ;;
    *) skip "real config loading requires an ARM64 Mac or Ubuntu host" ;;
  esac
  use_real_python
  mkdir "$TEST_ROOT/caller with spaces"
  # A test-only key is rejected with its name, which proves which local file was read without enabling access.
  printf 'remote_login_port = 2222\n' > "$TEST_ROOT/caller with spaces/local.toml"
  cd "$TEST_ROOT/caller with spaces"
  run bash "$TEST_REPO/remote-login.sh" --config local.toml --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"'remote_login_port' cannot be set"* ]]
  assert_access_unchanged
  cd "$TEST_REPO"
  run env MISE_ORIGINAL_CWD="$TEST_ROOT/caller with spaces" bash ./remote-login.sh --config local.toml --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"'remote_login_port' cannot be set"* ]]
  assert_access_unchanged
}
