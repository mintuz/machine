#!/usr/bin/env bash
: "${repo_dir:?Source this file from install.sh}"
sudo apt-get update
sudo apt-get install -y build-essential procps curl file git python3 rsync unzip zsh
bootstrap_shell_files=(.bashrc .zshrc)
source "$repo_dir/scripts/bootstrap-homebrew.sh"
