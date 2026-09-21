#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 COMMAND [ARG ...]" >&2
  exit 64
fi

tmp_dir=""
cleanup() {
  if [[ -n "${keepalive_pid:-}" ]]; then
    kill "$keepalive_pid" 2>/dev/null || true
    wait "$keepalive_pid" 2>/dev/null || true
  fi
  if [[ -n "$tmp_dir" ]]; then
    rm -rf "$tmp_dir"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if sudo -n -v 2>/dev/null; then
  sudo_args=(-n)
else
  if ! { exec 3<>/dev/tty; } 2>/dev/null; then
    echo "Sudo needs a password. Run from a terminal or configure passwordless sudo." >&2
    exit 1
  fi
  tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/dev-setup-sudo.XXXXXX")"
  password_file="$tmp_dir/password"
  askpass_file="$tmp_dir/askpass"
  printf "Sudo password: " >&3
  IFS= read -rs sudo_password <&3
  printf "\n" >&3
  exec 3>&-
  printf "%s\n" "$sudo_password" > "$password_file"
  unset sudo_password
  chmod 600 "$password_file"
  printf '#!/usr/bin/env bash\ncat %q\n' "$password_file" > "$askpass_file"
  chmod 700 "$askpass_file"
  export SUDO_ASKPASS="$askpass_file"
  export ANSIBLE_BECOME_PASSWORD_FILE="$askpass_file"
  sudo_args=(-A)
  sudo "${sudo_args[@]}" -v
fi
export ANSIBLE_BECOME_ASK_PASS=false

(
  while true; do
    sudo "${sudo_args[@]}" -v || exit
    sleep "${SUDO_KEEPALIVE_INTERVAL:-10}"
  done
) &
keepalive_pid=$!

"$@"
