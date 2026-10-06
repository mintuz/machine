#!/usr/bin/env bash
# Sourced by install.sh after the OS bootstrap. Installs the pinned mise release,
# verified against its published SHA-256, then the Python locked in mise.lock.
# Sets mise_bin and python_bin for install.sh.
: "${repo_dir:?Source this file from install.sh}"
: "${platform:?Source this file from install.sh}"
mise_version=2026.10.3
case "$platform" in
  macos)
    mise_asset=macos-arm64
    mise_sha256=0999bd4943523ccdbd149b5ad4080281536801b3f6406ac4495699bd0310969c
    ;;
  ubuntu)
    mise_asset=linux-arm64
    mise_sha256=357260e28904569a6e7124d33b65cef6d043846c07bb8f4906ddf22cc353d61d
    ;;
esac
mise_root="${XDG_DATA_HOME:-$HOME/.local/share}/dev-machine-setup/mise"
mise_bin="$mise_root/$mise_version/mise"

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d ' ' -f 1
  else
    shasum -a 256 "$1" | cut -d ' ' -f 1
  fi
}

if [[ ! -x "$mise_bin" || "$(sha256_of "$mise_bin")" != "$mise_sha256" ]]; then
  echo "Installing mise $mise_version..."
  mkdir -p "${mise_bin%/*}"
  mise_download="$(mktemp "${mise_bin%/*}/download.XXXXXX")"
  trap 'rm -f "$mise_download"' EXIT
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --output "$mise_download" \
    "https://github.com/jdx/mise/releases/download/v$mise_version/mise-v$mise_version-$mise_asset"
  if [[ "$(sha256_of "$mise_download")" != "$mise_sha256" ]]; then
    echo "The mise download does not match its pinned SHA-256; refusing to use it." >&2
    exit 1
  fi
  chmod 755 "$mise_download"
  mv -f "$mise_download" "$mise_bin"
  trap - EXIT
fi

# Dotfiles and new shells find mise as ~/.local/bin/mise. Keep a link that this
# setup created current, but never replace another mise installation.
mise_link="$HOME/.local/bin/mise"
if [[ ! -e "$mise_link" && ! -L "$mise_link" ]] ||
   [[ -L "$mise_link" && "$(readlink "$mise_link")" == "$mise_root/"* ]]; then
  mkdir -p "${mise_link%/*}"
  ln -sfn "$mise_bin" "$mise_link"
else
  echo "Keeping the existing $mise_link; setup uses $mise_bin."
fi

"$mise_bin" trust "$repo_dir/mise.toml"
(cd "$repo_dir" && "$mise_bin" install --locked python)
python_bin="$(cd "$repo_dir" && "$mise_bin" which python)"
