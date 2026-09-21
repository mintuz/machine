# Development Machine Setup

Set up macOS and Ubuntu development machines with Ansible and Homebrew.
Both operating systems support personal and work profiles. Ubuntu defaults
to a headless setup: no desktop apps, SSH changes, or dotfiles installation.

## Quick start

Run as your normal user with sudo access:

```bash
./install.sh personal
# or
./install.sh work
```

On macOS, bootstrap first if you still need to sign in to 1Password:

```bash
./install.sh --bootstrap-only
# Open 1Password, sign in, and enable its SSH agent.
make personal
```

Sign in to the Mac App Store before installing its apps. Public GitHub keys
for the Mac SSH configuration are stored under `.ssh/` in this repository.
`new-mac.sh` remains a shortcut for Mac bootstrap only.

On Ubuntu, bootstrap installs apt prerequisites, Homebrew, and Ansible.
It preserves the existing SSH configuration and agent, including a forwarded
agent. It does not install the 1Password desktop application. The shared
1Password CLI is independent of that desktop SSH agent.

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
| `make dotfiles` | Explicitly install the external dotfiles on either OS |
| `make update` | Update installed Homebrew packages, CLI casks, and runtime tools; App Store only on Mac |
| `make check` | Check routing, safety regressions, Brewfile parsing, shell syntax, and Ansible syntax |

Tagged commands assume bootstrap has already run. `PROFILE` defaults to
`personal`; it is not remembered between invocations. `make personal` and
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
- `manage_ssh_config` is true on Mac and false on Ubuntu. When enabled,
  setup backs up and replaces SSH configuration using `ssh_agent_socket`
  and the configured public key filenames. Inputs are checked before writes;
  every managed SSH run has a separate timestamped backup, including when
  selecting the SSH tasks directly.
- `install_dotfiles` is true on Mac and false on Ubuntu. `make dotfiles`
  opts in explicitly. The external dotfiles currently contain a hardcoded
  `/opt/homebrew` shell path: make them Linux-compatible before opting in
  on Ubuntu. This repository does not modify that external repository.
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
combinations, invalid inventories, headless sudo, successive SSH backups,
Node ownership, and error propagation. These checks do not replace a real
installation on a disposable machine.

Validation performed on 2026-09-21:

- Ubuntu 24.04 ARM64 in Docker: fresh bootstrap and the complete shared CLI
  inventory through `./install.sh work`, without a terminal; personal CLI
  rerun, update flow, and configured shell/tool startup checks.
- macOS: non-installing checks, inventory parsing, and Ansible syntax checks.
- Simulated failures: invalid profiles/inventories, missing sudo authorization,
  failed Node installation, runtime update errors, and unsafe Node unlinking.

Fresh macOS installation, GUI/App Store behavior, Ubuntu x86_64, and other
Ubuntu releases have not been runtime-tested. Repeat the disposable-machine
checks after changing package inventories or supported platforms.

Repository maintenance instructions live in [AGENTS.md](AGENTS.md).

[Dotfiles](https://github.com/mintuz/.dotfiles) ·
[Homebrew on Linux](https://docs.brew.sh/Homebrew-on-Linux) ·
[1Password SSH agent](https://developer.1password.com/docs/ssh)
