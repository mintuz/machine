# Repository guidance

This repository configures ARM64 macOS and headless Ubuntu development
machines. Both support personal and work profiles. Mise owns runtimes and the
command interface. Homebrew owns native formulae and casks. Python standard-
library helpers own configuration and privileged operations. Make, Ansible and
nvm are no longer provisioning engines. Do not add a parallel legacy path.

This is the shared maintenance guide for Codex and Claude Code. `CLAUDE.md`
imports this file; keep project instructions here to avoid divergent copies.
See `README.md` for user-facing commands, security limits and validation.
`ARCHITECTURE-REPORT.md` is historical research, not the current implementation
contract.

## Repository map

| Path | Responsibility |
| --- | --- |
| `install.sh`, `scripts/bootstrap-*.sh` | Consent prompts, ARM/OS validation and bootstrap prerequisites |
| `mise.toml`, `mise.lock` | Public tasks and the locked helper Python |
| `scripts/with-sudo-askpass.sh` | Sudo authorisation, password helper and cleanup |
| `scripts/setup.py`, `scripts/devsetup/cli.py` | Direct CLI and setup ordering |
| `scripts/devsetup/config.py`, `defaults.toml` | Configuration, OS/profile validation and per-platform defaults |
| `packages/` | Layered TOML inventories; no installation logic |
| `scripts/devsetup/software.py` | Homebrew/mas installation, mise runtimes and maintenance |
| `scripts/devsetup/host.py` | Prerequisites, Git, shell, external dotfiles, macOS preferences and Dock |
| `scripts/devsetup/security.py` | Managed SSH client configuration and Remote Login |
| `templates/` | Managed SSH client/server templates |
| `scripts/devsetup/global_gitignore` | Managed global Git ignore content |
| `.ssh/` | Public SSH keys only; never private keys |
| `scripts/check.py`, `scripts/check-*.py` | Non-installing configuration, host, software and security checks |

## Entry points and configuration

`install.sh [personal|work|--bootstrap-only] [--1password-ssh|--keep-ssh]
[--dotfiles|--skip-dotfiles]` validates the profile, OS, architecture and user
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

Load `defaults.toml`, then explicit repeatable `--config` files. Apply the
selected `[mac]` or `[linux]` table within each file. Later files override
earlier files; explicit feature flags override configuration. Keep platform
paths in these tables and shared preferences outside them. Do not let local
TOML files enable the private security command-injection seams used by tests.
Preserve the documented `remote_login_sshd` list and
`remote_login_launchctl` executable overrides for isolated validation.

Full setup validates prerequisites and refreshes Homebrew before managed SSH,
Git, CLI/fzf, Remote Login, GUI, Zsh, App Store, macOS preferences, Node,
dotfiles and Dock. Preserve this order and each OS/feature guard. A failed
prerequisite or Homebrew refresh must stop before SSH or host writes. Run the
Python process as the normal user; escalate individual operations with sudo.

`mise run packages --profile personal|work` is read-only. Root task settings
must prevent automatic runtime installation during previews and checks.
`--check` bypasses the sudo wrapper. It reports only supported previews;
several host actions deliberately say they are not previewed. Never describe
it as a complete configuration or SSH deployment preview.

## Consent and independent repositories

The SSH prompt defaults to No. Without a terminal, preserve SSH unless
`--1password-ssh` is explicit. Pass `manage_ssh_config` for that run; both OS
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
`Install your dotfiles? [Y/n]` before bootstrap. Enter and unattended runs keep
the default. Both explicit dotfiles flags skip the prompt. Bootstrap-only
runs neither ask about nor install dotfiles. `mise run dotfiles` is the later
explicit installation path.

Delegate installation to the external dotfiles repository's `install.sh`.
Keep portable shell behaviour and agent skills out of this repository. Changes
to another repository need explicit authorisation and a separate linked PR;
never modify a dirty live dotfiles checkout incidentally. The default dotfiles
revision pins the coordinated portable-mise change. Refuse dirty checkouts,
use fast-forward-only branch updates, and honour exact revision pins. Preserve
local branch commits. Refuse to leave unreferenced detached commits behind
until the user saves them on a branch. Back up managed conflict paths before
replacing them.

The external shell activates mise and handles project Node version files.
It must not require nvm or the Homebrew executable. Its `dotfiles.toml` fragment
must coexist with this repository's `dev-machine-setup.toml` under a real
`~/.config/mise/conf.d` directory. Honour `MISE_CONFIG_DIR` and
`XDG_CONFIG_HOME`. Do not overwrite user mise settings or write through
symlinked configuration directories. With dotfiles disabled, configure regular
shell files for Homebrew, mise and fzf. Ubuntu also gets pnpm paths and the
Oh My Zsh/autosuggestions block. Never edit symlinked shell files owned by
another repository.

SSH key filenames, Git identity, dotfiles source and pnpm global packages live
in `defaults.toml`. Profiles change the primary managed GitHub key, not Git
identity. Keep unique timestamped SSH backups inside the security operation
so direct calls cannot bypass them or overwrite an earlier backup. Backups
live under `~/.dev-setup-backups`; leave older backup directories untouched.

Reuse existing sudo authorisation, including NOPASSWD access when `sudo -v`
requires a password under the account's verification policy. Prompt only when
needed and a terminal is available. Keep authorisation alive during the
command, propagate its exit status and remove temporary credential files.

## Package and runtime ownership

Combine `shared/`, `shared/<profile>/`, `<mac|linux>/` and
`<mac|linux>/<profile>/` in that order. Each layer may contain `cli.toml`,
`cli-optional.toml`, `gui.toml`, `gui-optional.toml` and `app-store.toml`.
Create a layer only when it contains packages. Reject unknown inventory paths;
keep the shared required CLI inventory mandatory. Profiles are additive, not
uninstall lists.

Keep desktop apps under `packages/mac/`. Use `os = "macos"` for shared CLI
casks and provide supported Linux tool declarations where needed. Homebrew
handles native formulae and casks, including their post-install steps. The
runner generates Brewfiles from TOML; do not maintain duplicate inventories.
The native mise bottle installer did not create Git's certificate
configuration in clean Ubuntu validation, so it is not the native package
owner for this release. Use mise for runtimes and supported standalone CLI
providers. Use apt only for Ubuntu bootstrap prerequisites and zsh.

Required CLI failures stop setup. Optional CLI, GUI and App Store installation
failures must be reported even when setup continues. Preserve cask adoption
and greedy upgrades where configured. Mac App Store installation requires
sign-in. Remove disabled `tldr` before installing its replacement `tlrc`.

Prove mise's Node executable works and save its default configuration before
unlinking Homebrew Node. Transfer npm globals at their installed versions from
the previous mise runtime, nvm's default and Homebrew Node. Read legacy
providers only before the machine-owned fragment first declares Node; later
runs must respect packages the user uninstalled. Existing target packages win.
Report conflicting versions, linked/unreadable packages and other nvm versions
rather than silently losing them. Honour an explicit npm prefix without
rewriting `.npmrc`. A transfer or configuration failure must retain the old
provider and return failure. Keep old runtimes; do not prune before preserving
their globals. Ensure child tools can find the configured mise executable,
even with an absolute `--mise` path and a minimal `PATH`.

`mise run update` maintains all installed Homebrew formulae/casks regardless of
profile, mise tools, npm/pnpm globals, Mac App Store apps and Ollama models.
Use `mise upgrade --no-prune`. Continue independent maintenance components
after errors, then return failure if any component failed. A missing tool is
skipped, not reported as updated. Do not introduce Ubuntu system upgrades.

## Remote Login safety contract

Remote Login is Mac-only and opt-in per run. Interactive full macOS setup asks
`Configure and enable Remote Login on this Mac? [y/N]` before bootstrap.
Warn first about key replacement, interrupted sessions, phone keys, Tailscale,
policy/firewall review, Shields Up and FileVault. Do not offer it in detected
SSH sessions. Ubuntu, bootstrap-only, unattended, No, Enter and end-of-input
paths leave existing access unchanged; none revokes it. If selected, run the
read-only `remote-login-check` after bootstrap and before the setup sudo
wrapper. A failed preflight stops setup.

`mise run remote-login-check` checks phone keys, Tailscale and the SSH command
path without sudo, writes or service changes. It can run remotely. It does not
deploy configuration, validate effective SSH settings or prove network
isolation. It does not require the Homebrew executable.

`mise run remote-login` explicitly enables access. The separate
`mise run remote-login-revoke` opts in with `revoke_remote_login=true`.
Revocation wins if both flags are true. A false flag leaves earlier changes
in place. Enablement and revocation reject non-Mac, root, invalid profiles
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

Add software to TOML inventories, not Python package lists. Put behaviour in
the responsible domain module and keep the CLI dispatcher explicit. Keep
Mac-only commands behind platform guards. Update this guide and README when
commands or ownership change. Do not add compatibility aliases for removed
Make targets or Ansible tags.

After code or inventory changes, run `mise run check`, or
`python3 -B scripts/check.py` with Python 3.11 or newer. Checks use temporary
directories and substitute commands. They cover the four OS/profile pairs,
terminal prompts, opt-ins, configuration precedence, inventory errors,
headless sudo, backups, revision safety, runtime/global-package migration and
failure propagation. On macOS they also run real unprivileged `sshd -T` gates.
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
