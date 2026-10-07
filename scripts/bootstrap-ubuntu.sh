#!/usr/bin/env bash
# Sourced by install.sh: apt prerequisites for setup, Homebrew, and its formula builds.
: "${repo_dir:?Source this file from install.sh}"
sudo apt-get update
sudo apt-get install -y build-essential procps curl file git python3 rsync unzip zsh
