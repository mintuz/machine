# Sourced by the mise tasks (sh). Sets mise_env, the environment for one
# `mise bootstrap` run, and puts Homebrew on PATH for the hooks. The task's
# --profile (usage_profile) and DEVSETUP_PROFILE must agree; either wins for
# the run. Otherwise the environment mise already selected applies: the
# profile install.sh recorded in miserc.local.toml, or -E on `mise run`.
# Personal is the last resort.
profile="${usage_profile:-}"
for candidate in "$profile" "${DEVSETUP_PROFILE:-}"; do
  case "$candidate" in
    ""|personal|work) ;;
    *) echo "The profile must be personal or work, not '$candidate'." >&2; exit 64 ;;
  esac
done
if [ -n "$profile" ] && [ -n "${DEVSETUP_PROFILE:-}" ] && [ "$profile" != "$DEVSETUP_PROFILE" ]; then
  echo "--profile $profile conflicts with DEVSETUP_PROFILE=$DEVSETUP_PROFILE." >&2
  exit 64
fi
# shellcheck disable=SC2034  # read by the task that sources this file
mise_env="${profile:-${DEVSETUP_PROFILE:-${MISE_ENV:-personal}}}"
# The caller's shell may lack Homebrew (the external dotfiles own ~/.zshrc).
for brew in /opt/homebrew/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
  if [ -x "$brew" ]; then
    eval "$("$brew" shellenv sh)"
    break
  fi
done
