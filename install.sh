#!/usr/bin/env bash
set -euo pipefail

caller_dir="${MISE_ORIGINAL_CWD:-$PWD}"
repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
os_release=/etc/os-release
profile=""
profile_explicit=false
use_1password=""
install_dotfiles=""
config_args=()
skip_args=()
skip_names=""
has_config=false
dotfiles_explicit=false
usage() {
  echo "Usage: $0 [personal|work|--bootstrap-only] [--config PATH] [--skip STEP] [--1password-ssh|--keep-ssh] [--dotfiles|--skip-dotfiles]" >&2
  exit 64
}
while [[ $# -gt 0 ]]; do
  argument="$1"
  case "$argument" in
    personal|work|--bootstrap-only)
      [[ -z "$profile" ]] || usage
      profile="$argument"
      if [[ "$argument" != --bootstrap-only ]]; then profile_explicit=true; fi
      ;;
    --1password-ssh|--keep-ssh)
      [[ -z "$use_1password" ]] || usage
      if [[ "$argument" == --1password-ssh ]]; then use_1password=true; else use_1password=false; fi
      ;;
    --dotfiles|--skip-dotfiles)
      [[ -z "$install_dotfiles" ]] || usage
      dotfiles_explicit=true
      if [[ "$argument" == --dotfiles ]]; then install_dotfiles=true; else install_dotfiles=false; fi
      ;;
    --config)
      [[ "$has_config" == false && $# -ge 2 && -n "$2" ]] || usage
      config_path="$2"
      case "$config_path" in /*) ;; *) config_path="$caller_dir/$config_path" ;; esac
      config_args+=(--config "$config_path")
      has_config=true
      shift
      ;;
    --skip)
      [[ $# -ge 2 ]] || usage
      case "$2" in
        ssh|git|cli|remote-login|gui|zsh|app-store|osx|node|dotfiles|dock) ;;
        *) echo "Unknown or mandatory step: $2" >&2; usage ;;
      esac
      skip_args+=(--skip "$2")
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
      dotfiles_explicit=true
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
if [[ -n "${DEVSETUP_PROFILE:-}" ]]; then profile_explicit=true; fi
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
    if [[ "$has_config" == true ]]; then
      echo "Press Enter to keep the dotfiles choice from your configuration (default Yes)."
    fi
    while true; do
      read -r -p "Install your dotfiles? [Y/n] " answer || break
      case "$answer" in
        y|Y|yes|Yes|YES) dotfiles_explicit=true; break ;;
        "") break ;;
        n|N|no|No|NO) install_dotfiles=false; dotfiles_explicit=true; break ;;
        *) echo "Please answer yes or no." ;;
      esac
    done
  fi
fi

# OS prerequisites, Homebrew, then the checksummed mise release and the locked
# Python. bootstrap-mise.sh sets mise_bin and python_bin.
source "$repo_dir/scripts/bootstrap-$platform.sh"
source "$repo_dir/scripts/bootstrap-homebrew.sh"
source "$repo_dir/scripts/bootstrap-mise.sh"

if [[ "$use_1password" == true ]]; then ssh_flag=--1password-ssh; else ssh_flag=--keep-ssh; fi
bootstrap_profile="$profile"
if [[ "$bootstrap_profile" == --bootstrap-only ]]; then bootstrap_profile="${DEVSETUP_PROFILE:-personal}"; fi
# Remote Login is a separate, explicit operation after software installation.
common_args=(--mise "$mise_bin" "$ssh_flag" --keep-remote-login)
if [[ "$profile_explicit" == true ]]; then common_args+=(--profile "$bootstrap_profile"); fi
common_args+=(${config_args[@]+"${config_args[@]}"})
"$python_bin" "$repo_dir/scripts/setup.py" bootstrap "${common_args[@]}" ${skip_args[@]+"${skip_args[@]}"}

if [[ "$profile" != --bootstrap-only ]]; then
  dotfiles_args=()
  if [[ "$dotfiles_explicit" == true ]]; then
    if [[ "$install_dotfiles" == true ]]; then dotfiles_args=(--dotfiles); else dotfiles_args=(--skip-dotfiles); fi
  fi
  exec "$repo_dir/scripts/with-sudo-askpass.sh" "$python_bin" "$repo_dir/scripts/setup.py" install \
    "${common_args[@]}" ${dotfiles_args[@]+"${dotfiles_args[@]}"} ${skip_args[@]+"${skip_args[@]}"}
fi
