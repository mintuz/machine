# Development Machine Setup

Set up macOS and Ubuntu development machines with Ansible and Homebrew.
Both operating systems support personal and work profiles. Ubuntu defaults
to a headless setup without desktop apps. Dotfiles install by default on both
platforms, with a startup opt-out prompt on Ubuntu. Both platforms ask whether
to configure the 1Password SSH agent before bootstrap starts.

## Quick start

Run as your normal user with sudo access:

```bash
./install.sh personal
# or
./install.sh work
```

The SSH prompt defaults to **No**, preserving the existing SSH configuration
and agent. **Yes** backs up and replaces SSH configuration with the 1Password
agent and this repository's personal/work GitHub public keys. Check those keys
before opting in. The choice applies to that run; it is not saved.

For unattended runs, use an explicit flag. Without a terminal or flag, setup
preserves SSH:

```bash
./install.sh work --1password-ssh
./install.sh personal --keep-ssh
```

On Ubuntu, full setup also asks `Install your dotfiles? [Y/n]` before
bootstrap. Press Enter to install or answer No to skip. Without a terminal,
dotfiles install by default. Use these flags to choose without a prompt:

```bash
./install.sh work --skip-dotfiles
./install.sh personal --dotfiles
```

Both flags work on macOS too. Bootstrap-only runs do not install dotfiles or
ask about them. The choice applies to one run; `make dotfiles` installs them
later. The external dotfiles still contain Mac-specific shell paths; see the
compatibility note below before using the resulting shell on Linux.

On macOS, bootstrap first if you want 1Password SSH and still need to sign in:

```bash
./install.sh --bootstrap-only --1password-ssh
# Open 1Password, sign in, and enable its SSH agent.
./install.sh personal --1password-ssh
```

Sign in to the Mac App Store before installing its apps. Public GitHub keys
for managed SSH configuration are stored under `.ssh/` in this repository.
`new-mac.sh` remains a shortcut for Mac bootstrap only.

On Ubuntu, bootstrap installs apt prerequisites, Homebrew, and Ansible.
Opting into 1Password SSH uses `SSH_AUTH_SOCK` when it is set, allowing a
forwarded 1Password agent to follow each session's socket. Otherwise it uses
`~/.1password/agent.sock`, which requires an already configured local 1Password
app. Ubuntu setup does not install that desktop app. On a headless server,
[forward the agent from your client](https://www.1password.dev/ssh/agent/forwarding)
before opting in. Setup does not sign in to 1Password or enable the agent itself.

The SSH choice controls SSH configuration, not the software inventory:
1Password remains a Mac GUI package, and its CLI remains a shared package.
Declining on a later run leaves the existing configuration in place; it does
not undo an earlier opt-in.

For unattended setup, configure passwordless sudo for the setup user.
Ansible commands reuse and refresh existing sudo authorization. If a password
is needed, run from a terminal; the wrapper fails clearly when no terminal is
available and removes its temporary password helper when the command exits.

## Commands

| Command | Action |
| --- | --- |
| `make` / `make personal` | Bootstrap and run personal setup |
| `make work` | Bootstrap and run work setup |
| `make setup` | Bootstrap only |
| `make deps` | Install Ansible collections |
| `make packages PROFILE=work` | Preview selected inventories without changing the machine |
| `make cli PROFILE=work` | Install shared, OS, and work CLI tools |
| `make install PROFILE=work` | Run tasks tagged install |
| `make gui` | Install Mac applications; skipped on Ubuntu |
| `make app-store` | Install Mac App Store apps; skipped on Ubuntu |
| `make osx` / `make dock` | Configure macOS preferences / Dock; skipped on Ubuntu |
| `make git PROFILE=work` | Configure Git using the configured name and email |
| `make node` | Install nvm-managed Node LTS and configure pnpm |
| `make dotfiles` | Install or refresh the external dotfiles on either OS |
| `make update` | Update installed Homebrew packages, CLI casks, and runtime tools; App Store only on Mac |
| `make check` | Check routing, safety regressions, Brewfile parsing, shell syntax, and Ansible syntax |

Tagged commands assume bootstrap has already run. `PROFILE` defaults to
`personal`; it is not remembered between invocations. `make personal`,
`make work`, and `make setup` use the startup SSH prompt. Tagged Make commands
do not prompt and leave SSH configuration alone by default. `make personal` and
`make work` explicitly select their named profile.

## Package inventory

Each setup combines four layers, in this order:

1. `packages/shared/`
2. `packages/shared/<personal|work>/`
3. `packages/<mac|linux>/`
4. `packages/<mac|linux>/<personal|work>/`

The current files are:

```text
packages/
├── shared/
│   └── Brewfile.cli
└── mac/
    ├── Brewfile.cli
    ├── Brewfile.cli-optional
    ├── Brewfile.gui
    ├── Brewfile.app-store
    ├── personal/
    │   └── Brewfile.gui
    └── work/
        └── Brewfile.gui
```

Create `packages/linux/Brewfile.cli` only when there is a Linux-only tool.
For a work CLI on both systems, add it to
`packages/shared/work/Brewfile.cli`. For a personal Ubuntu addition, use
`packages/linux/personal/Brewfile.cli`. Missing optional layers need no files.

Each layer may contain `Brewfile.cli`, `Brewfile.cli-optional`,
`Brewfile.gui`, `Brewfile.gui-optional`, and `Brewfile.app-store`.
GUI and App Store inventories are executed only on macOS. Keep desktop
applications under `mac/`; Ubuntu desktop application setup is not implemented.
Use the CLI inventories for CLI casks such as Codex and Notion CLI.

CLI inventory failures stop setup; optional CLI and GUI installation failures
are reported and setup continues. App Store installation is also best effort;
failed app IDs are printed. Missing required inventories and misspelled
inventory paths stop setup. Profile layers are additive: switching
profiles does not uninstall the previous profile's packages. `tlrc` replaces
the disabled `tldr` formula and still provides the `tldr` command.

## Configuration

Shared preferences live in `defaults.yaml`. OS defaults live in
`ansible/vars/mac.yaml` and `ansible/vars/linux.yaml`. Ansible extra variables
(`-e`) override them.

- `machine_type` selects personal/work package layers and, when managed,
  the primary GitHub SSH key. Git name and email still come from `git_name`
  and `git_email`; profiles do not invent different Git identities.
- `manage_ssh_config` defaults to false on both platforms. The installer
  passes the startup choice explicitly. For a direct Ansible SSH-only run, use
  `scripts/with-sudo-askpass.sh ansible-playbook local.yaml --tags ssh
  -e machine_type=work -e manage_ssh_config=true`. When enabled,
  setup backs up and replaces SSH configuration using `ssh_agent_socket`
  and the configured public key filenames. Inputs are checked before writes;
  every managed SSH run has a separate timestamped backup, including when
  selecting the SSH tasks directly. `ssh_agent_socket` can be overridden
  with Ansible extra variables for a custom socket.
- `install_dotfiles` defaults to true on both platforms. The Ubuntu startup
  prompt and `--skip-dotfiles` can disable it for a full setup run. Direct
  Ansible runs can use `-e install_dotfiles=false`; tagged Make commands do
  not prompt. The external dotfiles currently contain a hardcoded
  `/opt/homebrew` shell path, so successful installation does not establish
  Linux shell compatibility. That requires changes in the external repository.
  The clone task refuses to discard local changes in an existing checkout.
- Ubuntu gets Homebrew shell initialization and Node/pnpm paths without
  requiring the external dotfiles. Zsh is installed through apt on Ubuntu,
  with Oh My Zsh and autosuggestions enabled. Homebrew Node stays linked
  until nvm has a working default runtime; `make node` installs Node LTS
  before switching ownership to nvm.
- Backups are written under `~/.dev-setup-backups`; existing backups under
  `~/.mac-setup-backups` are left in place.

`make update` updates installed tools, including those installed outside the
selected profile; it does not uninstall packages or run Ubuntu system upgrades.
Its summary distinguishes completed, skipped, and failed components. Runtime
and cask failures are collected, reported, and cause a nonzero exit status.
Commands that ran may still report `changed` on a repeat run; a successful
rerun does not imply a zero-change Ansible recap.

## Implementation and validation

`install.sh` detects macOS or Ubuntu and sources the corresponding bootstrap
script. Shared Homebrew setup lives in `scripts/bootstrap-homebrew.sh`.
Bootstrap owns prerequisites; `local.yaml` owns configuration and packages.
`update.yaml` owns maintenance. Unsupported operating systems and profiles
are rejected before setup tasks run.

`ansible/tasks/platform.yaml` selects package layers for both playbooks.
Shared tasks must not call Mac-only commands. Mac tasks live under
`ansible/tasks/mac/` and their imports are guarded in `local.yaml`.

`make check` does not install packages or change your shell/SSH configuration.
It uses temporary directories and fake commands to check all four OS/profile
combinations, SSH/dotfiles prompt answers and flags, opt-outs, invalid inventories,
headless sudo, successive SSH backups, Node ownership, and error propagation.
These checks do not replace a real
installation on a disposable machine.

Validation performed on 2026-09-21:

- Ubuntu 24.04 ARM64 in Docker: fresh bootstrap and the complete shared CLI
  inventory through `./install.sh work`, without a terminal and with dotfiles
  disabled (before the default changed); personal CLI
  rerun, update flow, and configured shell/tool startup checks.
- macOS: non-installing checks, inventory parsing, and Ansible syntax checks.
- Simulated failures: invalid profiles/inventories, missing sudo authorization,
  failed Node installation, runtime update errors, and unsafe Node unlinking.
- SSH opt-in follow-up: terminal prompt/flag checks, simulated Ansible runs
  on both OSes, and Ubuntu startup with inert bootstrap commands; live
  1Password authentication has not been tested.
- Dotfiles default/opt-out: routing and terminal prompt checks passed; the
  external dotfiles have not been runtime-tested on Linux.

Fresh macOS installation, GUI/App Store behavior, Ubuntu x86_64, and other
Ubuntu releases have not been runtime-tested. Repeat the disposable-machine
checks after changing package inventories or supported platforms.

Repository maintenance instructions live in [AGENTS.md](AGENTS.md).

[Dotfiles](https://github.com/mintuz/.dotfiles) ·
[Homebrew on Linux](https://docs.brew.sh/Homebrew-on-Linux) ·
[1Password SSH agent](https://developer.1password.com/docs/ssh)
