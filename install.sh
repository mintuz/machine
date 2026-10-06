#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
profile=""
use_1password=""
install_dotfiles=""
manage_remote_login=false
usage() {
  echo "Usage: $0 [personal|work|--bootstrap-only] [--1password-ssh|--keep-ssh] [--dotfiles|--skip-dotfiles]" >&2
  exit 64
}
for argument in "$@"; do
  case "$argument" in
    personal|work|--bootstrap-only)
      [[ -z "$profile" ]] || usage
      profile="$argument"
      ;;
    --1password-ssh|--keep-ssh)
      [[ -z "$use_1password" ]] || usage
      if [[ "$argument" == --1password-ssh ]]; then use_1password=true; else use_1password=false; fi
      ;;
    --dotfiles|--skip-dotfiles)
      [[ -z "$install_dotfiles" ]] || usage
      if [[ "$argument" == --dotfiles ]]; then install_dotfiles=true; else install_dotfiles=false; fi
      ;;
    *) usage ;;
  esac
done
profile="${profile:-personal}"

if [[ $EUID -eq 0 ]]; then
  echo "Run setup as your normal user with sudo access, not root." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin) platform=macos ;;
  Linux)
    source /etc/os-release
    if [[ "$ID" != ubuntu ]]; then
      echo "Only Ubuntu is supported on Linux." >&2
      exit 1
    fi
    platform=ubuntu
    ;;
  *) echo "Only macOS and Ubuntu are supported." >&2; exit 1 ;;
esac

if [[ -z "$use_1password" ]]; then
  use_1password=false
  if [[ -t 0 ]]; then
    while true; do
      read -r -p "Use the 1Password SSH agent (back up and replace SSH config)? [y/N] " answer || break
      case "$answer" in
        y|Y|yes|Yes|YES) use_1password=true; break ;;
        n|N|no|No|NO|"") break ;;
        *) echo "Please answer yes or no." ;;
      esac
    done
  fi
fi
if [[ "$use_1password" == true ]]; then
  echo "SSH: configure 1Password. Enable its agent or forward it from your client before using SSH."
else
  echo "SSH: preserve the existing configuration and agent."
fi
if [[ -z "$install_dotfiles" ]]; then
  install_dotfiles=true
  if [[ "$platform" == ubuntu && "$profile" != --bootstrap-only && -t 0 ]]; then
    while true; do
      read -r -p "Install your dotfiles? [Y/n] " answer || break
      case "$answer" in
        y|Y|yes|Yes|YES|"") break ;;
        n|N|no|No|NO) install_dotfiles=false; break ;;
        *) echo "Please answer yes or no." ;;
      esac
    done
  fi
fi
if [[ "$platform" == macos && "$profile" != --bootstrap-only ]]; then
  if [[ -n "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ]]; then
    echo "Remote Login: leave existing access unchanged. Enable it later from the Mac's local console."
  elif [[ -t 0 ]]; then
    echo "Remote Login enables incoming SSH access and replaces all authorised keys with your listed phone keys."
    echo "It can interrupt existing sessions. Run only from the Mac's local console."
    echo "First prepare phone public keys, connect Tailscale, and review the firewall and tailnet policy."
    echo "Keep Shields Up on. FileVault pre-unlock SSH is not covered by the key-only limits."
    echo "See 'Remote access from an iPhone' in README.md. If not ready, choose No and use make remote-login later."
    while true; do
      read -r -p "Configure and enable Remote Login on this Mac? [y/N] " answer || break
      case "$answer" in
        y|Y|yes|Yes|YES) manage_remote_login=true; break ;;
        n|N|no|No|NO|"") break ;;
        *) echo "Please answer yes or no." ;;
      esac
    done
  fi
fi

source "$repo_dir/scripts/bootstrap-$platform.sh"

if [[ "$profile" != --bootstrap-only ]]; then
  if [[ "$manage_remote_login" == true ]]; then
    bash "$repo_dir/scripts/remote-login.sh" check "$profile"
  fi
  exec "$repo_dir/scripts/with-sudo-askpass.sh" ansible-playbook local.yaml \
    -e "machine_type=$profile" -e "manage_ssh_config=$use_1password" \
    -e "install_dotfiles=$install_dotfiles" -e "manage_remote_login=$manage_remote_login"
fi
