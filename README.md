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
| `make remote-login-check` | Check macOS Remote Login prerequisites read-only, without sudo; does not validate effective SSH settings or network isolation |
| `make remote-login` | Configure and enable macOS SSH key logins from the local console; first complete the [remote access prerequisites](#before-you-start) |
| `make remote-login-revoke` | From the local console, disable macOS SSH startup/listener and back up then clear your `authorized_keys`; existing sessions need separate action |
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
  key files in `.ssh/` and must not be empty when enabling access.
  `remote_login_sources` limits the source addresses accepted for SSH logins;
  it does not bind the listener to those interfaces. `tailscale_cli` is the
  path of the Tailscale command-line tool. None of the Remote Login commands
  changes Shields Up. `make remote-login-revoke` sets the separate,
  default-false `revoke_remote_login` flag for one run. It needs neither
  phone keys nor Homebrew nor a Tailscale connection.
  If both opt-in flags are true, revocation takes precedence.
  See [Remote access from an iPhone](#remote-access-from-an-iphone).
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

`make remote-login` configures SSH access to this Mac from your Tailscale
network (tailnet), for example from an iPhone with Secure ShellFish or Moshi.
It works on macOS only, and only when you opt in. The key-only and
source-address limits apply to normal SSH **after FileVault unlocks**, not
to every boot state or every service on the Mac.

Start with [prerequisites](#before-you-start) and
[network restrictions](#restrict-network-access-before-setup), then
[set up the Mac](#set-up-the-mac) and [iPhone](#set-up-the-iphone).
For existing access: [change keys](#add-or-remove-phone-keys),
[revoke access](#turn-off-remote-access),
[handle a lost phone](#if-the-iphone-is-lost-or-compromised), or
[troubleshoot](#remote-login-troubleshooting).

### Before you start

Use your normal macOS account, not root. The commands require Ansible
and the repository's Ansible collections; complete bootstrap first if
needed. Enablement and its read-only preflight also require Homebrew,
connected Tailscale, and phone public keys. Revocation does not.

Read these limits before enabling Remote Login:

- Before FileVault unlocks after a restart, macOS can accept an SSH password
  to unlock the disk. The managed SSH settings are on the locked data volume
  and do not apply then (`man apple_ssh_and_filevault`). Use a strong login
  password; do not assume the post-unlock key-only rules protect this path.
  If you require key-only access in every boot state, do not enable the
  built-in Remote Login service with this command.
- Remote Login uses wildcard listeners and advertises SSH on the local
  network with Bonjour. `remote_login_sources` restricts authentication, not
  network exposure. **Tailscale Shields Up is not LAN protection.** Configure
  and verify a local firewall before enabling Remote Login. Do not assume
  a post-unlock application firewall protects FileVault's pre-unlock SSH.
- Run enablement, key changes, and revocation from a local console, not
  SSH or mosh. The commands refuse environments with `SSH_CONNECTION`,
  `SSH_CLIENT`, or `SSH_TTY` set; do not unset these to bypass the check.
  A reused terminal session can retain or omit these variables; the guard
  cannot prove local-console use. Start a fresh local terminal on the Mac.
  Setup disables and unloads Remote Login before replacing its live
  configuration. Existing sessions may be interrupted; stopping the
  listener does not reliably end all SSH or mosh sessions.
  The read-only `make remote-login-check` does not require a local console.
- Keep Shields Up on until setup and the policy checks below succeed.
  None of the Remote Login commands changes it.
  Releasing it permits inbound traffic to any service allowed by the full
  tailnet policy, including development servers if broad rules remain.

Install the Tailscale app on the Mac and iPhone and sign in to the same
tailnet. On the Mac, explicitly keep inbound tailnet connections blocked
while preparing access:

```bash
tailscale set --shields-up=true
```

Install Moshi, Secure ShellFish, or both on the iPhone. Moshi has herdr
support; in Secure ShellFish you start herdr yourself. Run `make cli` to
install mosh from the personal Mac inventory. Install herdr from
[herdr.dev](https://herdr.dev); SSH commands find it in `~/.local/bin`, the
Homebrew `bin` directory, or `/usr/local/bin`.

### Restrict network access before setup

Review the **whole** Tailscale or Headscale access policy before activating
SSH or releasing Shields Up. Grants and legacy ACLs are additive: adding a
narrow rule does not cancel a broad allow rule. Remove or narrow every
matching broad grant and ACL, including rules that allow all devices,
all ports, or access through a group or tag. This repository never rewrites
the control-server policy.

Allow only the intended iPhone to reach this Mac on TCP port 22 (SSH) and
UDP ports 60000–61000 (mosh). This is an illustrative grant, not a complete
policy. The addresses `100.100.100.10` and `100.100.100.20` are fictional
examples, not actual device addresses; replace them with your devices'
addresses and include their IPv6 identities where applicable:

```jsonc
"hosts": { "iphone-example": "100.100.100.10", "mac-example": "100.100.100.20" },
"grants": [{ "src": ["iphone-example"], "dst": ["mac-example"], "ip": ["tcp:22", "udp:60000-61000"] }]
```

Use your control server's policy tests to verify both allowed and denied
traffic: the iPhone may reach those SSH/mosh ports; other devices may not;
and the iPhone may not reach other Mac services. If you cannot inspect the
full policy or run these tests, ask the provider or control-server
administrator to do so and confirm the results before proceeding. Merely
adding the example grant is not proof of isolation.

Configure the local firewall, such as Little Snitch, before setup too.
Allow incoming TCP 22 and UDP 60000–61000 only from the intended iPhone's
tailnet addresses; block other sources, including LAN addresses. Review
existing rules and their precedence so a broad allow cannot override these
limits. Verify the rules for both IPv4 and IPv6. The command does not
configure the firewall. A firewall rule allowing SSH is not a substitute
for reviewing other exposed services.

### Set up the Mac

1. Complete the network policy and local firewall checks above. Leave
   Shields Up on.
2. For Secure ShellFish, create a key on the iPhone's Secure Enclave.
   The private key cannot leave the iPhone.
3. For Moshi, create an Ed25519 key. Turn on **Biometric for keys** and
   keep credential sync off. Only create keys for the apps you will use.
4. Copy each public key into `.ssh/` in this repository. For example, copy
   the public key on the iPhone, then run this command on the Mac. This needs
   Universal Clipboard.

   ```bash
   pbpaste > .ssh/iphone-shellfish.pub
   ```

5. List only those key files in `defaults.yaml`:

   ```yaml
   remote_login_public_keys:
     - iphone-shellfish.pub
     - iphone-moshi.pub
   ```

   By default, `remote_login_sources` accepts SSH logins from all tailnet
   addresses. Narrow it to the iPhone's Tailscale IPv4 and IPv6 addresses
   if only that device should log in. If its addresses change, update the
   list at the Mac. This authentication limit does not replace the policy
   or firewall checks.
6. Run the read-only prerequisite check as your normal user:

   ```bash
   make remote-login-check
   ```

   This checks phone keys, Tailscale, and Homebrew without sudo or changes
   to services, configuration, or keys. It uses limited Ansible check mode:
   configuration deployment, the effective SSH settings gate, and activation
   are skipped. A pass is **not** a full SSH configuration preview, proof
   that enablement will succeed, or verification of policy or firewall rules.
7. Before enabling, review the key list: each run backs up and **replaces
   all of `~/.ssh/authorized_keys`** with these keys. Hand-added keys and
   Moshi Easy Pair keys not in the list will be removed. Setup also limits
   Remote Login to your account. Existing SSH or mosh sessions may be
   interrupted, but are not reliably terminated.
   At the Mac's local console, run:

   ```bash
   make remote-login
   ```

   Enter your sudo password if asked. Keep the connection details and
   host key fingerprints. If the run fails, do not enable Remote Login
   manually; fix the reported cause and rerun locally.
8. Only after enablement succeeds and the full policy and firewall checks pass,
   explicitly allow inbound tailnet traffic:

   ```bash
   tailscale set --shields-up=false
   ```

9. Set up the iPhone as described below. Then verify an actual iPhone
   connection and denied connections from other devices, including LAN sources.
   Check that unrelated Mac services are still unreachable.
   If any result differs from the intended rules,
   restore Shields Up and use `make remote-login-revoke` locally while you
   fix the policy or firewall. Shields Up alone does not block LAN access.

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
- After a restart, normal tailnet access needs somebody to unlock FileVault
  and log in locally so the Tailscale app starts. This does not mean
  pre-unlock password SSH is unavailable on other network paths. Install
  macOS updates when you are at the Mac.
- Sign in to Tailscale on the Mac again before its node key expires.
  `tailscale status --json` shows the expiry date in `Self.KeyExpiry`.

### Add or remove phone keys

For changes that leave at least one trusted key:

1. Add or remove filenames in `remote_login_public_keys`.
2. Run `make remote-login-check` to check the revised inputs, then
   `make remote-login` from the local console. Enablement interrupts the
   listener while it rechecks the effective SSH configuration.

Each enable run replaces `~/.ssh/authorized_keys` with the listed keys. Keys added
by hand or by Moshi's Easy Pair are removed. Before each change to a nonempty
file, it is backed up under
`~/.dev-setup-backups/<timestamp>/remote-login-<previous-content-hash>/authorized_keys`.
Backups are not active key files; do not restore a revoked phone key.

To remove the final key, use `make remote-login-revoke` instead. Then remove
its filename from `remote_login_public_keys` so a later setup cannot
reinstall it. An empty list deliberately fails the enable command; it is
not a revocation request. Removing a key prevents new authentication, not
access through an already authenticated SSH or mosh session.

### Turn off remote access

Setting `manage_remote_login` to false does not undo an earlier run. At the
local console, run:

```bash
make remote-login-revoke
```

This Mac-only command opts in with `revoke_remote_login=true` and the
`remote-login-revoke` tag. It disables SSH startup, unloads the listener
if present, and backs up then clears the invoking user's
`~/.ssh/authorized_keys`. It retains the managed SSH configuration. It needs
sudo and the existing Ansible prerequisites, but not Homebrew, phone keys,
or a working Tailscale connection. Neither full setup nor a false revoke
flag revokes access.

If Tailscale is available, also run `tailscale set --shields-up=true`.
Revocation itself does not change Shields Up or the control-server policy.
**Listener shutdown and key removal do not end all existing SSH or mosh
sessions.** Use the incident steps below if an active session is untrusted.

### If the iPhone is lost or compromised

1. Revoke or remove the iPhone device in the tailnet control server. Ask its
   administrator if you cannot do this yourself. Do not rely on this alone
   to terminate existing Mac sessions.
2. At the Mac's local console, run `make remote-login-revoke`. If available,
   also run `tailscale set --shields-up=true`. Remove the lost phone's key
   filenames from `remote_login_public_keys`.
3. Identify established SSH connections, mosh UDP listeners, and their
   process trees before terminating anything:

   ```bash
   sudo lsof -nP -iTCP -sTCP:ESTABLISHED
   sudo lsof -nP -iUDP
   ps ax -o pid=,ppid=,user=,tty=,command=
   ```

   Match remote addresses and ports to the affected account's `sshd` child
   processes and `mosh-server` processes. Inspect their child shells and
   jobs too; do not assume stopping one parent ends every child. If the
   connection cannot be attributed, treat all remote sessions for that
   account as suspect and review them individually.
4. For each confirmed remote-session PID, verify it immediately before
   signalling it. Replace `<PID>` below with that numeric PID; do not paste
   the placeholder literally:

   ```bash
   ps -p <PID> -o pid=,ppid=,user=,tty=,command=
   sudo kill -TERM <PID>
   ps -p <PID> -o pid=,ppid=,user=,tty=,command=
   ```

   Repeat the connection and process listings to confirm that the affected
   transports have gone. If a process remains, inspect it again before
   considering `sudo kill -KILL <PID>`; forced termination can lose work.
   Do not kill all processes for your account, all terminal sessions, or
   herdr wholesale. Herdr work can survive a transport disconnect. Inspect
   suspect work separately and preserve unrelated local sessions.
5. Review what the compromised session could access, including credentials
   and jobs it started. Rotate affected credentials where needed. Re-enable
   access only with trusted replacement keys, reviewed policy/firewall
   rules, and a successful `make remote-login` run; then release Shields Up
   manually as in setup.

### Remote Login troubleshooting

- **Wrong platform, root, or missing Ansible:** use a normal macOS account
  and complete bootstrap. Do not run the Make commands with `sudo`; enable
  and revoke request it when needed.
- **Local-console refusal:** move to a local terminal on the Mac. Do not
  bypass the SSH environment check. Read-only preflight can run remotely.
- **Preflight fails:** correct the reported phone-key, Homebrew, or Tailscale
  prerequisite, then rerun `make remote-login-check`. Each key file must
  contain one public key line, without authorised-key options.
- **Enablement fails after preflight passed:** preflight does not run the
  effective SSH settings gate. Review the error and the
  [security limits](#security-limits), fix the cause, and rerun locally.
  Do not bypass the gate by enabling SSH manually.
- **The phone cannot connect:** check Tailscale on both devices, the selected
  key and account, and the reviewed policy/firewall rules. Do not widen
  rules merely to get a connection. A host fingerprint mismatch must be
  investigated before connecting.

### Security limits

- The SSH server configuration can contain no `Match` block except the one
  in `010-remote-login.conf`. It also cannot set `DenyUsers`, `DenyGroups`,
  `AllowGroups`, `RefuseConnection`, `ForceCommand`, `ChrootDirectory`,
  `PermitTTY no`, or `MaxSessions 0`. Another `Match` block could add a login
  that the limits do not cover, and those settings could stop your own
  login. `make remote-login` stops when it finds them.
- The key-only promise applies to normal post-unlock SSH. Review the
  FileVault, wildcard-listener, Bonjour, and firewall warnings
  [before setup](#before-you-start).
- If `~/.ssh/config` sends SSH to the 1Password agent, outgoing SSH from an
  iPhone session, for example `git push`, waits for approval on the Mac
  screen.

### What setup changes

`make remote-login` performs these steps and stops on failure:

1. Checks Homebrew, that the phone key list is nonempty, that each file holds
   one public key line without options, and that Tailscale is connected.
2. Creates SSH host keys if needed.
3. Disables SSH startup and unloads its listener if loaded. Rejects a symlink
   or non-regular file at `/etc/ssh/sshd_config.d/010-remote-login.conf` and
   saves the previous regular file's content, owner, group, and mode, if
   present.
4. Installs the managed configuration. This limits normal post-unlock SSH
   to key logins for your account from `remote_login_sources`, with keys only in
   `~/.ssh/authorized_keys`. It also sets the SSH command `PATH` so mosh and
   herdr can be found.
5. Validates the configuration and effective SSH settings. If deployment
   or this gate fails, restores the previous configuration, or removes the
   new file if none existed, and leaves Remote Login disabled. The original
   failure is reported.
6. Only after the gate succeeds, backs up and replaces
   `~/.ssh/authorized_keys` with the listed phone keys, and sets the Remote
   Login access list to your account only.
7. Enables Remote Login and checks the SSH port. An activation or port-check
   failure disables startup and unloads the listener again.
8. Shows connection details and SSH host key fingerprints, and warns if
   `mosh-server` or `herdr` is not on the SSH `PATH`.

If any step fails, fix the reported cause and rerun from the local console.
Do not enable Remote Login manually in System Settings or with `launchctl`
to bypass a failed run.

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

Validation performed on 2026-10-06, before the security-review fixes:

- `make check` passed. Each new check failed against a copy of the
  repository with one safeguard removed: the macOS guard, the password
  setting, the `Match all` block, `PubkeyAuthentication yes`, the `Match`
  block check, the account-rule check, or the `RefuseConnection` check.
- A check-mode run against the real Mac, without root, showed the planned
  changes and changed nothing.
- The effective-settings check passed on a copy of macOS SSH configuration.
  With the `Match all` block, weaker global settings in other
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
  steps, and connections from an iPhone have not been tested. This history
  does not establish the later rollback or revocation behaviour.

Security-review follow-up validation on 2026-10-06:

- `make check` passed, including offline final-key revocation, check-mode
  safety, partial activation failure, restoration of previous configuration,
  removal of rejected first-install configuration, and refusal to replace
  configuration when listener shutdown fails.
- An isolated `make remote-login-revoke` run used a temporary home directory,
  a generated public key, and a stateful `launchctl` substitute. It cleared
  the key file, preserved its previous content in a backup, and left the
  service model disabled and unloaded.
- The production activation block recovered from a simulated partial
  `bootstrap` failure. It reported failure and confirmed that the service
  model was disabled and unloaded.
- The operator-workflow checks passed: valid-key preflight preserved existing
  access in a temporary home, and direct Ansible enable/revoke runs refused
  detected SSH sessions before touching service state or keys.
- Command smoke checks confirmed local-console refusals, non-Mac rejection,
  and an actionable empty-key preflight failure without sudo. No host
  activation or revocation was performed.
- These checks did not call real privileged `launchctl` operations or
  establish firewall, tailnet, FileVault boot, or iPhone behaviour.

Fresh macOS installation, GUI/App Store behavior, Ubuntu x86_64, and other
Ubuntu releases have not been runtime-tested. Repeat the disposable-machine
checks after changing package inventories or supported platforms.

Repository maintenance instructions live in [AGENTS.md](AGENTS.md).

[Dotfiles](https://github.com/mintuz/.dotfiles) ·
[Homebrew on Linux](https://docs.brew.sh/Homebrew-on-Linux) ·
[1Password SSH agent](https://developer.1password.com/docs/ssh)
