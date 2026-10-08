#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
os_release=/etc/os-release
profile=""
use_1password=""
install_dotfiles=""
mise_skip=""
skip_names=""
usage() {
  echo "Usage: $0 [personal|work|--bootstrap-only] [--skip PART] [--1password-ssh|--keep-ssh] [--dotfiles|--skip-dotfiles]" >&2
  exit 64
}
while [[ $# -gt 0 ]]; do
  argument="$1"
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
    --skip)
      [[ $# -ge 2 ]] || usage
      # Repository names map onto mise bootstrap parts; a part's hooks go with it.
      case "$2" in
        cli) mise_skip="$mise_skip,packages,tools" ;;
        gui|app-store) mise_skip="$mise_skip,packages" ;;
        zsh) mise_skip="$mise_skip,user" ;;
        osx) mise_skip="$mise_skip,macos-defaults" ;;
        ssh|dotfiles) ;;
        *) echo "Unknown or mandatory step: $2" >&2; usage ;;
      esac
      skip_names="$skip_names $2"
      shift
      ;;
    *) usage ;;
  esac
  shift
done
for skipped_step in $skip_names; do
  case "$skipped_step" in
    ssh)
      [[ "$use_1password" != true ]] || { echo "--skip ssh conflicts with --1password-ssh." >&2; exit 64; }
      use_1password=false
      ;;
    dotfiles)
      [[ "$install_dotfiles" != true ]] || { echo "--skip dotfiles conflicts with --dotfiles." >&2; exit 64; }
      install_dotfiles=false
      ;;
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
  if [[ "$profile" != --bootstrap-only && -t 0 ]]; then
    while true; do
      read -r -p "Use the 1Password SSH agent (replace SSH config; mise keeps the previous file)? [y/N] " answer || break
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

# OS prerequisites, Homebrew (on PATH for the bootstrap hooks), then the
# checksummed mise release and the locked Python. bootstrap-mise.sh sets mise_bin.
source "$repo_dir/scripts/bootstrap-$platform.sh"
source "$repo_dir/scripts/bootstrap-homebrew.sh"
source "$repo_dir/scripts/bootstrap-mise.sh"
for command in git curl; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command '$command' is missing after bootstrap." >&2; exit 1; }
done

# Everything else is declared in the mise configuration. The sudo wrapper
# authorises once for the login shell and the Mac update check.
mise_env="${DEVSETUP_PROFILE:-personal}"
if [[ "$profile" != --bootstrap-only ]]; then mise_env="$profile"; fi
if [[ "$profile" == --bootstrap-only ]]; then
  exec "$repo_dir/scripts/with-sudo-askpass.sh" "$mise_bin" -E "$mise_env" bootstrap --only files,user --yes
fi
if [[ "$use_1password" == true ]]; then
  mise_env="$mise_env,ssh"
  # Keep the current SSH client configuration in mise's history before the template replaces it.
  if [[ -f "$HOME/.ssh/config" ]]; then "$mise_bin" dot track --yes "$HOME/.ssh/config"; fi
fi
if [[ "$install_dotfiles" == false ]]; then mise_skip="$mise_skip,repos,task"; fi
mise_args=(--yes)
if [[ -n "$mise_skip" ]]; then mise_args+=(--skip "${mise_skip#,}"); fi
exec "$repo_dir/scripts/with-sudo-askpass.sh" "$mise_bin" -E "$mise_env" bootstrap "${mise_args[@]}"
