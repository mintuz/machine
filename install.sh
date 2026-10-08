#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_dir"
os_release=/etc/os-release
mode=""
profile=""
use_1password=""
install_dotfiles=""
mise_skip=""
local_skip=""
# `mise bootstrap --help` lists these parts; gui and app-store are this
# repository's own exclusions, honoured by the Brewfile hooks.
mise_parts="plugins packages accounts files services firewall compose repos dotfiles mise-shell-activate shell macos-defaults defaults macos-launchd-agents launchd linux-systemd-units systemd user tools task final-hook"
# Where install.sh records the machine's profile for later `mise run` tasks.
record_file="${MISE_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/mise}/miserc.local.toml"

usage() {
  echo "Usage: $0 [personal|work|--bootstrap-only] [--skip NAME[,NAME...]] [--1password-ssh|--keep-ssh] [--dotfiles|--skip-dotfiles]" >&2
  exit 64
}
while [[ $# -gt 0 ]]; do
  argument="$1"
  case "$argument" in
    personal|work)
      [[ -z "$profile" && -z "$mode" ]] || usage
      profile="$argument"
      ;;
    --bootstrap-only)
      [[ -z "$profile" && -z "$mode" ]] || usage
      mode="$argument"
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
      [[ $# -ge 2 && -n "$2" ]] || usage
      for name in ${2//,/ }; do
        case " gui app-store $mise_parts " in
          *" $name "*) ;;
          *)
            echo "Unknown --skip name '$name'. Use gui, app-store or a mise bootstrap part:" >&2
            echo "  ${mise_parts// /, }" >&2
            exit 64
            ;;
        esac
        case "$name" in
          gui|app-store) local_skip="$local_skip,$name" ;;
          *) mise_skip="$mise_skip,$name" ;;
        esac
      done
      shift
      ;;
    *) usage ;;
  esac
  shift
done
if [[ -n "${DEVSETUP_PROFILE:-}" ]]; then
  case "$DEVSETUP_PROFILE" in
    personal|work) ;;
    *) echo "DEVSETUP_PROFILE must be personal or work." >&2; exit 64 ;;
  esac
  if [[ -n "$profile" && "$profile" != "$DEVSETUP_PROFILE" ]]; then
    echo "The requested profile conflicts with DEVSETUP_PROFILE." >&2
    exit 64
  fi
fi
# The profile for this run: the argument, DEVSETUP_PROFILE, then the record
# from an earlier run. Bootstrap-only applies no profile-specific part.
recorded=""
if [[ -f "$record_file" ]]; then
  recorded="$(awk -F'"' '/^env *= *\[/ { print $2; exit }' "$record_file")"
fi
case "$recorded" in personal|work) ;; *) recorded="" ;; esac
run_profile="${profile:-${DEVSETUP_PROFILE:-$recorded}}"
if [[ -z "$run_profile" ]]; then
  if [[ "$mode" == --bootstrap-only ]]; then
    run_profile=personal
  else
    echo "Pass personal or work: this machine has no recorded profile yet." >&2
    exit 64
  fi
fi

if [[ $EUID -eq 0 ]]; then
  echo "Run setup as your normal user with sudo access, not root." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin) platform=macos ;;
  Linux)
    ID=""
    # shellcheck source=/dev/null
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
  if [[ "$mode" != --bootstrap-only && -t 0 ]]; then
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
  if [[ "$platform" == ubuntu && "$mode" != --bootstrap-only && -t 0 ]]; then
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

# Remember the profile given on the command line so later runs and the mise
# tasks need no profile. The file is mise's own per-machine environment
# selection; only its env line is written.
if [[ -n "$profile" && "$recorded" != "$profile" ]]; then
  record="env = [\"$profile\"]"
  mkdir -p "${record_file%/*}"
  if [[ -f "$record_file" ]] && grep -q '^env *=' "$record_file"; then
    updated="$(awk -v record="$record" '/^env *=/ && !done { print record; done = 1; next } { print }' "$record_file")"
    printf '%s\n' "$updated" > "$record_file"
  else
    printf '%s\n' "$record" >> "$record_file"
  fi
  echo "Recorded the $profile profile in $record_file."
fi

# OS prerequisites, Homebrew (on PATH for the bootstrap hooks), then the
# checksummed mise release and the locked Python. bootstrap-mise.sh sets mise_bin.
# shellcheck source=/dev/null
source "$repo_dir/scripts/bootstrap-$platform.sh"
source "$repo_dir/scripts/bootstrap-homebrew.sh"
source "$repo_dir/scripts/bootstrap-mise.sh"
for command in git curl; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command '$command' is missing after bootstrap." >&2; exit 1; }
done

# Everything else is declared in the mise configuration. The sudo wrapper
# authorises once for the login shell and the Mac update check.
if [[ "$mode" == --bootstrap-only ]]; then
  exec "$repo_dir/scripts/with-sudo-askpass.sh" "$mise_bin" -E "$run_profile" bootstrap --only files,user --yes
fi
mise_env="$run_profile"
if [[ "$use_1password" == true ]]; then
  mise_env="$mise_env,ssh"
  # Keep the current SSH client configuration in mise's history before the template replaces it.
  if [[ -f "$HOME/.ssh/config" ]]; then "$mise_bin" dot track --yes "$HOME/.ssh/config"; fi
fi
if [[ "$install_dotfiles" == false ]]; then mise_skip="$mise_skip,repos,task"; fi
if [[ -n "$local_skip" ]]; then
  export DEV_MACHINE_SKIP="${local_skip#,}"
  echo "Skipping the ${DEV_MACHINE_SKIP//,/ and } Brewfiles (DEV_MACHINE_SKIP=$DEV_MACHINE_SKIP)."
fi
mise_args=(--yes)
if [[ -n "$mise_skip" ]]; then mise_args+=(--skip "${mise_skip#,}"); fi
exec "$repo_dir/scripts/with-sudo-askpass.sh" "$mise_bin" -E "$mise_env" bootstrap "${mise_args[@]}"
