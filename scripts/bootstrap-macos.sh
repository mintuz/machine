#!/usr/bin/env bash
: "${repo_dir:?Source this file from install.sh}"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install || true
  until xcode-select -p >/dev/null 2>&1; do
    echo "Waiting for Xcode Command Line Tools installation..."
    sleep 5
  done
fi
bootstrap_shell_files=(.zshrc)
source "$repo_dir/scripts/bootstrap-homebrew.sh"
if [[ "${use_1password:-false}" == true ]]; then
  if ! brew list --cask 1password >/dev/null 2>&1 && [[ ! -d /Applications/1Password.app ]]; then
    brew install --cask 1password
  fi
  echo "Open 1Password, sign in, and enable its SSH agent before using Git over SSH."
fi
