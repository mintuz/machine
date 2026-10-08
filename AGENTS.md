# Repository guidance

This repository configures ARM64 macOS and headless Ubuntu development
machines. Both support personal and work profiles. Mise owns runtimes and the
command interface. Homebrew owns native formulae and casks. Python standard-
library helpers own configuration and privileged operations. Make and
Ansible are no longer provisioning engines. Do not add a parallel legacy path.

This is the shared maintenance guide for Codex and Claude Code. `CLAUDE.md`
imports this file; keep project instructions here to avoid divergent copies.
See `README.md` for user-facing commands, security limits and validation.
`ARCHITECTURE-REPORT.md` is historical research, not the current implementation
contract.

## Repository map

| Path | Responsibility |
| --- | --- |
| `install.sh`, `scripts/bootstrap-*.sh` | Consent prompts, ARM/OS validation and bootstrap prerequisites |
| `remote-login.sh` | Explicit post-install Remote Login entry point using mise's configured Python |
| `mise.toml`, `mise.lock` | Public tasks and the locked helper Python |
| `scripts/with-sudo-askpass.sh` | Sudo authorisation, password helper and cleanup |
| `scripts/setup.py`, `scripts/devsetup/cli.py` | Direct CLI and setup ordering |
| `scripts/devsetup/config.py`, `defaults.toml` | Configuration, OS/profile validation and per-platform defaults |
| `packages/` | Literal Homebrew Bundle files and mise `[tools]` tables per layer; no installation logic |
| `scripts/devsetup/software.py` | `brew bundle` installation, mise tool installation and the machine fragment |
| `scripts/devsetup/host.py` | Prerequisites, Git, shell, external dotfiles, macOS preferences and Dock |
| `scripts/update.sh` | Shell maintenance of installed Homebrew, mise, npm/pnpm, App Store and Ollama software |
| `scripts/devsetup/security.py` | Managed SSH client configuration and Remote Login |
| `templates/` | Managed SSH client/server templates |
| `scripts/devsetup/global_gitignore` | Managed global Git ignore content |
| `.ssh/` | Public SSH keys only; never private keys |
| `scripts/check.py`, `scripts/check-*.py` | Non-installing configuration, host, software and security checks |
| `tests/shell/` | Bats behaviour tests for shell entry points and sudo authorisation |

## Entry points and configuration

`install.sh [personal|work|--bootstrap-only] [--config PATH] [--skip STEP]
[--1password-ssh|--keep-ssh] [--dotfiles|--skip-dotfiles]` validates the profile, OS, architecture and user
before bootstrap. Reject Intel, Rosetta, non-Ubuntu Linux and root. Bootstrap
helpers are sourced, not independent entry points. Keep OS prerequisites,
Homebrew installation and the checksummed mise/locked Python installation in
that order. Do not introduce an Ansible or pip bootstrap dependency.
`new-mac.sh` remains the Mac bootstrap-only wrapper.

`mise run setup personal|work` invokes the installer. Other tasks dispatch to
`scripts/setup.py` and assume bootstrap is complete. They do not prompt for
feature choices. Use `--profile personal|work` or `DEVSETUP_PROFILE`; default
to personal on each invocation and reject conflicting selections. The
installer uses a positional profile and must reject an environment conflict
before any installation. Pass the effective profile to its bootstrap helper.

Load `defaults.toml`, then the single optional `--config` file. Apply the
selected `[mac]` or `[linux]` table within each file after its shared keys.
The override file replaces defaults; explicit feature flags override
configuration. Keep platform paths in these tables and shared preferences
outside them. Unknown keys pass through untouched. Do not let local TOML
files enable the private security command-injection seams used by tests.
Preserve the documented `remote_login_sshd` list and
`remote_login_launchctl` executable overrides for isolated validation.
The profile comes only from the command line or `DEVSETUP_PROFILE`, never
from a settings file. The canonical `[steps]` table contains `ssh`, `git`,
`cli`, `remote-login`, `gui`, `zsh`, `app-store`, `osx`, `node`, `dotfiles`
and `dock`. Merge it by key, not whole-table replacement. Other lists
replace earlier values. The old root feature keys are removed, not aliases.
Repeatable `--skip STEP` overrides the selected policy for aggregate
installation only. Direct component commands opt in explicitly and report
when they override a saved exclusion; contradictory explicit flags fail.
Bootstrap and preflight cannot be skipped. Revocation is a separate
operation and must never be suppressed by a step exclusion.

The installer forwards the same `--config` file and component choices to
Python, resolving the relative path from the original invocation
directory. A repeated `--config` is a usage error. Keep TOML parsing in
Python. On an unbootstrapped machine, TOML validation follows interpreter
installation; do not promise zero bootstrap
changes for an invalid file. SSH client consent remains before bootstrap
and takes precedence over file choices. The installer always disables
Remote Login enablement for its run; access setup is a later explicit
operation. Pass dotfiles and profile overrides only for explicit choices;
otherwise let Python resolve the configured values and defaults.


Full setup validates prerequisites and refreshes Homebrew before managed SSH,
Git, CLI/fzf, Remote Login, GUI, Zsh, App Store, macOS preferences, Node,
dotfiles and Dock. Filter this fixed order by the typed step policy.
Preserve each OS and security guard. A failed prerequisite or Homebrew
refresh must stop before SSH or host writes. Host preflight owns the one
setup/component refresh; CLI and GUI helpers must not repeat it. The
installer's prerequisite bootstrap has its own refresh. Run Python as the
normal user; escalate individual operations with sudo.

`mise run packages --profile personal|work` is read-only. Root task settings
must prevent automatic runtime installation during previews and checks.
`--check` bypasses the sudo wrapper. It reports only supported previews;
several host actions deliberately say they are not previewed. Never describe
it as a complete configuration or SSH deployment preview.

## Consent and independent repositories

The SSH prompt defaults to No. Without a terminal, preserve SSH unless
`--1password-ssh` is explicit. Set `steps.ssh` for that run; both OS
defaults are false. Declining must leave existing SSH files and agents
untouched, including a configuration from an earlier opt-in. The explicit
`mise run ssh` action opts in without a prompt.

When requested for SSH, Mac bootstrap installs 1Password early. Enabling its
agent and signing in remain manual. The Mac app and shared CLI inventories
remain independent of the SSH choice. On Ubuntu, an existing `SSH_AUTH_SOCK`
selects the literal `IdentityAgent "SSH_AUTH_SOCK"`, not a temporary socket
path; otherwise use `~/.1password/agent.sock`. Headless users forward their
client agent. Do not install the Linux desktop app during headless bootstrap.

Dotfiles default to enabled on both OSes. Interactive Ubuntu full setup asks
`Install your dotfiles? [Y/n]` before bootstrap. Enter and unattended runs
keep the file's `steps.dotfiles` choice, or the enabled default. Explicit
dotfiles flags and `--skip dotfiles` skip the prompt. Bootstrap-only runs
neither ask about nor install dotfiles. `mise run dotfiles` is the later
explicit installation path.

Delegate installation to the external dotfiles repository's `install.sh`.
Keep portable shell behaviour and agent skills out of this repository. Changes
to another repository need explicit authorisation and a separate linked PR;
never modify a dirty live dotfiles checkout incidentally. The default dotfiles
revision tracks `master`: fetch and fast-forward before running its installer
on each enabled setup. Honour an explicit revision override. Refuse dirty
checkouts and preserve local branch commits. Refuse to leave unreferenced detached commits behind
until the user saves them on a branch. Back up managed conflict paths before
replacing them.
For an existing checkout, reject an origin that differs from the configured
repository before fetching or changing its revision. Compare local paths
using Git's path interpretation; never silently rewrite a user's origin.

The external shell activates mise and handles project Node version files.
It must not require the Homebrew executable. Its `dotfiles.toml` fragment
must coexist with this repository's `dev-machine-setup.toml` under a real
`~/.config/mise/conf.d` directory. Honour `MISE_CONFIG_DIR` and
`XDG_CONFIG_HOME`. Do not overwrite user mise settings or traverse external
symlinked configuration ancestors, including `.config`. Normal macOS `/var`
and `/tmp` aliases are permitted. With dotfiles disabled, bootstrap still
configures regular shell files for Homebrew and mise. Selected CLI setup
adds fzf; selected Node setup adds Ubuntu pnpm paths; selected Zsh setup
adds the Oh My Zsh/autosuggestions block. Use host.ensure_block for managed
shell blocks. Never edit symlinked shell files owned by another repository.

SSH key filenames, Git identity, dotfiles source and pnpm global packages live
in `defaults.toml`. Profiles change the primary managed GitHub key, not Git
identity. Keep unique timestamped SSH backups inside the security operation
so direct calls cannot bypass them or overwrite an earlier backup. Backups
live under `~/.dev-setup-backups`; leave older backup directories untouched.

Mac preferences and Dock argument lists live in `defaults.toml` under
`[mac]`, as `macos_preferences` and `dock_items`. Validate their shapes
before writes. Empty Dock data must not clear the Dock. Empty preference
data skips configurable defaults but retains Library visibility and
automatic-update checks; `steps.osx=false` skips the entire operation.
Do not restore the removed automatic `LSQuarantine=false` preference.

Reuse existing sudo authorisation, including NOPASSWD access when `sudo -v`
requires a password under the account's verification policy. Prompt only when
needed and a terminal is available. Keep authorisation alive during the
command, propagate its exit status and remove temporary credential files.

## Package and runtime ownership

Combine `shared/`, `shared/<profile>/`, `<mac|linux>/` and
`<mac|linux>/<profile>/` in that order. Each layer may contain
`Brewfile.cli`, `Brewfile.gui`, `Brewfile.app-store`, `tools.cli.toml` and
`tools.node.toml`; every file is optional. Brewfiles use plain Homebrew
Bundle syntax. Setup concatenates the selected files of one kind in layer
order and pipes them to `brew bundle install --file=-` with
`HOMEBREW_NO_AUTO_UPDATE=1`. `tools.*.toml` files hold a mise `[tools]`
table; setup merges them in layer order, runs `mise install name@version`
and records the merged table in `~/.config/mise/conf.d/dev-machine-setup.toml`
while keeping unrelated earlier entries. Create a layer only when it
contains packages. Profiles are additive, not uninstall lists.

Keep casks under `packages/mac/`. Declare a Linux provider for a CLI cask
in `packages/linux/tools.cli.toml` where one exists. Homebrew handles
native formulae and casks, including their post-install steps. Do not
generate Brewfiles or maintain duplicate inventories. The native mise
bottle installer did not create Git's certificate configuration in clean
Ubuntu validation, so it is not the native package owner for this release.
Use mise for runtimes and supported standalone CLI providers. Use apt only
for Ubuntu bootstrap prerequisites and zsh. Rely on `brew bundle`
semantics: it adopts apps already present in `/Applications`, upgrades
outdated items and leaves self-updating casks alone unless an item says
`greedy: true`. App Store apps use `mas "Name", id: N` lines with the Mac
app's ID. A third-party formula or cask needs its `tap` line and
item-level `trusted: true` on the fully qualified item. Never trust a
whole tap or disable Homebrew's trust policy. Preview commands must not
modify the trust store. Maintenance must not grant blanket trust to
installed taps or restore revoked permissions implicitly.

The `cli` step owns `Brewfile.cli`, `tools.cli.toml` and fzf; a bundle or
`mise install` failure stops setup. `gui` owns `Brewfile.gui` and
`app-store` owns `Brewfile.app-store`; both are Mac-only, and `app-store`
runs `mdimport /Applications` first so mas can see installed apps. Their
failures let later steps continue: return one issue string from the step;
the dispatcher lists the issues at the end, also after a fatal error, and
returns failure. Never repair Homebrew state or delete backups
automatically. Mac App Store installation requires sign-in. Remove disabled
`tldr` before installing its replacement `tlrc`. Remove the conflicting
`claude-code@latest` cask before installing its replacement `claude-code`
cask.

The `node` step owns `tools.node.toml`: Node, pnpm and all `npm:` mise
providers. It installs and records those tools, adds the `PNPM_HOME` shell
block on Ubuntu through `host.ensure_block`, creates `pnpm_home/bin` and
installs each `pnpm_global_packages` entry with
`mise exec <specs> -- pnpm add -g <package>@latest`. A pnpm failure stops
setup. Do not hide Node mutation in CLI installation, even when Node is
excluded. Native prerequisites of selected components remain allowed;
exclusions are not an uninstall/package-denial policy. Ensure child tools
can find the configured mise executable, even with an absolute `--mise`
path and a minimal `PATH`.

`mise run update` runs `scripts/update.sh`, a Bash script without Python
or the sudo wrapper. It maintains all installed software regardless of
profile or step settings; `--skip` and `--config` do not apply. In order:
`brew update`, `brew upgrade` with Homebrew's default non-greedy semantics,
`brew cleanup -s`, `mise upgrade --no-prune`, `npm update -g` and
`pnpm update -g` through `mise exec`, `mas upgrade` on macOS and
`ollama pull` for each listed model. Skip a component whose tool is absent
and print why; pnpm also needs `PNPM_HOME`. Continue after a failed
component, print a summary with one line per component and return failure
if any component failed. Do not introduce Ubuntu system upgrades.

## Remote Login safety contract

Remote Login is Mac-only and opt-in per run. The initial installer must
not offer an enablement prompt or run the Remote Login preflight. Always
pass `--keep-remote-login` from `install.sh`, including when local files
enable that step. Keep the Python bootstrap action free of Remote Login
checks so missing Tailscale or phone keys cannot stop software installation.

After installation, use `./remote-login.sh`. Keep this launcher thin:
resolve the repository's Python through mise, then invoke the existing
`remote-login` action. That action checks prerequisites before sudo or
service changes; do not chain a duplicate preflight. Find mise on PATH or
at the bootstrap link `~/.local/bin/mise`. Preserve the caller's directory
for relative configuration paths. Keep the direct mise tasks available.

Tailscale's Mac app is in the GUI inventory. Users must still sign in,
prepare phone keys and review policy/firewall restrictions. Before
enablement, document key replacement, interrupted sessions, Shields Up
and FileVault limits. Do not treat app installation as consent or proof
of network isolation. Offline revocation must not depend on enablement's
phone-key or Tailscale prerequisites.

`mise run remote-login-check` checks phone keys, Tailscale and the SSH command
path without sudo, writes or service changes. It can run remotely. It does not
deploy configuration, validate effective SSH settings or prove network
isolation. It does not require the Homebrew executable.

`mise run remote-login` explicitly enables access. The separate
`mise run remote-login-revoke` opts in with `revoke_remote_login=true`.
Revocation wins if both choices are true, including the direct
`remote-login --revoke-remote-login` command. A false step leaves earlier
changes in place. Enablement and revocation reject non-Mac, root, invalid profiles
and detected SSH sessions (`SSH_CONNECTION`, `SSH_CLIENT`, `SSH_TTY`). These
checks are an operator guard, not proof of local-console use. Never bypass
them by clearing variables.

Keep normal post-unlock SSH key-only and limited to tailnet source addresses.
Do not extend that promise to FileVault's pre-unlock password SSH. Source
restrictions do not bind the wildcard listener or stop Bonjour advertising.
Shields Up is not a LAN firewall.

Keep the limits in the managed file's `Match all` block. Match settings override
global settings in every file. Pin `AuthorizedKeysFile`,
`AuthorizedKeysCommand`, `TrustedUserCAKeys` and `PubkeyAuthentication yes`
there. Disable startup and unload the listener before snapshotting or deploying
configuration. Reject symlink/non-regular managed files. Save prior bytes,
owner, group and mode.

Validate with native `sshd -t` and `sshd -T`. Stop if sshd does not read the
managed file, another file weakens limits or adds a Match block, or account
rules could block login. Refuse `DenyUsers`, `DenyGroups`, `AllowGroups`,
`RefuseConnection`, `ForceCommand`, `ChrootDirectory`, `PermitTTY no` and
`MaxSessions 0`; do not override them. Later Match blocks can add AllowUsers
entries. On deployment or gate failure, restore the previous file and metadata,
or remove the new file if previously absent. Leave SSH off and report the
original failure.

Only after the gate succeeds may authorised keys and the access list change.
Limit the access list to the invoking account, including removal of nested
groups. Parse all continuation lines in directory-service output. Enable
startup only after these changes succeed. If activation or the port check
fails, disable startup and unload again. Never suggest manual enablement after
a failed run.

Use `/usr/sbin/sshd` and `/usr/bin/ssh-keygen` by default, not Homebrew OpenSSH's
different configuration paths. All launchctl commands use the configured
`remote_login_launchctl`, default `/bin/launchctl`, so checks can substitute a
stateful executable. Enablement needs a nonempty list of files, each with one
public key line and no options. Back up a differing nonempty `authorized_keys`
before replacing the whole file. Removing the final key uses revocation, not
empty-key enablement. Revocation disables startup/listener and backs up then
clears this account's keys. It needs neither Homebrew, Tailscale nor phone keys
and retains the managed server configuration.

Stopping the listener or removing keys does not reliably end existing SSH or
mosh sessions. Warn that sessions may be interrupted. Incident response must
identify and terminate affected processes without killing herdr or unrelated
local terminal sessions indiscriminately.

Never change Shields Up or the control-server policy automatically. README
must require a local firewall and review of all additive grants and legacy
ACLs before activation. Remove or narrow matching broad rules. Require allow
and deny policy tests, with the provider's administrator if needed. Keep
Shields Up on until setup and policy checks succeed, then document only
explicit manual release. Keep network examples fictional. iPhone, firewall
and incident steps remain manual.

## Making and validating changes

Add software to the layer Brewfiles and `tools.*.toml` files, not Python
package lists. Put behaviour in the responsible domain module and keep the
CLI dispatcher explicit. Keep Mac-only commands behind platform guards.
Update this guide and README when
commands or ownership change. Do not add compatibility aliases for removed
Make targets or Ansible tags.

After code or inventory changes, run `mise run check`, or
`python3 -B scripts/check.py` with Python 3.11 or newer and `bats` on PATH.
Homebrew `bats-core` is required in both Mac profiles. On Ubuntu or before
Mac CLI installation, install that test dependency explicitly. Missing
Bats must fail the full check command, not silently omit shell coverage.
Use `mise run check-shell` or `bats tests/shell` for the shell suite alone;
`tests/shell/update.bats` covers `scripts/update.sh` with fake executables.
Keep those tests focused on public outcomes: state preservation, refused
operations, exit status and credential cleanup. Reuse the isolated sandbox
and substitute privileged commands; do not assert source text, exact
internal command sequences or copied argument echoes. Move overlapping
shell cases out of the Python checks instead of maintaining duplicate tests.

Checks use temporary directories and substitute commands. They cover the four OS/profile pairs,
terminal prompts, opt-ins, configuration precedence, malformed tools files,
headless sudo, backups, revision safety, fragment safety and failure
propagation. On macOS they also run real unprivileged `sshd -T` gates.
Stateful service substitutes cover stop-before-write, rollback, offline final-
key revocation and partial activation failures without changing host services.
Inspect real selection with `mise run packages --profile personal` and
`mise run packages --profile work`. ShellCheck can check the Bash entry points.

Use disposable machines or containers for real bootstrap/install/update and
shell checks. Do not provision the development host to validate a change.
Syntax checks and substitute commands do not prove fresh-machine or interactive
shell behaviour. Report the limits of each result. In VMPal, detach writable
host shares before provisioning; VM disk isolation does not protect them.

Remote Login check mode skips deployment, the effective-settings gate and
activation. A real enable run needs sudo and phone keys; revocation needs sudo
but not keys or Tailscale. Only an actual phone connection and denied network
paths establish end-to-end access and isolation. Never activate or revoke the
development host's Remote Login merely to validate an edit.

## Approved architecture migration

`ARCHITECTURE-PLAN.md` holds the 2026-10-08 provisioning review and a phased
migration to `mise bootstrap`, approved by the owner with the contract
decisions in its section 9. `docs/research/` holds the raw findings. Each
phase updates this guide when its code lands; until then this guide
describes the current code, not the plan.
