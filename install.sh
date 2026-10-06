#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
os_release=/etc/os-release
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
if [[ -n "${DEVSETUP_PROFILE:-}" ]]; then
  case "$DEVSETUP_PROFILE" in
    personal|work) ;;
    *) echo "DEVSETUP_PROFILE must be personal or work." >&2; exit 64 ;;
  esac
  if [[ -n "$profile" && "$profile" != --bootstrap-only && "$profile" != "$DEVSETUP_PROFILE" ]]; then
    echo "The requested profile conflicts with DEVSETUP_PROFILE." >&2
    exit 64
  fi
fi
profile="${profile:-${DEVSETUP_PROFILE:-personal}}"

if [[ $EUID -eq 0 ]]; then
  echo "Run setup as your normal user with sudo access, not root." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin) platform=macos ;;
  Linux)
    ID=""
    source "$os_release"
    if [[ "$ID" != ubuntu ]]; then
      echo "Only Ubuntu is supported on Linux." >&2
      exit 1
    fi
    platform=ubuntu
    ;;
  *) echo "Only macOS and Ubuntu are supported." >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ;;
  *)
    echo "Only ARM64 machines are supported: Apple silicon Macs (not under Rosetta) and aarch64 Ubuntu." >&2
    exit 1
    ;;
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
    echo "See 'Remote access from an iPhone' in README.md. If not ready, choose No and use mise run remote-login later."
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

# OS prerequisites, then the checksummed mise release and the locked Python.
# bootstrap-mise.sh sets mise_bin and python_bin.
source "$repo_dir/scripts/bootstrap-$platform.sh"
source "$repo_dir/scripts/bootstrap-mise.sh"

if [[ "$use_1password" == true ]]; then ssh_flag=--1password-ssh; else ssh_flag=--keep-ssh; fi
bootstrap_profile="$profile"
if [[ "$bootstrap_profile" == --bootstrap-only ]]; then bootstrap_profile="${DEVSETUP_PROFILE:-personal}"; fi
"$python_bin" "$repo_dir/scripts/setup.py" bootstrap --profile "$bootstrap_profile" --mise "$mise_bin" "$ssh_flag"

if [[ "$profile" != --bootstrap-only ]]; then
  if [[ "$install_dotfiles" == true ]]; then dotfiles_flag=--dotfiles; else dotfiles_flag=--skip-dotfiles; fi
  remote_flag=--keep-remote-login
  if [[ "$manage_remote_login" == true ]]; then
    "$python_bin" "$repo_dir/scripts/setup.py" remote-login-check --profile "$profile" --mise "$mise_bin"
    remote_flag=--remote-login
  fi
  exec "$repo_dir/scripts/with-sudo-askpass.sh" "$python_bin" "$repo_dir/scripts/setup.py" install \
    --profile "$profile" --mise "$mise_bin" "$ssh_flag" "$dotfiles_flag" "$remote_flag"
fi
