#!/usr/bin/env bash
set -euo pipefail
if [[ "$(uname -s)" != Darwin ]]; then
  echo "Use ./install.sh on Ubuntu." >&2
  exit 1
fi
exec "$(dirname "$0")/install.sh" --bootstrap-only "$@"
