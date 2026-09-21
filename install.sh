#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
profile=""
use_1password=""
usage() {
  echo "Usage: $0 [personal|work|--bootstrap-only] [--1password-ssh|--keep-ssh]" >&2
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
source "$repo_dir/scripts/bootstrap-$platform.sh"

if [[ "$profile" != --bootstrap-only ]]; then
  exec "$repo_dir/scripts/with-sudo-askpass.sh" ansible-playbook local.yaml \
    -e "machine_type=$profile" -e "manage_ssh_config=$use_1password"
fi
