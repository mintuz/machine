#!/usr/bin/env bash
# Usage: shell-block.sh FILE MARKER LINE...
# Keep one "# BEGIN MARKER" ... "# END MARKER" block in FILE: append it when
# missing, replace it in place when it differs, leave the rest alone. A
# symlinked FILE belongs to another repository (the external dotfiles), so it
# is reported and left unchanged. mise bootstrap hooks call this script.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 FILE MARKER LINE..." >&2
  exit 64
fi
file="$1"
marker="$2"
shift 2
if [[ -L "$file" ]]; then
  echo "$file: left unchanged because it is a symlink to externally managed configuration."
  exit 0
fi
begin="# BEGIN $marker"
end="# END $marker"
BLOCK="$(printf '%s\n' "$begin" "$@" "$end")"
export BLOCK
current=""
if [[ -e "$file" ]]; then
  current="$(<"$file")"
fi
if grep -qxF -- "$begin" "$file" 2>/dev/null && grep -qxF -- "$end" "$file"; then
  updated="$(awk -v begin="$begin" -v end="$end" \
    '$0 == begin && !skip { print ENVIRON["BLOCK"]; skip = 1; next }
     $0 == end && skip { skip = 0; next }
     !skip' "$file")"
elif [[ -z "$current" ]]; then
  updated="$BLOCK"
else
  updated="$current"$'\n'"$BLOCK"
fi
if [[ "$updated" == "$current" ]]; then
  exit 0
fi
printf '%s\n' "$updated" > "$file"
echo "$file: updated the $marker block."
