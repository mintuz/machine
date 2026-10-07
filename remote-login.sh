#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
mise_bin="$(command -v mise || true)"
if [[ -z "$mise_bin" ]]; then mise_bin="$HOME/.local/bin/mise"; fi
if [[ ! -x "$mise_bin" ]]; then
  echo "mise is unavailable. Run ./install.sh before configuring Remote Login." >&2
  exit 1
fi
case "$mise_bin" in /*) ;; *) mise_bin="$PWD/$mise_bin" ;; esac
python_bin="$("$mise_bin" -C "$repo_dir" which python)"
exec "$python_bin" "$repo_dir/scripts/setup.py" remote-login --mise "$mise_bin" "$@"
