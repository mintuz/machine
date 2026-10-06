# Repository guidance

This repository configures macOS and headless Ubuntu development machines
using Ansible and Homebrew. Both support personal and work profiles.

This is the shared maintenance guide for Codex and Claude Code. `CLAUDE.md`
imports this file; keep project instructions here to avoid divergent copies.
See `README.md` for user-facing setup instructions and validation history.

## Repository map

| Path | Responsibility |
| --- | --- |
| `install.sh`, `scripts/bootstrap-*.sh` | OS detection and bootstrap prerequisites |
| `makefile` | Profile selection and shortcuts for setup, updates, and checks |
| `scripts/with-sudo-askpass.sh` | Sudo authorization, password helper, and cleanup |
| `local.yaml` | Setup task ordering and platform/feature guards |
| `update.yaml`, `ansible/tasks/update.yaml` | Maintenance of installed tools |
| `defaults.yaml` | Shared user preferences and default profile |
| `ansible/vars/{mac,linux}.yaml` | OS paths and SSH/dotfiles defaults |
| `ansible/tasks/platform.yaml` | OS/profile validation and inventory selection |
| `packages/` | Homebrew package inventories; no installation logic |
| `ansible/tasks/` | Shared SSH, Git, CLI, shell, Node, and dotfiles tasks |
| `ansible/tasks/mac/` | Mac GUI, App Store, system preferences, Remote Login, and Dock tasks |
| `ansible/templates/` | SSH client and server configuration and global Git ignore templates |
| `.ssh/` | Public SSH keys used by managed SSH setup and Remote Login; never private keys |
| `ansible.cfg`, `inventory`, `requirements.yaml` | Local Ansible execution and collection dependencies |
| `scripts/check-platforms.py`, `scripts/check-safety.py` | Routing and safety regression checks |

## Entry points

- `install.sh [personal|work|--bootstrap-only] [--1password-ssh|--keep-ssh] [--dotfiles|--skip-dotfiles]`
  detects the OS, asks about 1Password SSH before bootstrap, and sources
  `scripts/bootstrap-macos.sh` or `scripts/bootstrap-ubuntu.sh`; both use
  `scripts/bootstrap-homebrew.sh` for Homebrew and Ansible prerequisites.
- `new-mac.sh` is the legacy Mac bootstrap-only wrapper.
- `local.yaml` runs setup; `update.yaml` runs maintenance.
- `make personal` and `make work` bootstrap and configure their profiles.
- Tagged targets such as `make cli PROFILE=work` assume bootstrap is complete.
- `make packages PROFILE=work` previews selected inventories without writes.
- `make check` runs shell syntax, package-selection checks, Brewfile parsing,
  safety regressions, and Ansible syntax checks without installing packages.
- `make remote-login-check` runs only the shared Remote Login prerequisites
  in Ansible check mode, without sudo. It checks keys, Tailscale, and Homebrew;
  it does not deploy configuration, validate effective SSH settings, or
  change services or keys. It can run from a remote session.
- `make remote-login` turns on Remote Login (SSH) for tailnet key logins on
  macOS. It passes `manage_remote_login=true`; the Mac default is false, and
  full setup does not prompt for it. Its command wrapper runs the read-only
  preflight before requesting sudo.
- `make remote-login-revoke` is a separate Mac-only opt-in. It passes
  `revoke_remote_login=true` with the `remote-login-revoke` tag; the default
  is false. It disables SSH startup/listener and backs up then clears the
  invoking user's `authorized_keys`, without requiring Homebrew, Tailscale,
  or phone keys. None of the Remote Login commands changes Shields Up.
  If both flags are true, skip enablement and run revocation.
  `scripts/remote-login.sh` rejects non-macOS, root, invalid profiles, and
  missing Ansible before requesting sudo. Enablement and revocation refuse
  detected SSH sessions (`SSH_CONNECTION`, `SSH_CLIENT`, or `SSH_TTY`).
  The Ansible tasks also enforce this session check outside check mode.
  These environment checks are an operator guard, not proof of local-console
  use. Do not bypass them by clearing variables.

The SSH prompt defaults to No. Without a terminal, preserve SSH unless
`--1password-ssh` is explicit. Pass the selection as `manage_ssh_config` to
Ansible; both OS defaults are false. The choice is per run, not persisted.
Declining must leave existing SSH files and agents untouched, including a
configuration installed by an earlier opt-in. Tagged Make commands do not
prompt; direct SSH setup requires `-e manage_ssh_config=true`.

Dotfiles default to enabled on both OSes. Ubuntu full setup asks
`Install your dotfiles? [Y/n]` before bootstrap; Enter and unattended runs
keep the default. Pass the answer as `install_dotfiles` to Ansible.
`--dotfiles` and `--skip-dotfiles` work on both OSes and skip the prompt.
Bootstrap-only runs do not ask about or install dotfiles. Tagged Make commands
use the OS defaults without prompts; direct Ansible runs can override them.

Bootstrap runs as the normal user, then invokes `local.yaml` through the sudo
wrapper. Setup selects the platform and inventories, validates prerequisites,
and updates Homebrew before running SSH, Git, CLI, Remote Login, GUI, Zsh, App
Store, macOS preferences, Node, dotfiles, and Dock tasks in that order. OS and
feature guards skip inapplicable tasks. Bootstrap helpers are sourced by
`install.sh`, not standalone entry points; do not duplicate their work in an
Ansible bootstrap.

Both playbooks load `defaults.yaml` and select platform defaults before their
work. Ansible extra variables (`-e`) override these defaults. Make passes
`PROFILE` as `machine_type`; it defaults to `personal` on each invocation.
`make update` updates all installed tools, regardless of their package layer.

## Package ownership

Keep inventory under `packages/`. The selector combines `shared/`,
`shared/<profile>/`, `<mac|linux>/`, and `<mac|linux>/<profile>/` in that order.
Each layer may contain `Brewfile.cli`, `Brewfile.cli-optional`, `Brewfile.gui`,
`Brewfile.gui-optional`, and `Brewfile.app-store`. Create missing layers only
when there are packages to put in them. Profiles are additive, not uninstall
lists. Keep Mac desktop apps under `packages/mac/`; CLI casks may be shared
when their package supports Linux. Required CLI failures stop setup;
optional CLI and GUI installation failures are reported and tolerated.
Reject unknown inventory paths and keep the shared CLI inventory required.
Report failed App Store installations even though setup continues.

For example, add a CLI needed by both work platforms to
`packages/shared/work/Brewfile.cli`; a personal Ubuntu-only CLI belongs in
`packages/linux/personal/Brewfile.cli`. No Linux inventory exists yet because
Ubuntu currently uses only shared packages. Do not create empty placeholders.

## Platform boundaries

Select the OS and profile through `ansible/tasks/platform.yaml` before setup
or update tasks. Keep platform paths and defaults in `ansible/vars/`.
Put Mac-only tasks under `ansible/tasks/mac/` and guard their imports in
`local.yaml`. Use Homebrew for shared development tools and apt for Ubuntu
bootstrap prerequisites. Do not add Mac-only commands to shared tasks.

Both platforms preserve existing SSH configuration and agents by default.
Dotfiles installation delegates to the external repository's `install.sh`;
`make dotfiles` installs or refreshes them on either OS. The external shell
configuration still contains hardcoded Mac paths, so distinguish installation
from verified Linux shell compatibility. Never modify that external repository
as an incidental part of machine setup work.

When opting in, the 1Password agent must be enabled separately. Mac bootstrap
installs the desktop app early only when requested for SSH. The software
inventories still include the Mac password manager and shared CLI regardless
of SSH choice. On Ubuntu, an existing `SSH_AUTH_SOCK` selects the literal
`IdentityAgent "SSH_AUTH_SOCK"`, not its temporary socket path; otherwise use
`~/.1password/agent.sock`. Headless users forward their client agent. Do not
install the Linux desktop app as part of headless bootstrap. Mac App Store
installation requires the App Store to be signed in.

SSH public key filenames, Git name/email, dotfiles source,
and pnpm global packages are configured in `defaults.yaml`. Profile selection
changes the primary SSH key but does not invent a different Git identity.
Keep SSH backups before managed SSH writes and use per-task privilege
escalation rather than running the playbook as root.
Keep backups inside the SSH task with unique timestamps so direct or mixed
tag runs cannot bypass them or overwrite an earlier backup. Refuse to discard
local changes in the external dotfiles checkout.

Reuse existing sudo authorization on headless machines; prompt only when it
is needed and a terminal is available. Keep sudo authorization alive while
the command runs and remove temporary credential files on exit.

Remote Login is Mac-only and opt-in per run, like managed SSH: a false flag
leaves earlier changes in place. Keep normal post-unlock SSH key-only and
limited to tailnet source addresses; do not extend that promise to
FileVault's pre-unlock password SSH. Source restrictions do not bind the
wildcard listener or stop Bonjour advertising. Shields Up is not a LAN
firewall.

Keep the limits in the managed file's `Match all` block, because `Match`
settings override global settings in every file; keep key sources
(`AuthorizedKeysFile`, `AuthorizedKeysCommand`, `TrustedUserCAKeys`) and
`PubkeyAuthentication yes` pinned there. Disable SSH startup and unload any
listener before snapshotting or deploying configuration. Reject
symlink/non-regular managed configuration files and snapshot prior content,
owner, group, and mode.
Validate with `sshd -t` and check effective settings with `sshd -T`
(`remote-login-check.yaml`). Stop if sshd does not read the managed file,
another file weakens the limits or adds a `Match` block, or a setting such
as `DenyUsers`, `RefuseConnection`, or `ForceCommand` could block the account.
Refuse those settings instead of overriding them: a later `Match` block can
still add `AllowUsers` entries. If deployment or the gate fails, restore
the prior file and metadata, or remove the new file if previously absent.
Leave Remote Login disabled and report the original failure.

Only after the gate succeeds may keys, the access list, and startup change.
If activation or the port check fails, disable startup and unload again.
Never suggest manual enablement after a failed run. Run from the local
console and warn that existing sessions may be interrupted. Stopping the
listener and removing keys do not reliably terminate existing SSH or mosh
sessions; incident response must inspect and terminate affected processes
without indiscriminately killing herdr or local terminal sessions.

Use macOS's `/usr/sbin/sshd` and `/usr/bin/ssh-keygen` by default, because
Homebrew OpenSSH uses other configuration paths. Preserve the existing
`remote_login_sshd` list override for isolated validation. All launchctl
commands use `remote_login_launchctl | default('/bin/launchctl')` so tests
can substitute a stateful executable that rejects unexpected operations.
Enablement requires a nonempty list of key files, each containing one
public key line without options. Back up `authorized_keys` under
`~/.dev-setup-backups` before each change; listed keys replace the whole
file. Removing the final key uses the separate revoke path, never empty-key
enablement. Keep revocation independent of Tailscale status, Homebrew, and
public-key inputs; retain the managed SSH configuration.

Never change Shields Up or rewrite the control-server policy automatically.
README setup must require a local firewall and review of all additive
grants and legacy ACLs before activation, removing or narrowing matching
broad rules. Require allow/deny policy tests, with the provider's
administrator if necessary. Keep Shields Up on until setup and policy
checks succeed, then document only explicit manual release. Keep network
examples fictional and the iPhone, firewall, and incident steps manual.

Use `ansible_facts` rather than deprecated injected fact variables. Preserve
Homebrew Node until a working nvm default exists, and install Node before
unlinking its previous provider. Propagate installer errors; runtime updates
may continue independent components but must return failure at the end when
any component failed. A missing tool is skipped, not reported as updated.

## Making and validating changes

Add software to its Brewfile rather than embedding package lists in tasks.
For new configuration behavior, edit the responsible task and wire it through
`local.yaml` only if it needs a new task file. Preserve task tags so both full
setup and targeted commands work. Platform selection must retain `always`;
inventory preview must remain read-only. Keep OS defaults separate from shared
user preferences and update this guide and `README.md` when commands change.

After code or inventory changes, run `make check` with Homebrew, Ansible,
Python 3, and the collections from `make deps` available. It covers all four
OS/profile combinations and SSH/dotfiles defaults and overrides, plus terminal
prompt and flag checks with inert bootstrap scripts. On macOS it also checks
the effective Remote Login SSH server settings with an unprivileged `sshd -T`,
configuration rollback, and stop-before-write behaviour. A stateful `launchctl`
substitute covers offline final-key revocation, check mode, and partial
activation failure without changing host services.
Safety checks use temporary directories and fake commands. Use
`make packages PROFILE=personal` and `make packages PROFILE=work` to inspect
actual inventory selection on the host.
ShellCheck can also check the Bash entry points and sourced bootstrap scripts.

Use a disposable machine or container for real bootstrap/install/update checks;
do not run full setup on the development host merely to validate an edit.
Syntax checks and mocked facts do not establish fresh-machine installation
or interactive shell behavior; report those evidence limits explicitly.
Remote Login's `--check --diff` mode is limited: it skips deployment, the
effective-settings gate, and activation. Do not describe it as a full SSH
configuration preview. A real enable run needs sudo and phone keys;
revocation needs sudo but no keys or Tailscale connection. Only an actual
phone connection and denied
network paths establish end-to-end access and isolation. Never exercise
real activation or revocation on the development host just to validate
an edit.
