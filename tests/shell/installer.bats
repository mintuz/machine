#!/usr/bin/env bats
load helpers

setup() {
  setup_sandbox
  # new-mac.sh rejects non-Mac hosts before parsing; simulate its supported host.
  stub_command uname <<'SH'
#!/bin/sh
case "$1" in
  -s) printf 'Darwin\n' ;;
  -m) printf 'arm64\n' ;;
esac
SH
  mkdir -p "$HOME/.ssh"
  printf 'existing SSH configuration\n' > "$HOME/.ssh/config"
  cp "$HOME/.ssh/config" "$TEST_ROOT/original-ssh"
}

assert_no_host_effects() {
  [ ! -e "$TEST_ROOT/bootstrap-attempted" ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/brew-attempted" ]
  [ ! -e "$HOME/.gnupg" ]
  cmp "$TEST_ROOT/original-ssh" "$HOME/.ssh/config"
}

@test "invalid and conflicting profiles stop before bootstrap" {
  for entrypoint in install.sh new-mac.sh; do
    run bash "$TEST_REPO/$entrypoint" invalid
    [ "$status" -eq 64 ]
    assert_no_host_effects
    run env DEVSETUP_PROFILE=invalid bash "$TEST_REPO/$entrypoint"
    [ "$status" -eq 64 ]
    assert_no_host_effects
  done
  for pair in 'personal work' 'work personal'; do
    read -r requested inherited <<< "$pair"
    run env DEVSETUP_PROFILE="$inherited" bash "$TEST_REPO/install.sh" "$requested"
    [ "$status" -eq 64 ]
    assert_no_host_effects
  done
  run bash "$TEST_REPO/install.sh" personal work
  [ "$status" -eq 64 ]
  assert_no_host_effects
}

@test "contradictory feature selections cannot silently provision" {
  for entrypoint in install.sh new-mac.sh; do
    run bash "$TEST_REPO/$entrypoint" --keep-ssh --1password-ssh
    [ "$status" -eq 64 ]
    assert_no_host_effects
    run bash "$TEST_REPO/$entrypoint" --dotfiles --skip-dotfiles
    [ "$status" -eq 64 ]
    assert_no_host_effects
    run bash "$TEST_REPO/$entrypoint" --skip ssh --1password-ssh
    [ "$status" -eq 64 ]
    assert_no_host_effects
    run bash "$TEST_REPO/$entrypoint" --skip dotfiles --dotfiles
    [ "$status" -eq 64 ]
    assert_no_host_effects
  done
}

@test "unknown or mandatory skips and missing option values are refused" {
  for entrypoint in install.sh new-mac.sh; do
    for step in unknown preflight git fzf dock remote-login; do
      run bash "$TEST_REPO/$entrypoint" --skip "$step"
      [ "$status" -eq 64 ]
      assert_no_host_effects
    done
    run bash "$TEST_REPO/$entrypoint" --skip
    [ "$status" -eq 64 ]
    assert_no_host_effects
  done
}

@test "unsupported operating systems and Mac architectures stop before bootstrap" {
  [ "$EUID" -ne 0 ] || skip "installer refuses root before platform detection"
  stub_command uname <<'SH'
#!/bin/sh
case "$1" in
  -s) printf '%s\n' "$TEST_SYSTEM" ;;
  -m) printf '%s\n' "$TEST_MACHINE" ;;
esac
SH
  for entrypoint in install.sh new-mac.sh; do
    run env TEST_SYSTEM=FreeBSD TEST_MACHINE=arm64 bash "$TEST_REPO/$entrypoint" --keep-ssh
    [ "$status" -eq 1 ]
    assert_no_host_effects
    run env TEST_SYSTEM=Darwin TEST_MACHINE=x86_64 bash "$TEST_REPO/$entrypoint" --keep-ssh
    [ "$status" -eq 1 ]
    assert_no_host_effects
  done
}

@test "bootstrap-only launchers apply the user parts only, without full setup or SSH replacement" {
  for script in "$TEST_REPO"/scripts/bootstrap-*.sh; do
    printf ':\n' > "$script"
  done
  printf 'mise_bin="$TEST_BIN/mise"\n' > "$TEST_REPO/scripts/bootstrap-mise.sh"
  stub_command mise <<'SH'
#!/bin/sh
echo "$*" >> "$TEST_ROOT/mise-calls"
SH
  printf '#!/bin/sh\nexec "$@"\n' > "$TEST_REPO/scripts/with-sudo-askpass.sh"
  run bash "$TEST_REPO/install.sh" --bootstrap-only --1password-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(cat "$TEST_ROOT/mise-calls")" = "-E personal bootstrap --only files,user --yes" ]
  cmp "$TEST_ROOT/original-ssh" "$HOME/.ssh/config"
  rm "$TEST_ROOT/mise-calls"
  run env DEVSETUP_PROFILE=work bash "$TEST_REPO/new-mac.sh" --keep-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(cat "$TEST_ROOT/mise-calls")" = "-E work bootstrap --only files,user --yes" ]
  cmp "$TEST_ROOT/original-ssh" "$HOME/.ssh/config"
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/brew-attempted" ]
}
