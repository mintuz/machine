# Repository guidance

This repository configures ARM64 macOS and headless Ubuntu development
machines. Both support personal and work profiles. Mise owns runtimes, the
command interface and, through `mise bootstrap`, package installation and
host configuration. Homebrew owns native formulae and casks. Python
standard-library helpers own Remote Login. Make and Ansible are no longer
provisioning engines. Do not add a parallel legacy path.

This is the shared maintenance guide for Codex and Claude Code. `CLAUDE.md`
imports this file; keep project instructions here to avoid divergent copies.
See `README.md` for user-facing commands, security limits and validation.
`ARCHITECTURE-REPORT.md` is historical research, not the current implementation
contract.

## Repository map

| Path | Responsibility |
| --- | --- |
| `install.sh`, `scripts/bootstrap-*.sh` | Consent prompts, ARM/OS validation, bootstrap prerequisites, the profile record and the `mise bootstrap` hand-off |
| `remote-login.sh` | Explicit post-install Remote Login entry point using mise's configured Python |
| `mise.toml`, `mise.lock`, `.miserc.toml` | Public tasks and the `check` task, the locked helper Python, shared `[vars]`, the managed files, private directories, the Git repositories, the shared hooks (Brewfiles, Oh My Zsh, Git settings), the dotfiles installer task and early mise settings |
| `mise.macos.toml`, `mise.linux.toml` | Platform `[vars]`, the login shell, the shell startup blocks, fzf; on macOS also the `packages/mac` Brewfile hooks, the preferences and the Dock |
| `mise.personal.toml` | Brewfile hooks for the `packages/mac/personal` layer |
| `mise.ssh.toml` | The managed SSH client configuration and public keys, selected with `-E <profile>,ssh` |
| `mise/conf.d/tools.toml` | Every mise tool for both platforms and profiles, selected with `os` |
| `scripts/task-env.sh` | Profile resolution sourced by the bootstrap tasks |
| `scripts/shell-block.sh` | Marker-delimited block in a shell startup file; skips symlinks with a notice |
| `scripts/with-sudo-askpass.sh` | Sudo authorisation, password helper and cleanup |
| `scripts/devsetup/cli.py` | The Python entry point: the three Remote Login actions |
| `scripts/devsetup/config.py`, `remote-login.toml` | Remote Login settings and the OS/profile/user guards |
| `packages/` | Literal Homebrew Bundle files per layer; no installation logic |
| `scripts/update.sh` | Shell maintenance of installed Homebrew, mise, npm/pnpm, App Store and Ollama software |
| `scripts/devsetup/security.py` | Remote Login |
| `templates/` | Sources of managed files: the SSH client template, the global Git ignore file and the Remote Login sshd template |
| `.ssh/` | Public SSH keys only; never private keys |
| `scripts/check-security.py` | Non-installing Remote Login checks with stateful substitutes |
| `tests/shell/` | Bats behaviour tests for the installer, the Remote Login launcher, the block helper, sudo authorisation and the updater |

## Entry points and configuration

`install.sh [personal|work|--bootstrap-only] [--skip NAME[,NAME...]]
[--1password-ssh|--keep-ssh] [--dotfiles|--skip-dotfiles]` validates the
profile, OS, architecture and user before bootstrap. Reject Intel, Rosetta,
non-Ubuntu Linux and root. Bootstrap helpers are sourced, not independent
entry points. Keep OS prerequisites, Homebrew installation and the
checksummed mise/locked Python installation in that order; Homebrew must be
on the installer's `PATH` because the bootstrap hooks call `brew`. The mise
release is pinned once, as `min_version` in `mise.toml`;
`scripts/bootstrap-mise.sh` reads it from there and holds the SHA-256 of
each platform's executable. Change the three together; the installer
refuses a download whose checksum does not match. Do not replace this with
`mise.run` (it checks a checksum file from the same release) or with a tool
the fresh machine lacks. After them the installer checks that `git` and
`curl` exist, then runs one
command under the sudo wrapper: `mise -E <profile>[,ssh] bootstrap --yes
[--skip <parts>]` from the checkout. A full run calls no Python. Do not
introduce an Ansible or pip bootstrap dependency. `--bootstrap-only` runs
`mise -E <profile> bootstrap --only files,user --yes` instead: private
directories, the login shell and the shell startup blocks, nothing else.
There is no separate Mac wrapper.

The profile is remembered per machine. A positional profile on `install.sh`
is written as `env = ["<profile>"]` to mise's own per-machine selection file
`$MISE_CONFIG_DIR/miserc.local.toml` (default
`~/.config/mise/miserc.local.toml`, outside the repository, never
committed); only that `env` line is written and an existing one is
replaced. mise then loads `mise.<profile>.toml` for every command on the
machine without `-E`, in this checkout and elsewhere. For one run an
explicit choice wins: the positional profile or `--profile` on a task, or
`DEVSETUP_PROFILE`; the two must agree, and a conflict is refused before
any installation. `DEVSETUP_PROFILE` is never recorded. With neither, the
recorded profile applies. With nothing recorded, full setup requires the
positional profile, `--bootstrap-only` uses personal (its parts are
profile-independent and it records nothing) and the tasks use personal.
The `ssh` environment is selected per run by consent, `--1password-ssh` or
`mise run ssh`; it is never recorded.

`mise run setup [personal|work]` invokes the installer. The other tasks
source `scripts/task-env.sh`, which sets the environment for the run from
`--profile`, `DEVSETUP_PROFILE`, then the `MISE_ENV` that mise passes to
the task (the recorded profile or `-E` on `mise run`), then `personal`. It
also runs `brew shellenv` for the first Homebrew it finds, so the hooks do
not depend on the caller's shell having Homebrew on PATH.
They run `mise -E <env> bootstrap` for a set of parts and assume bootstrap
is complete; they do not prompt for feature choices. `packages` previews
with `--dry-run`; `install` applies every part; `cli` applies
`packages,dotfiles,tools,final-hook`; `git` applies `dotfiles`; `zsh`
applies `repos,user`; `dotfiles` applies `repos,task`; `osx` applies
`macos-defaults`; `ssh` adds `,ssh` and applies `files,dotfiles`. A part's
hooks run with it. Tasks that may need sudo (`install`, `zsh`, `osx`) run
under the sudo wrapper.

Setup values live in the mise files: `[vars]` holds the Git identity, the
Homebrew prefix, the agent socket, the key filenames and the Dock list;
`[bootstrap.repos]` holds the dotfiles source and revision. A machine
overrides them in the gitignored `mise.local.toml` (a later file wins for
`[vars]` and replaces a repository entry by path) or, for platform values,
`mise.<os>.local.toml`. `remote-login.toml` holds only what the Remote
Login commands read: the phone key list, the source addresses, the managed
sshd file and the Tailscale path. `config.py` loads it, then the
gitignored `remote-login.local.toml` in the checkout when it exists; a key
in the local file replaces the default. There is no other settings file
and no `--config` option. Neither file may set detected values (`home`,
`repo_dir`, `platform`, `user`, `profile`) or the per-run choice
(`revoke_remote_login`). Do not let local TOML files enable the private
security command-injection seams used by tests: `config.py` refuses the
test-only keys by name, and `check-security.py` injects them by calling
`security.run` with a dictionary, never through a file. Preserve the
documented `remote_login_sshd` list and `remote_login_launchctl`
executable overrides, which the local file may set for isolated
validation. The profile comes from the command line or `DEVSETUP_PROFILE`,
never from `remote-login.toml`.

`--skip` takes `mise bootstrap` part names, validated against the list in
`mise bootstrap --help` and passed through unchanged; a part's hooks are
skipped with it. Two repository names are added for what parts cannot
express: `gui` and `app-store`. The installer exports
`DEV_MACHINE_SKIP=<names>` and each `Brewfile.gui` and
`Brewfile.app-store` hook command tests it with a `case`, printing a
notice instead of running `brew bundle`; `Brewfile.cli` still installs.
Other names are refused with the valid list. The old repository names map
as: `cli` → `packages,tools`; `gui` → `gui`; `app-store` → `app-store`;
`zsh` → `user`; `osx` → `macos-defaults`; `dotfiles` → `--skip-dotfiles`
(`repos,task` without the prompt); `ssh` → `--keep-ssh`. `--skip user` also
skips Oh My Zsh and the plugin clone, as the old `zsh` step did;
`--skip repos,task` keeps them. `--skip dotfiles`
now means the mise `dotfiles` part (the managed files). Contradictory
explicit flags fail. Bootstrap and the prerequisite check cannot be
skipped. Revocation is a separate operation and must never be suppressed
by a skip.

The installer resolves consent before bootstrap: the SSH choice adds the
`ssh` environment, the dotfiles choice adds `--skip repos,task`. The
installer always leaves Remote Login alone; access setup is a later explicit
operation. Full setup runs the mise phases in mise's order: Brewfile hooks,
fzf, private directories, repositories, managed files, Git settings, macOS
preferences with the post-defaults hook, Oh My Zsh, login shell, shell
blocks, tools, the dotfiles installer task, the final hook. The Brewfile
hooks set `HOMEBREW_NO_AUTO_UPDATE=1`; the installer's prerequisite
bootstrap has its own refresh and there is no other. Run mise as the normal
user; mise and the hooks escalate individual operations with sudo.

`mise run packages [--profile personal|work]` is read-only: it runs
`mise -E <env> bootstrap --dry-run`, which prints every hook command,
the files, repositories, preferences and tools that would change. Hooks are
printed, not run. Root task settings must prevent automatic runtime
installation during previews and checks. `--check` on the Remote Login
commands bypasses the sudo wrapper and reports the preflight only.

## Consent and independent repositories

The SSH prompt defaults to No. Without a terminal, preserve SSH unless
`--1password-ssh` is explicit. Consent selects the `ssh` mise environment
for that run; nothing selects it by default and the record never includes
it. Declining must leave existing SSH files and agents untouched, including
a configuration from an earlier opt-in. The explicit `mise run ssh` task
opts in without a prompt.

`mise.ssh.toml` declares `~/.ssh/config` as a template of
`templates/ssh_config` with mode `0600` and the two public keys as `0600`
copies; `[bootstrap.directories]` in `mise.toml` keeps `~/.ssh` and
`~/.gnupg` at `0700`. The template takes the agent socket from the platform
file's `vars.ssh_agent_socket` and the primary GitHub key from the profile
in `mise_env`. Before the first apply, the installer and the `ssh` task run
`mise dot track --yes ~/.ssh/config` when the file exists, so mise history
holds the previous file (`mise dot history`, `mise dot rollback`); this
adds a tracking entry to the user's global mise configuration. There is no
other backup of `~/.ssh`. 1Password itself comes from `Brewfile.gui` in the
packages phase, before the files are written; enabling its agent and
signing in remain manual. The Mac app and shared CLI inventories remain
independent of the SSH choice. On Ubuntu, an existing `SSH_AUTH_SOCK`
selects the literal `IdentityAgent "SSH_AUTH_SOCK"`, not a temporary socket
path; otherwise use `~/.1password/agent.sock`. Headless users forward their
client agent. Do not install the Linux desktop app during headless bootstrap.

Dotfiles default to enabled on both OSes. Interactive Ubuntu full setup asks
`Install your dotfiles? [Y/n]` before bootstrap. Enter and unattended runs
keep the enabled default. The explicit `--dotfiles` and `--skip-dotfiles`
flags skip the prompt; `--skip repos` or `--skip task` are raw part
exclusions and do not. Bootstrap-only runs neither ask about nor install
dotfiles. `mise run dotfiles` is the later explicit installation path.

Delegate installation to the external dotfiles repository's `install.sh`,
which `[tasks.bootstrap]` runs as the last bootstrap step. Keep portable
shell behaviour and agent skills out of this repository. Changes to another
repository need explicit authorisation and a separate linked PR; never
modify a dirty live dotfiles checkout incidentally. `[bootstrap.repos]` in
`mise.toml` declares `~/.dotfiles` with `ref = "master"`; a machine pins
another branch, tag or commit by replacing that entry in `mise.local.toml`.
mise clones a missing checkout and, on each apply, fetches and
fast-forwards a clean checkout to the ref. mise refuses a dirty worktree
(including untracked files), a different `origin`, a non-Git directory and
a non-fast-forward move; it never resets local work or rewrites `origin`.
mise compares `git@host:path`, `ssh://git@host/path` and
`https://host/path` as the same origin and everything else, including
local paths and `file://` URLs, byte for byte. mise does not check for
unreferenced detached commits before moving a pinned checkout. The external
installer owns conflict backups (`~/.dotfiles-backup.*`); this repository
backs up nothing before running it.

The external shell activates mise and handles project Node version files.
It must not require the Homebrew executable. Its `dotfiles.toml` file must
coexist with this repository's `dev-machine-setup.toml` symlink under a real
`~/.config/mise/conf.d` directory. mise creates that symlink from the
`[dotfiles]` entry in `mise.toml`; it refuses to replace an existing regular
file there. Apart from that link, the SSH tracking entry and the `env`
line of `miserc.local.toml`, setup never writes the user's own mise files.
The entry targets mise's default global directory; `MISE_CONFIG_DIR` and
`XDG_CONFIG_HOME` do not move it.

Shell startup files may belong to the external dotfiles, so no
`[dotfiles]` block entry or `[bootstrap.mise_shell_activate]` entry targets
them: mise refuses to edit a symlinked target and stops bootstrap. Instead
the `post-user` hooks call `scripts/shell-block.sh`, which appends or
updates a `# BEGIN/END <marker>` block in a regular file and leaves a
symlink unchanged with one notice. The `dev-machine mise` block (Homebrew
`shellenv`, `mise activate` with the absolute mise path, the fzf source
line) goes in `~/.zshrc` on both platforms and `~/.bashrc` on Ubuntu; Ubuntu
also gets the `dev-machine oh-my-zsh` block in `~/.zshrc` and the
`dev-machine Node and pnpm` block in `~/.bashrc`. The fzf `post-packages`
hook runs the formula's installer with `--no-update-rc` and skips with a
notice when fzf is absent. The Oh My Zsh `pre-user` hook runs the upstream
installer with `RUNZSH=no CHSH=no KEEP_ZSHRC=yes` only when `~/.oh-my-zsh`
is missing, after creating an empty `~/.zshrc` if none exists so the
installer never writes its template; it then clones the
`zsh-autosuggestions` plugin into the custom plugins directory or
fast-forwards the existing clone. The plugin is not a `[bootstrap.repos]`
entry: the repos phase runs before `pre-user`, and the upstream installer
refuses an existing `~/.oh-my-zsh`. The Ubuntu zsh block sources
`oh-my-zsh.sh` only when the file exists. The login shell is declared in `[bootstrap.user]` per
platform file, but mise's own `chsh` runs as the user and asks for the
account password, which a key-only server account may lack; the `pre-user`
hook therefore sets the shell with `{{ vars.sudo }} chsh` first and mise
only verifies it. `vars.sudo` (in `mise.toml`) renders to `sudo -A` when
the wrapper exported `SUDO_ASKPASS` and to `sudo -n` otherwise; use it for
every sudo call in a hook.

Git identity lives in `[vars]`; profiles change the primary managed GitHub
key, not Git identity. The `post-dotfiles` hook applies the global Git
settings after the `copy` entry writes `~/.global_gitignore`; the copy
overwrites a changed target.

Mac preferences are typed `[bootstrap.macos.defaults]` entries in
`mise.macos.toml`; mise writes only unset or differing values and never
deletes one. The two home-relative values, the Dock
`expose-animation-duration`, Library visibility, the system-wide update
check (`vars.sudo`), `killall Finder` and the Dock are the `post-defaults`
hook. `expose-animation-duration` is a hook line because `defaults write
-float` stores a 32-bit float that never equals the 64-bit `0.1` mise
compares, so a typed entry would be rewritten on every run. The Dock list
is `vars.dock_tiles`, one absolute `.app` path or `spacer` per line,
validated by `mise run check`; the hook removes every tile, adds each line
with `dockutil`, reports and skips a missing app or spacer, and restarts
the Dock. An empty list leaves the Dock unchanged. `--skip macos-defaults`
skips the preferences and the hook together. Do not restore the removed
automatic `LSQuarantine=false` preference.

Reuse existing sudo authorisation, including NOPASSWD access when `sudo -v`
requires a password under the account's verification policy. Prompt only when
needed and a terminal is available. Keep authorisation alive during the
command, propagate its exit status and remove temporary credential files.

## Package and runtime ownership

Brewfiles live in `packages/shared/`, `packages/shared/<profile>/`,
`packages/mac/` and `packages/mac/<profile>/`. Each layer may contain
`Brewfile.cli`, `Brewfile.gui` and `Brewfile.app-store`; every file is
optional, and there is no Linux layer. Brewfiles use plain Homebrew Bundle
syntax. `mise bootstrap` installs them from `[bootstrap.hooks.pre-packages]`
entries, one `brew bundle install --file=<layer file>` with
`HOMEBREW_NO_AUTO_UPDATE=1` per file: shared layers in `mise.toml`, the
`mac` layer in `mise.macos.toml` (loaded on macOS by `auto_env`) and
profile layers in `mise.<profile>.toml` (loaded with `-E <profile>`). mise
appends hooks in that load order, so files apply as shared, mac, then the
profile layers; each file is self-contained and `brew bundle` is idempotent,
so the order does not change the result. A hook for a Mac-only layer in a
profile file renders as a no-op comment on Linux through
`{% if os() == "macos" %}`. Add a hook line when you add a layer file;
create a layer only when it contains packages. Profiles are additive, not
uninstall lists.

mise tools are declared once, in `mise/conf.d/tools.toml`. Give a
platform-specific entry `os = ["linux"]` or `os = ["macos"]`; put a tool
that one profile needs in `mise.personal.toml` or `mise.work.toml`. The
`[dotfiles]` entry in `mise.toml` links `mise/conf.d/tools.toml` to
`~/.config/mise/conf.d/dev-machine-setup.toml`, so the tools are active in
every directory. `mise.lock` covers the helper Python only: the tools
request `latest` or `lts`, and `mise run update` upgrades them in place.

Keep casks under `packages/mac/`. Declare a Linux provider for a CLI cask
as a `[tools]` entry with `os = ["linux"]` where one exists. Homebrew handles
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

`Brewfile.cli` hooks are fatal: a failure stops bootstrap before the tools
link and `mise install`. `Brewfile.gui` and `Brewfile.app-store` hooks are
Mac-only; the App Store hook runs `mdimport /Applications` first so mas can
see installed apps. Their failures let bootstrap continue: the hook appends
one line to `$XDG_STATE_HOME/dev-machine-setup/bootstrap-issues` (default
`~/.local/state/...`), and `[bootstrap.hooks.final]` in `mise.toml` prints
the lines, deletes the file and returns failure. The first shared hook
deletes a stale file. Never repair Homebrew state or delete backups
automatically. Mac App Store installation requires sign-in. A package that
an inventory replaced, such as the disabled `tldr` formula or the
`claude-code@latest` cask, must be removed by hand; setup no longer
uninstalls anything.

The `post-packages` hook owns the fzf key bindings and completion and needs
the `fzf` formula from `Brewfile.cli`. Node, pnpm and the `npm:` providers
are ordinary entries in `mise/conf.d/tools.toml`, installed by the `tools`
part. The external dotfiles export `PNPM_HOME` for zsh; the Ubuntu
`~/.bashrc` block exports it for bash. Native prerequisites of selected
components remain allowed; exclusions are not an uninstall/package-denial
policy. Hooks run in the installer's environment, not with `[tools]` on
`PATH`; they see the installer's exported variables such as
`DEV_MACHINE_SKIP`. The `mise activate` line in the shell blocks uses
`$HOME/.local/bin/mise`, the link bootstrap keeps, so the block is
byte-identical whichever mise ran bootstrap.

`mise run update` runs `scripts/update.sh`, a Bash script without Python
or the sudo wrapper. It maintains all installed software regardless of
profile; `--skip` does not apply. In order:
`brew update`, `brew upgrade` with Homebrew's default non-greedy semantics,
`brew cleanup -s`, `mise upgrade --no-prune`, `npm update -g` and
`pnpm update -g` through `mise exec`, `mas upgrade` on macOS and
`ollama pull` for each listed model. Skip a component whose tool is absent
and print why; pnpm also needs `PNPM_HOME`. Continue after a failed
component, print a summary with one line per component and return failure
if any component failed. Do not introduce Ubuntu system upgrades.

## Remote Login safety contract

Remote Login is Mac-only and opt-in per run. The initial installer must
not offer an enablement prompt or run the Remote Login preflight; it runs
no Python at all, so missing Tailscale or phone keys cannot stop software
installation, and local files that enable that step have no effect on it.

After installation, use `./remote-login.sh`. Keep this launcher thin:
resolve the repository's Python through mise, then invoke the existing
`remote-login` action in `scripts/devsetup/cli.py`, the only Python entry
point. That action checks prerequisites before sudo or service changes; do
not chain a duplicate preflight. Find mise on PATH or at the bootstrap link
`~/.local/bin/mise`. Keep the direct mise tasks available.

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
`mise run remote-login-revoke` sets the per-run `revoke_remote_login`
choice, as does the direct `remote-login --revoke-remote-login` command;
revocation wins over enablement in the same run. Neither choice is stored
in a file. Enablement and revocation reject non-Mac, root, invalid profiles
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

Add software to the layer Brewfiles and `mise/conf.d/tools.toml`, not
Python package lists; a new layer file also needs its hook line. Put host
configuration in the mise files as declarative entries first and hooks
second; keep the CLI dispatcher explicit. Keep Mac-only entries in
`mise.macos.toml`.
Update this guide and README when
commands or ownership change. Do not add compatibility aliases for removed
Make targets or Ansible tags.

After code or inventory changes, run `mise run check`. It is a mise task
(`[tasks.check]` in `mise.toml`) that depends on `check-shell` (Bats),
then parses every tracked TOML file and validates the Dock list, runs
`bash -n` and, when installed, ShellCheck on the shell entry points, runs
`python3 -B scripts/check-security.py`, and runs `mise -E personal|work
config`, `mise -E personal bootstrap plan` and `mise -E work bootstrap
--dry-run` with an empty `HOME` so the machine's own files never make a
preview refuse. It needs the locked Python and `bats` on PATH.
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

Checks use temporary directories and substitute commands. Bats covers the
installer's refusals, the profile record, the `--skip` translation and the
`mise bootstrap` hand-off; the task profile precedence in
`scripts/task-env.sh`; the Remote Login launcher
with the real `cli.py`, including the local settings file, the refused
test-only keys and the prerequisite check before any service change; the
shell block helper; headless sudo; and the updater. `check-security.py`
covers Remote Login backups and failure propagation; on macOS it also runs
real unprivileged `sshd -T` gates. Stateful service substitutes cover
stop-before-write, rollback, offline final-key revocation and partial
activation failures without changing host services. The mise declarations
are checked by mise itself: inspect them with `mise run packages
[--profile personal|work]` (`mise -E <env> bootstrap --dry-run`),
`mise -E <env> config` for the loaded files and `mise bootstrap status`
for drift.

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
