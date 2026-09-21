#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
profile="${1:-personal}"
if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [personal|work|--bootstrap-only]" >&2
  exit 64
fi
case "$profile" in
  personal|work|--bootstrap-only) ;;
  *) echo "Usage: $0 [personal|work|--bootstrap-only]" >&2; exit 64 ;;
esac

if [[ $EUID -eq 0 ]]; then
  echo "Run setup as your normal user with sudo access, not root." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin) source "$repo_dir/scripts/bootstrap-macos.sh" ;;
  Linux)
    source /etc/os-release
    if [[ "$ID" != ubuntu ]]; then
      echo "Only Ubuntu is supported on Linux." >&2
      exit 1
    fi
    source "$repo_dir/scripts/bootstrap-ubuntu.sh"
    ;;
  *) echo "Only macOS and Ubuntu are supported." >&2; exit 1 ;;
esac

if [[ "$profile" != --bootstrap-only ]]; then
  exec "$repo_dir/scripts/with-sudo-askpass.sh" ansible-playbook local.yaml -e "machine_type=$profile"
fi
