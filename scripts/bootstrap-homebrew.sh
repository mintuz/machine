#!/usr/bin/env bash
# Sourced by the OS bootstrap so Homebrew stays on the installer's PATH.
: "${bootstrap_shell_files:?Source an OS bootstrap from install.sh}"
for brew_path in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
  if [[ -x "$brew_path" ]]; then
    eval "$("$brew_path" shellenv)"
    break
  fi
done

if ! command -v brew >/dev/null 2>&1; then
  brew_installer="$(mktemp)"
  trap 'rm -f "$brew_installer"' EXIT
  curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$brew_installer"
  /bin/bash "$brew_installer"
  rm -f "$brew_installer"
  trap - EXIT
  for brew_path in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
    if [[ -x "$brew_path" ]]; then
      eval "$("$brew_path" shellenv)"
      break
    fi
  done
fi

brew_path="$(command -v brew)"
for shell_rc in "${bootstrap_shell_files[@]}"; do
  shellenv_line="eval \"\$(\"$brew_path\" shellenv)\""
  if ! grep -Fqx "$shellenv_line" "$HOME/$shell_rc" 2>/dev/null; then
    printf '%s\n' "$shellenv_line" >> "$HOME/$shell_rc"
  fi
done

mkdir -p "$HOME/.ssh" "$HOME/.gnupg"
brew update
brew install ansible
ansible-galaxy collection install -r requirements.yaml
