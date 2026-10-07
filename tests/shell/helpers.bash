setup_sandbox() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  TEST_ROOT="$BATS_TEST_TMPDIR/sandbox"
  TEST_BIN="$TEST_ROOT/bin"
  TEST_REPO="$TEST_ROOT/repo"
  TEST_PYTHON="${DEVSETUP_TEST_PYTHON:-$(command -v python3)}"
  export REPO_ROOT TEST_ROOT TEST_BIN TEST_REPO TEST_PYTHON
  export HOME="$TEST_ROOT/home" TMPDIR="$TEST_ROOT/tmp"
  mkdir -p "$TEST_BIN" "$TEST_REPO" "$HOME" "$TMPDIR"
  export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share"
  export XDG_CACHE_HOME="$HOME/.cache"
  export MISE_CONFIG_DIR="$XDG_CONFIG_HOME/mise" MISE_DATA_DIR="$XDG_DATA_HOME/mise"
  export MISE_CACHE_DIR="$XDG_CACHE_HOME/mise" MISE_STATE_DIR="$HOME/.local/state/mise"
  cp "$REPO_ROOT/install.sh" "$REPO_ROOT/new-mac.sh" "$REPO_ROOT/remote-login.sh" \
    "$REPO_ROOT/defaults.toml" "$REPO_ROOT/mise.toml" "$TEST_REPO/"
  cp -R "$REPO_ROOT/scripts" "$TEST_REPO/scripts"
  export PATH="$TEST_BIN:/usr/bin:/bin"
  unset DEVSETUP_PROFILE MISE_ORIGINAL_CWD SUDO_ASKPASS BASH_ENV ENV
  cp -R "$REPO_ROOT/packages" "$TEST_REPO/packages"
  unset SSH_CONNECTION SSH_CLIENT SSH_TTY
  # A test must opt into each substitute. Never provision the host by accident.
  for script in "$TEST_REPO"/scripts/bootstrap-*.sh; do
    printf 'touch "$TEST_ROOT/bootstrap-attempted"\nreturn 99\n' > "$script"
  done
  stub_command sudo <<'SH'
#!/bin/sh
touch "$TEST_ROOT/sudo-attempted"
exit 99
SH
  stub_command brew <<'SH'
#!/bin/sh
touch "$TEST_ROOT/brew-attempted"
exit 99
SH
}

stub_command() {
  cat > "$TEST_BIN/$1"
  chmod 700 "$TEST_BIN/$1"
}
