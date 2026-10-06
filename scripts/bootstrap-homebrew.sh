#!/usr/bin/env bash
# Sourced by install.sh after the OS bootstrap. Installs Homebrew with its
# official installer at the ARM64 prefix that defaults.toml expects, and puts
# it on the installer's PATH. Homebrew owns native formulae and casks; the
# setup.py bootstrap step adds `brew shellenv` to the shell startup files.
: "${platform:?Source this file from install.sh}"
case "$platform" in
  macos) brew_path=/opt/homebrew/bin/brew ;;
  ubuntu) brew_path=/home/linuxbrew/.linuxbrew/bin/brew ;;
esac

if [[ ! -x "$brew_path" ]]; then
  brew_installer="$(mktemp)"
  trap 'rm -f "$brew_installer"' EXIT
  curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$brew_installer"
  /bin/bash "$brew_installer"
  rm -f "$brew_installer"
  trap - EXIT
fi
if [[ ! -x "$brew_path" ]]; then
  echo "Homebrew was not installed at $brew_path." >&2
  exit 1
fi
eval "$("$brew_path" shellenv)"
brew update
