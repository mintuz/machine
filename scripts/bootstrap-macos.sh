#!/usr/bin/env bash
# Sourced by install.sh. The Command Line Tools supply git, the compiler and
# codesign that native Homebrew formula installs and source builds need.
: "${repo_dir:?Source this file from install.sh}"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install || true
  until xcode-select -p >/dev/null 2>&1; do
    echo "Waiting for Xcode Command Line Tools installation..."
    sleep 5
  done
fi
