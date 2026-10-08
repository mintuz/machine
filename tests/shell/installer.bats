#!/usr/bin/env bats
load helpers

setup() {
  setup_sandbox
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
  RECORD="$MISE_CONFIG_DIR/miserc.local.toml"
}

assert_no_host_effects() {
  [ ! -e "$TEST_ROOT/bootstrap-attempted" ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/brew-attempted" ]
  [ ! -e "$HOME/.gnupg" ]
  [ ! -e "$RECORD" ]
  cmp "$TEST_ROOT/original-ssh" "$HOME/.ssh/config"
}

# Replace the bootstrap helpers with no-ops and record every mise call.
fake_bootstrap() {
  for script in "$TEST_REPO"/scripts/bootstrap-*.sh; do
    printf ':\n' > "$script"
  done
  printf 'mise_bin="$TEST_BIN/mise"\n' > "$TEST_REPO/scripts/bootstrap-mise.sh"
  stub_command mise <<'SH'
#!/bin/sh
echo "$*" >> "$TEST_ROOT/mise-calls"
echo "skip=${DEV_MACHINE_SKIP:-}" >> "$TEST_ROOT/mise-env"
SH
  printf '#!/bin/sh\nexec "$@"\n' > "$TEST_REPO/scripts/with-sudo-askpass.sh"
}

last_mise_call() {
  tail -n 1 "$TEST_ROOT/mise-calls"
}

@test "invalid and conflicting profiles stop before bootstrap" {
  run bash "$TEST_REPO/install.sh" invalid
  [ "$status" -eq 64 ]
  assert_no_host_effects
  run env DEVSETUP_PROFILE=invalid bash "$TEST_REPO/install.sh"
  [ "$status" -eq 64 ]
  assert_no_host_effects
  for pair in 'personal work' 'work personal'; do
    read -r requested inherited <<< "$pair"
    run env DEVSETUP_PROFILE="$inherited" bash "$TEST_REPO/install.sh" "$requested"
    [ "$status" -eq 64 ]
    assert_no_host_effects
  done
  run bash "$TEST_REPO/install.sh" personal work
  [ "$status" -eq 64 ]
  assert_no_host_effects
  run bash "$TEST_REPO/install.sh" work --bootstrap-only
  [ "$status" -eq 64 ]
  assert_no_host_effects
}

@test "full setup without a recorded profile requires the profile argument" {
  run bash "$TEST_REPO/install.sh" --keep-ssh
  [ "$status" -eq 64 ]
  [[ "$output" == *"no recorded profile"* ]]
  assert_no_host_effects
}

@test "contradictory feature selections cannot silently provision" {
  run bash "$TEST_REPO/install.sh" personal --keep-ssh --1password-ssh
  [ "$status" -eq 64 ]
  assert_no_host_effects
  run bash "$TEST_REPO/install.sh" personal --dotfiles --skip-dotfiles
  [ "$status" -eq 64 ]
  assert_no_host_effects
}

@test "unknown skip names and missing option values are refused with the valid list" {
  for name in unknown ssh git fzf dock remote-login cli osx zsh
  do
    run bash "$TEST_REPO/install.sh" personal --skip "$name"
    [ "$status" -eq 64 ]
    [[ "$output" == *"packages, "*"macos-defaults, "*"final-hook"* ]]
    assert_no_host_effects
  done
  run bash "$TEST_REPO/install.sh" personal --skip "packages,nosuchpart"
  [ "$status" -eq 64 ]
  assert_no_host_effects
  run bash "$TEST_REPO/install.sh" personal --skip
  [ "$status" -eq 64 ]
  assert_no_host_effects
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
  run env TEST_SYSTEM=FreeBSD TEST_MACHINE=arm64 bash "$TEST_REPO/install.sh" personal --keep-ssh
  [ "$status" -eq 1 ]
  assert_no_host_effects
  run env TEST_SYSTEM=Darwin TEST_MACHINE=x86_64 bash "$TEST_REPO/install.sh" personal --keep-ssh
  [ "$status" -eq 1 ]
  assert_no_host_effects
}

@test "bootstrap-only applies the user parts only, without full setup, SSH replacement or a record" {
  fake_bootstrap
  run bash "$TEST_REPO/install.sh" --bootstrap-only --1password-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(last_mise_call)" = "-E personal bootstrap --only files,user --yes" ]
  cmp "$TEST_ROOT/original-ssh" "$HOME/.ssh/config"
  [ ! -e "$RECORD" ]
  run env DEVSETUP_PROFILE=work bash "$TEST_REPO/install.sh" --bootstrap-only --keep-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(last_mise_call)" = "-E work bootstrap --only files,user --yes" ]
  [ ! -e "$RECORD" ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/brew-attempted" ]
}

@test "the profile argument is recorded once and later runs reuse it" {
  fake_bootstrap
  run bash "$TEST_REPO/install.sh" work --keep-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(cat "$RECORD")" = 'env = ["work"]' ]
  [ "$(last_mise_call)" = "-E work bootstrap --yes" ]
  run bash "$TEST_REPO/install.sh" --keep-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(cat "$RECORD")" = 'env = ["work"]' ]
  [ "$(last_mise_call)" = "-E work bootstrap --yes" ]
  # DEVSETUP_PROFILE wins for one run and is not recorded.
  run env DEVSETUP_PROFILE=personal bash "$TEST_REPO/install.sh" --keep-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(cat "$RECORD")" = 'env = ["work"]' ]
  [ "$(last_mise_call)" = "-E personal bootstrap --yes" ]
  # A new argument replaces only the env line of the user's file.
  printf 'auto_env = true\nenv = ["work"]\nenv_conf_d = true\n' > "$RECORD"
  run bash "$TEST_REPO/install.sh" personal --keep-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(cat "$RECORD")" = "$(printf 'auto_env = true\nenv = ["personal"]\nenv_conf_d = true')" ]
  [ "$(last_mise_call)" = "-E personal bootstrap --yes" ]
}

@test "skips pass mise parts through and translate gui and app-store for the hooks" {
  fake_bootstrap
  run bash "$TEST_REPO/install.sh" personal --keep-ssh --skip packages,tools --skip macos-defaults </dev/null
  [ "$status" -eq 0 ]
  [ "$(last_mise_call)" = "-E personal bootstrap --yes --skip packages,tools,macos-defaults" ]
  [ "$(tail -n 1 "$TEST_ROOT/mise-env")" = "skip=" ]
  run bash "$TEST_REPO/install.sh" personal --keep-ssh --skip gui --skip app-store --skip-dotfiles </dev/null
  [ "$status" -eq 0 ]
  [[ "$output" == *"DEV_MACHINE_SKIP=gui,app-store"* ]]
  [ "$(last_mise_call)" = "-E personal bootstrap --yes --skip repos,task" ]
  [ "$(tail -n 1 "$TEST_ROOT/mise-env")" = "skip=gui,app-store" ]
  run bash "$TEST_REPO/install.sh" personal --1password-ssh </dev/null
  [ "$status" -eq 0 ]
  [ "$(last_mise_call)" = "-E personal,ssh bootstrap --yes" ]
  grep -q "^dot track --yes $HOME/.ssh/config$" "$TEST_ROOT/mise-calls"
}
