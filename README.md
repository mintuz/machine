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
| `make remote-login` | Allow SSH key logins to this Mac from your tailnet, for example from an iPhone; macOS only, see [Remote access from an iPhone](#remote-access-from-an-iphone) |
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
    │   ├── Brewfile.cli
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
- `manage_remote_login` defaults to false on macOS. `make remote-login` sets it
  to true for one run; full setup does not ask about it. Setting it to false
  does not undo an earlier run. `remote_login_public_keys` lists phone public
  key files in `.ssh/`, and `remote_login_sources` lists the address ranges
  that can log in. `tailscale_cli` is the path of the Tailscale command-line
  tool. See [Remote access from an iPhone](#remote-access-from-an-iphone).
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

## Remote access from an iPhone

`make remote-login` lets you log in to this Mac over SSH from devices in your
Tailscale network (tailnet), for example an iPhone with Secure ShellFish or
Moshi. It works on macOS only, and only when you run it. The Mac then accepts
only key logins for your account, and only from tailnet addresses.

The command does these steps in this order. It stops at the first problem.

1. Checks the phone public keys, and checks that Tailscale is connected.
   Each key file must hold one public key line without options.
2. Creates the SSH host keys if they do not exist.
3. Installs `/etc/ssh/sshd_config.d/010-remote-login.conf`. For every
   connection, this file allows only key logins for your account, only from
   `remote_login_sources`, and only with keys in `~/.ssh/authorized_keys`. It
   also puts `~/.local/bin` and the Homebrew `bin` directory in `PATH` for SSH
   commands, so that mosh and herdr work.
4. Reads the effective SSH server settings. The run stops before it turns on
   Remote Login if the SSH server does not read the file, if another file
   weakens the limits or adds a `Match` block, or if another file sets a rule
   that can stop your login (see [Security limits](#security-limits)).
5. Backs up `~/.ssh/authorized_keys`, then replaces it with the listed phone
   keys.
6. Sets the Remote Login access list to your account only.
7. Turns on Remote Login.
8. Turns off Tailscale Shields Up, so that tailnet devices can connect.
9. Shows the host name, the user name, and the SSH host key fingerprints. It
   warns if `mosh-server` or `herdr` is not on the SSH `PATH`.

### Before you start

- Install the Tailscale app on the Mac and on the iPhone. Sign in to the same
  tailnet on both devices.
- Install Moshi, Secure ShellFish, or both on the iPhone. Moshi has herdr
  support. Secure ShellFish does not, so in it you start herdr yourself.
- Run `make cli` to install mosh. It is in the personal Mac inventory.
- Install herdr on the Mac from [herdr.dev](https://herdr.dev). SSH commands
  find it in `~/.local/bin`, the Homebrew `bin` directory, or `/usr/local/bin`.

### Set up the Mac

1. In Secure ShellFish, create a key on the Secure Enclave. The private key
   cannot leave the iPhone.
2. In Moshi, create an Ed25519 key. Turn on **Biometric for keys**. Keep
   credential sync off.
3. Copy each public key into `.ssh/` in this repository. For example, copy
   the public key on the iPhone, then run this command on the Mac. This needs
   Universal Clipboard.

   ```bash
   pbpaste > .ssh/iphone-shellfish.pub
   ```

4. List the key files in `defaults.yaml`:

   ```yaml
   remote_login_public_keys:
     - iphone-shellfish.pub
     - iphone-moshi.pub
   ```

5. Optional: preview the changes. This command can ask for your password. It
   does not change the Mac:

   ```bash
   scripts/with-sudo-askpass.sh ansible-playbook local.yaml --tags remote-login -e manage_remote_login=true --check --diff
   ```

6. Run `make remote-login`. Enter your password when it asks.
7. Keep the host name and the fingerprints that the command shows.
8. Open System Settings > General > Sharing, and make sure that Remote Login
   is on. If it is off, turn it on there. The command turns on Remote Login
   with `launchctl`; System Settings has not been checked after that method.

### Allow the iPhone to reach the Mac

The tailnet access policy must let the iPhone reach the Mac on TCP port 22
(SSH) and UDP ports 60000–61000 (mosh). Add a grant like this one to the
Tailscale or Headscale policy file. Replace the addresses with the Tailscale
addresses of your devices:

```jsonc
"hosts": { "my-iphone": "100.64.0.10", "my-mac": "100.64.0.9" },
"grants": [{ "src": ["my-iphone"], "dst": ["my-mac"], "ip": ["tcp:22", "udp:60000-61000"] }]
```

If somebody else runs the control server, for example a company Headscale
server, ask an administrator to add the grant. That administrator then
controls which devices can reach the Mac. The phone keys still control who
can log in.

If you use Little Snitch, add the rules yourself; the command cannot add them.
Add these incoming rules for any process:

1. Allow TCP port 22 and UDP ports 60000–61000 from `100.64.0.0/10` and
   `fd7a:115c:a1e0::/48`.
2. Deny TCP port 22 and UDP ports 60000–61000 from any server.

Rules for addresses take priority over rules for any server.

### Set up the iPhone

1. In the Tailscale app, open Settings > VPN On Demand. Set Wi-Fi and
   Cellular to **Always**.
2. In each app, add a server. Use the host name that `make remote-login`
   showed, your Mac account name, and port 22.
3. In Moshi, keep the connection type at **Auto**.
4. Connect. Compare the host key fingerprint with the fingerprints that
   `make remote-login` showed. If they are different, do not continue.
5. In Moshi's session picker, open the **Herdr** tab and tap a session to
   attach to it. Moshi lists only running sessions. If there is none, tap
   **Skip**, then run `herdr` to start one.
6. In Secure ShellFish, leave the tmux option off. After you connect, run
   `herdr` to attach to the default session, or `herdr session attach <name>`
   for a named session.

Work inside herdr keeps running on the Mac when the phone disconnects.

### Keep the Mac available

- Keep the Mac connected to power.
- To use the Mac with the lid closed, start an Amphetamine session that stops
  system sleep when the display is closed. Do not keep a closed Mac running
  in a bag, because it can overheat.
- After a restart, you cannot connect until somebody logs in at the Mac.
  FileVault keeps the data volume locked, and the Tailscale app starts only
  after login. Install macOS updates when you are at the Mac.
- Sign in to Tailscale on the Mac again before its node key expires.
  `tailscale status --json` shows the expiry date in `Self.KeyExpiry`.

### Add or remove phone keys

1. Add the key file name to `remote_login_public_keys`, or remove it.
2. Run `make remote-login`.

Each run replaces `~/.ssh/authorized_keys` with the listed keys. Keys that
you add by hand, or that Moshi's Easy Pair adds, are removed. Before a change,
the previous file is copied to
`~/.dev-setup-backups/<timestamp>/remote-login/authorized_keys`.

### Turn off remote access

Setting `manage_remote_login` to false does not undo anything. To turn off
remote access:

1. Turn off System Settings > General > Sharing > Remote Login. If System
   Settings does not show it as on, run
   `sudo launchctl bootout system/com.openssh.sshd` and then
   `sudo launchctl disable system/com.openssh.sshd`.
2. Run `tailscale set --shields-up=true`.
3. Optional: remove the SSH server settings with
   `sudo rm /etc/ssh/sshd_config.d/010-remote-login.conf`.

### Security limits

- The SSH server configuration can contain no `Match` block except the one
  in `010-remote-login.conf`. It also cannot set `DenyUsers`, `DenyGroups`,
  `AllowGroups`, `RefuseConnection`, `ForceCommand`, `ChrootDirectory`,
  `PermitTTY no`, or `MaxSessions 0`. Another `Match` block could add a login
  that the limits do not cover, and those settings could stop your own
  login. `make remote-login` stops when it finds them.
- After a restart, before FileVault unlocks, macOS accepts an SSH password
  to unlock the disk. The SSH server settings do not apply at that time,
  because macOS keeps them on the locked data volume
  (`man apple_ssh_and_filevault`). Use a strong login password.
- With Shields Up off, devices that the tailnet policy allows can reach every
  service that listens on the Mac, for example development servers. Keep the
  policy limited to the iPhone and the ports above.
- Remote Login advertises SSH on the local network with Bonjour.
- If `~/.ssh/config` sends SSH to the 1Password agent, outgoing SSH from an
  iPhone session, for example `git push`, waits for approval on the Mac
  screen.
- By default, `remote_login_sources` accepts logins from every tailnet
  address. To accept only the iPhone, replace the ranges with its two
  Tailscale addresses. If the iPhone gets new addresses, you cannot log in
  until you change the list at the Mac.

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
headless sudo, successive SSH backups, Node ownership, error propagation, Remote
Login routing and missing phone keys, and, on macOS, the effective Remote Login
SSH server settings.
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

Validation performed on 2026-10-06 (Remote Login, macOS 26.6 on Apple silicon):

- `make check` passed. Each new check failed against a copy of the
  repository with one safeguard removed: the macOS guard, the password
  setting, the `Match all` block, `PubkeyAuthentication yes`, the `Match`
  block check, the account-rule check, or the `RefuseConnection` check.
- A check-mode run against the real Mac, without root, showed the planned
  changes and changed nothing.
- The effective-settings check passed on a copy of this Mac's SSH
  configuration. With the `Match all` block, weaker global settings in other
  files (passwords, key logins turned off, extra key files, a user CA,
  `SetEnv`, `AllowUsers`) did not change the effective settings. Another
  `Match` block, a configuration that does not read the managed file,
  `DenyUsers`, and `RefuseConnection yes` each stopped the run.
- The key check accepted Ed25519 and ECDSA P-256 keys. It refused key
  options, extra lines, two keys, private keys, empty files, and truncated
  keys.
- Throwaway copies of macOS `sshd` on loopback ports refused passwords,
  non-tailnet sources, and keys outside `~/.ssh/authorized_keys`. Through
  `SetEnv PATH`, SSH commands found `mosh-server` and the same
  `~/.local/bin/herdr` that the interactive shell uses.
- A real `make remote-login` run with root, the `launchctl` and access-list
  steps, and connections from an iPhone have not been tested.

Fresh macOS installation, GUI/App Store behavior, Ubuntu x86_64, and other
Ubuntu releases have not been runtime-tested. Repeat the disposable-machine
checks after changing package inventories or supported platforms.

Repository maintenance instructions live in [AGENTS.md](AGENTS.md).

[Dotfiles](https://github.com/mintuz/.dotfiles) ·
[Homebrew on Linux](https://docs.brew.sh/Homebrew-on-Linux) ·
[1Password SSH agent](https://developer.1password.com/docs/ssh)
