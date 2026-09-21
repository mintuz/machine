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
| `ansible/tasks/mac/` | Mac GUI, App Store, system preferences, and Dock tasks |
| `ansible/templates/` | SSH configuration and global Git ignore templates |
| `.ssh/` | Public SSH keys used by managed SSH setup; never private keys |
| `ansible.cfg`, `inventory`, `requirements.yaml` | Local Ansible execution and collection dependencies |
| `scripts/check-platforms.py`, `scripts/check-safety.py` | Routing and safety regression checks |

## Entry points

- `install.sh [personal|work|--bootstrap-only] [--1password-ssh|--keep-ssh]`
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

The SSH prompt defaults to No. Without a terminal, preserve SSH unless
`--1password-ssh` is explicit. Pass the selection as `manage_ssh_config` to
Ansible; both OS defaults are false. The choice is per run, not persisted.
Declining must leave existing SSH files and agents untouched, including a
configuration installed by an earlier opt-in. Tagged Make commands do not
prompt; direct SSH setup requires `-e manage_ssh_config=true`.

Bootstrap runs as the normal user, then invokes `local.yaml` through the sudo
wrapper. Setup selects the platform and inventories, validates prerequisites,
and updates Homebrew before running SSH, Git, CLI, GUI, Zsh, App Store, macOS
preferences, Node, dotfiles, and Dock tasks in that order. OS and feature guards
skip inapplicable tasks. Bootstrap helpers are sourced by `install.sh`, not
standalone entry points; do not duplicate their work in an Ansible bootstrap.

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
Ubuntu skips the external dotfiles. `make dotfiles` explicitly opts in; the external
repository must support Linux before enabling it. It currently contains
hardcoded Mac shell paths. Never modify that external repository as an
incidental part of machine setup work.

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
OS/profile combinations and SSH opt-in/opt-out, plus terminal prompt and flag
checks with inert bootstrap scripts. Safety checks use temporary
directories and fake commands. Use `make packages PROFILE=personal` and
`make packages PROFILE=work` to inspect actual inventory selection on the host.
ShellCheck can also check the Bash entry points and sourced bootstrap scripts.

Use a disposable machine or container for real bootstrap/install/update checks;
do not run full setup on the development host merely to validate an edit.
Syntax checks and mocked facts do not establish fresh-machine installation
or interactive shell behavior; report those evidence limits explicitly.
