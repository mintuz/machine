#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash scripts/remote-login.sh {check|enable|revoke} [personal|work]" >&2
  exit 64
}
[[ $# -ge 1 && $# -le 2 ]] || usage
action="$1"
profile="${2:-personal}"
case "$action" in check|enable|revoke) ;; *) usage ;; esac
case "$profile" in personal|work) ;; *) usage ;; esac

if [[ "$(uname -s)" != Darwin ]]; then
  echo "Remote Login commands support macOS only." >&2
  exit 1
fi
if [[ $EUID -eq 0 ]]; then
  echo "Run as your normal macOS user, not root." >&2
  exit 1
fi
if [[ "$action" != check && -n "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ]]; then
  echo "Run from the Mac's local console, not SSH or mosh: this command stops the SSH listener." >&2
  echo "Do not unset SSH environment variables to bypass this check. Read-only check: make remote-login-check." >&2
  exit 1
fi
if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "Ansible is missing. Complete repository bootstrap (make setup), then run make deps." >&2
  exit 1
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
playbook=(ansible-playbook local.yaml -e "machine_type=$profile")

if [[ "$action" != revoke ]]; then
  echo "Checking prerequisites without sudo or changes to services, SSH configuration, or keys."
  "${playbook[@]}" --tags remote-login-preflight -e manage_remote_login=true --check
  [[ "$action" != check ]] || exit 0
  echo "Enabling Remote Login: the SSH listener will stop and all authorised keys will be replaced."
  echo "Keep Shields Up on. Complete the README policy and local firewall checks before allowing inbound traffic."
  exec scripts/with-sudo-askpass.sh "${playbook[@]}" --tags remote-login -e manage_remote_login=true
fi

echo "Revoking Remote Login: disabling SSH startup/listening and backing up then clearing this account's authorised keys."
echo "Existing SSH and mosh sessions need separate action. Shields Up is unchanged."
exec scripts/with-sudo-askpass.sh "${playbook[@]}" --tags remote-login-revoke -e revoke_remote_login=true
