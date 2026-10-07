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
    for step in unknown preflight; do
      run bash "$TEST_REPO/$entrypoint" --skip "$step"
      [ "$status" -eq 64 ]
      assert_no_host_effects
    done
    for option in --skip --config; do
      run bash "$TEST_REPO/$entrypoint" "$option"
      [ "$status" -eq 64 ]
      assert_no_host_effects
    done
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

@test "bootstrap-only launchers perform isolated user bootstrap without full setup or SSH replacement" {
  [ "$EUID" -ne 0 ] || skip "real CLI requires a normal user"
  # Real config loading is intentionally not monkeypatched on unsupported hosts.
  case "$(/usr/bin/uname -s):$(/usr/bin/uname -m)" in
    Darwin:arm64) ;;
    *) skip "real bootstrap integration requires an ARM64 Mac" ;;
  esac
  for script in "$TEST_REPO"/scripts/bootstrap-*.sh; do
    printf ':\n' > "$script"
  done
  printf 'mise_bin="$TEST_BIN/mise"\npython_bin="$TEST_PYTHON"\n' > "$TEST_REPO/scripts/bootstrap-mise.sh"
  stub_command mise <<'SH'
#!/bin/sh
exit 99
SH
  # Full setup must never be reached, even if its selected steps would be no-ops.
  printf '#!/bin/sh\ntouch "$TEST_ROOT/full-setup-attempted"\nexit 98\n' > "$TEST_REPO/scripts/with-sudo-askpass.sh"
  run bash "$TEST_REPO/install.sh" --bootstrap-only </dev/null
  [ "$status" -eq 0 ]
  [ -d "$HOME/.gnupg" ]
  [ -s "$HOME/.zshrc" ]
  [ ! -e "$TEST_ROOT/full-setup-attempted" ]
  cmp "$TEST_ROOT/original-ssh" "$HOME/.ssh/config"
  cp "$HOME/.zshrc" "$TEST_ROOT/first-zshrc"
  run bash "$TEST_REPO/new-mac.sh" --keep-ssh </dev/null
  [ "$status" -eq 0 ]
  cmp "$TEST_ROOT/first-zshrc" "$HOME/.zshrc"
  cmp "$TEST_ROOT/original-ssh" "$HOME/.ssh/config"
  [ ! -e "$TEST_ROOT/full-setup-attempted" ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/brew-attempted" ]
}
