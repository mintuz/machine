# Development Machine Setup

Configure and maintain an ARM64 development machine running macOS or
headless Ubuntu. Choose a `personal` or `work` profile, then use the same
commands to install software, configure your environment and keep it updated.

The repository aims to:

- Provide repeatable setup with package inventories you can review and customise.
- Let you run the full setup or select individual components.
- Keep SSH client changes and Mac Remote Login opt-in.
- Preserve local dotfiles work and existing global packages when changing runtimes.

[Homebrew](https://brew.sh/) manages native command-line tools and Mac apps.
[mise](https://mise.jdx.dev/) manages runtimes and provides the command
interface. A separately configured dotfiles repository manages personal
shell configuration.

## Contents

- [Requirements](#requirements)
- [Set up a machine](#set-up-a-machine)
- [Command reference](#command-reference)
- [Configure your machine](#configure-your-machine)
- [Choose what to install](#choose-what-to-install)
- [Configure SSH with 1Password](#configure-ssh-with-1password)
- [Manage dotfiles and runtimes](#manage-dotfiles-and-runtimes)
- [Update installed software](#update-installed-software)
- [Customise the package inventory](#customise-the-package-inventory)
- [Remote access from an iPhone](#remote-access-from-an-iphone)
- [Check the setup files](#check-the-setup-files)
- [Troubleshoot setup](#troubleshoot-setup)

## Requirements

- An Apple silicon Mac running natively, or ARM64 Ubuntu. Intel Macs,
  Rosetta, other Linux distributions and non-ARM64 Linux are not supported.
- A normal user account with sudo access. Do not run the installer or
  mise tasks as root, or prefix them with `sudo`.
- Network access to download tools and packages.
- For Mac App Store apps, sign in to the App Store before installing them.

**Review the defaults before full setup.** This repository contains the
owner's Git name, email address, public-key filenames, dotfiles source,
macOS preferences and Dock layout. Read [defaults.toml](defaults.toml) and
[the package inventories](packages/). Use [local settings](#configure-your-machine)
to supply your own values or exclude components you do not want.

## Set up a machine

### Run the installer

1. Download and extract the repository, then open a terminal in its directory.
   If Git is already available, you can clone it instead:

   ```bash
   git clone https://github.com/mintuz/machine.git
   cd machine
   ```

2. Review the defaults and prepare any local configuration file before
   continuing. For a personal machine, run:

   ```bash
   ./install.sh personal
   ```

   For a work machine, use `./install.sh work` instead. To apply your own
   settings, pass the file explicitly:

   ```bash
   ./install.sh personal --config "$HOME/.config/dev-machine-setup.toml"
   ```

3. Review the SSH and dotfiles choices before bootstrap. The SSH prompt
   defaults to **No**. Ubuntu also asks whether to install dotfiles.
   Dotfiles default to enabled; Enter keeps the configured choice.
   Unattended runs preserve SSH unless `--1password-ssh` is explicit
   and keep the configured dotfiles choice.

4. Follow the bootstrap prompts. Setup installs OS prerequisites,
   Homebrew, a checksum-verified mise executable and the locked helper Python.
   If macOS requests Command Line Tools, finish that installation, then
   rerun the same command. Ubuntu uses `apt` for bootstrap prerequisites
   and Zsh; it does not run a system upgrade.

To preserve SSH settings and omit the external dotfiles installation:

```bash
./install.sh personal --keep-ssh --skip-dotfiles
```

This does not prevent selected components from configuring regular shell
files. Use [component exclusions](#choose-what-to-install) to control those
operations too. Explicit `--dotfiles` and `--skip-dotfiles` work on both OSes.

Full setup checks prerequisites and refreshes Homebrew before applying
selected components. It then configures SSH, Git, command-line tools, GUI
apps, Zsh, App Store apps, macOS preferences, Node, dotfiles and the Dock.
Mac-only actions do not run on Ubuntu.

The installer **never enables Remote Login**, even if a configuration file
requests it. Set up [remote access](#remote-access-from-an-iphone) separately.
Installing Tailscale or 1Password does not grant consent to configure SSH.
Sign-in and agent or network configuration remain manual.

### Install bootstrap tools only

To prepare the command interface without running full setup:

```bash
./install.sh --bootstrap-only
```

On macOS, `./new-mac.sh` is a shortcut for this operation. Bootstrap-only
does not ask about or install external dotfiles. After bootstrap, use the
commands below to inspect packages or configure selected components.

## Command reference

After bootstrap, open a fresh login shell so it loads mise. Run these
commands from the repository directory. Except for `setup` and
`bootstrap-only`, tasks do not prompt for feature choices. They use
defaults, supplied configuration files and explicit flags.

| Command | Purpose |
|---|---|
| `mise run setup personal` | Run the installer, including bootstrap and consent prompts. |
| `mise run bootstrap-only` | Run bootstrap without full setup. |
| `mise run packages --profile work` | Show selected packages without installing them. |
| `mise run install --profile work` | Run full setup without bootstrap or feature prompts. |
| `mise run cli` | Install native and non-Node command-line tools, plus fzf integration. |
| `mise run node` | Install Node, pnpm and Node-based tools; preserve npm globals. |
| `mise run gui` | Install or upgrade Mac desktop apps. |
| `mise run app-store` | Install Mac App Store apps; requires sign-in. |
| `mise run git` | Install Git and apply global Git settings. |
| `mise run zsh` | Set the login shell and install Oh My Zsh. |
| `mise run dotfiles` | Install or refresh the configured external dotfiles. |
| `mise run osx` | Apply macOS preferences. |
| `mise run dock` | Apply the configured macOS Dock layout. |
| `mise run ssh` | Explicitly back up and configure the 1Password SSH client setup. |
| `mise run update` | Maintain installed software in selected categories. |
| `mise run remote-login-check` | Check Mac Remote Login prerequisites without changes. |
| `mise run remote-login` | Enable Mac remote access after the security prerequisites are met. |
| `mise run remote-login-revoke` | Disable Mac Remote Login and clear this account's authorised keys. |
| `mise run check` | Run the non-installing repository checks. |
| `mise run check-shell` | Run the shell behaviour checks. |

Use `--profile personal|work` with component tasks. The installer uses a
positional profile instead. For task-specific help:

```bash
mise run cli -- --help
```

To inspect both inventories and preview supported installation actions:

```bash
mise run packages --profile personal
mise run packages --profile work
mise run install --profile personal --keep-remote-login --check
```

`--check` bypasses sudo and reports supported previews without making
changes. Some host actions are not previewed. It is not a complete
configuration or SSH deployment simulation. Tasks do not automatically
install missing runtimes, so complete bootstrap first.

The direct `install` task honours configured steps, including an explicitly
enabled Remote Login step. Add `--keep-remote-login` when that operation must
remain excluded. Follow the [remote access guide](#remote-access-from-an-iphone)
before any enablement.

## Configure your machine

### Create local settings

Create a TOML file outside the checkout. Replace the sample identity with
your own. This example also omits external dotfiles and the Mac App Store
and Dock steps:

```toml
# ~/.config/dev-machine-setup.toml
git_name = "Your Name"
git_email = "you@example.com"

[steps]
dotfiles = false

[mac]
pnpm_home = "~/Library/pnpm"

[mac.steps]
app-store = false
dock = false

[linux]
pnpm_home = "~/.local/share/pnpm"
```

Configuration files are not discovered automatically. Pass your file on
each command that needs it:

```bash
./install.sh personal --config "$HOME/.config/dev-machine-setup.toml"
```

To layer another file, create it first, then pass it last:

```bash
mise run install --profile work --keep-remote-login \
  --config "$HOME/.config/dev-machine-setup.toml" \
  --config "$HOME/.config/dev-machine-work.toml"
```

Setup loads `defaults.toml`, then each `--config` file in order. Within each
file, `[mac]` or `[linux]` overrides shared settings. Later files override
earlier files; explicit feature flags take precedence. `[steps]` merges by
key. Other lists replace earlier lists. Relative paths resolve from the
directory where you invoked the command, including through mise.

Unknown settings, unknown steps and non-boolean step choices are errors,
including in inactive platform tables. On a machine without the helper
Python, TOML validation follows bootstrap. An invalid file can therefore
leave bootstrap changes behind.

### Select a profile

The default profile is `personal`. Select `work` with the installer's
positional argument, `--profile work` on tasks, `DEVSETUP_PROFILE`, or a
root-level `profile = "work"` in a supplied configuration file.

All supplied profile values must agree. A command-line profile does not
override a conflicting environment variable or file. Unset
`DEVSETUP_PROFILE` or make these values agree before changing profiles.
Setup does not save your per-run profile choice.

Profiles select additive package layers and the primary managed GitHub
SSH key. They do not select separate Git identities or uninstall packages
from another profile. Set `git_name` and `git_email` explicitly.

### Adjust preferences and paths

Use the keys in [defaults.toml](defaults.toml) to configure SSH public-key
filenames, the agent socket, the dotfiles repository and revision, pnpm
paths and global packages. Keep platform-specific paths under `[mac]` or
`[linux]`. Bootstrap uses `/opt/homebrew` on macOS and
`/home/linuxbrew/.linuxbrew` on Ubuntu.

On macOS, `macos_preferences` contains the arguments after `defaults write`.
`{home}` expands to your home directory. `dock_items` contains argument
lists for `dockutil --add`; paths can start with `~/`.

```toml
[mac]
macos_preferences = [
  ["com.apple.finder", "ShowPathbar", "-bool", "true"],
  ["com.apple.screencapture", "location", "-string", "{home}/Desktop"],
]
dock_items = []
```

An empty Dock list leaves the Dock untouched. An empty preferences list
skips configurable defaults, but Library visibility and automatic-update
checks still run. Skip `osx` to omit the entire preferences operation.

## Choose what to install

Use repeated `--skip` options to omit components for one full setup run:

```bash
./install.sh personal --skip app-store --skip dock
```

Supported steps are `ssh`, `git`, `cli`, `remote-login`, `gui`, `zsh`,
`app-store`, `osx`, `node`, `dotfiles` and `dock`. All default to enabled
except `ssh` and `remote-login`. Save recurring exclusions in `[steps]`,
`[mac.steps]` or `[linux.steps]` in your local configuration file.

A direct component command explicitly opts in for that run. For example,
this installs App Store apps even if your file excludes them from full setup:

```bash
mise run app-store --config "$HOME/.config/dev-machine-setup.toml"
```

The command reports the override. Contradictory explicit flags fail.
Bootstrap and prerequisite checks cannot be skipped. `--skip` is for
aggregate setup and maintenance, not direct component commands.

**Skipping is not uninstalling or revoking.** It leaves previous settings
and installed software in place. Included components may still install
native prerequisites. For example, skipping Git configuration does not
exclude the Git executable needed for dotfiles. Homebrew dependencies and
the external dotfiles installer can have their own effects.

The `cli` step includes fzf, but not Node. The separate `node` step owns
Node, pnpm, all `npm:` mise providers and npm global-package transfers.
Tailscale is a Mac GUI package, not an App Store package. Its sign-in and
required macOS extension approval remain manual.

## Configure SSH with 1Password

SSH client setup controls outgoing connections, such as GitHub access. It
is separate from the Mac's incoming Remote Login service.

The installer's SSH prompt defaults to No. Declining leaves existing SSH
files and agents untouched, including settings from an earlier opt-in.
This consent choice overrides a file's `steps.ssh` setting for that run.
The choice is not saved for the next invocation.

Before opting in, review the public keys selected in `defaults.toml` or
your local settings. Only public keys belong in this repository's `.ssh/`
directory. Opting in replaces `~/.ssh/config` and copies the selected public
keys. Setup first backs up existing SSH files in a unique timestamped
directory under `~/.dev-setup-backups`.

On macOS, you can install 1Password before full setup:

```bash
./install.sh --bootstrap-only --1password-ssh
```

Sign in to 1Password and enable its SSH agent manually. Then run full setup
with `--1password-ssh`, or explicitly configure SSH after bootstrap:

```bash
mise run ssh --profile personal --config "$HOME/.config/dev-machine-setup.toml"
```

The direct `ssh` task does not ask for consent again. The Mac app and
1Password command-line package inventories are independent of the SSH
choice, so declining SSH management does not exclude those packages.

On headless Ubuntu, forward the SSH agent from your client. When
`SSH_AUTH_SOCK` exists, setup uses the literal `IdentityAgent "SSH_AUTH_SOCK"`
rather than saving its temporary socket path. Otherwise it uses
`~/.1password/agent.sock`. Headless bootstrap does not install the Linux
desktop app.

## Manage dotfiles and runtimes

### Install or refresh dotfiles

Setup delegates to the configured dotfiles repository's `install.sh`.
Review that repository before running it. Its shell configuration must
support your platform and activate mise. To omit it, use
`--skip-dotfiles` during setup; to install it later, run:

```bash
mise run dotfiles --profile personal --config "$HOME/.config/dev-machine-setup.toml"
```

By default, each enabled run fetches and fast-forwards `~/.dotfiles` to
the latest `master`. To select a reviewed branch, tag or commit, set
`dotfiles_version` at the root of your local configuration file. Pass that
file on subsequent runs too. Changing this repository does not change the
external dotfiles revision.

Setup refuses dirty checkouts, divergent branch updates and an origin that
differs from `dotfiles_repo`. Save local work and resolve the reported
condition before retrying. Before leaving an unreferenced detached commit,
save it on a branch. Setup does not reset local work or rewrite origin.

Before invoking the external installer, setup backs up non-symlink paths
listed in `dotfiles_conflict_paths` under `~/.dev-setup-backups`. The default
list contains `.agents/.skill-lock.json`. This does not guarantee that the
external installer backs up every file it manages. Existing backup
directories remain untouched.

After installation, start a fresh login shell:

```bash
exec zsh -l
```

### Understand shell and runtime settings

The machine's runtime settings live in
`~/.config/mise/conf.d/dev-machine-setup.toml`. Compatible dotfiles use an
adjacent `dotfiles.toml` fragment. Setup honours `MISE_CONFIG_DIR` and
`XDG_CONFIG_HOME`; it preserves user mise settings and refuses to write
through externally symlinked configuration directories. Tools selected by
another profile remain in the machine-managed fragment.

Compatible dotfiles should support project `.nvmrc` and `.node-version`
files and preserve a custom `PNPM_HOME`. When dotfiles are disabled,
bootstrap configures Homebrew and mise in regular shell files. Selected
components add their own shell integration. Setup does not edit symlinked
shell files owned by another repository; those files must activate mise
and source fzf themselves.

### Change Node without losing global packages

Run the `node` task to install the Node ecosystem independently:

```bash
mise run node --profile personal --config "$HOME/.config/dev-machine-setup.toml"
```

Setup preserves npm globals at their installed versions from the previous
mise runtime, nvm's default and Homebrew Node. Existing target packages win.
It reports version conflicts, linked or unreadable packages and other nvm
versions rather than silently discarding them. It honours an explicit npm
prefix without rewriting `.npmrc` and keeps old runtimes.

Homebrew Node remains linked until the target runs, the package transfer
succeeds and the default configuration is saved. Conflicting user mise
settings stop this change. nvm and Homebrew sources are read only before the
machine fragment first declares Node; later runs do not restore packages
you deliberately uninstalled.

If a transfer fails, correct the reported cause and rerun the same command
with the same profile and configuration. The adjacent
`dev-machine-setup.node.json` records the requested version selector and
pending source. Setup retains the working pin and resumes from that source.
If the source was removed, restore it first. Do not delete pending state
or remove old runtimes to bypass a failure.

## Update installed software

With default component choices, run:

```bash
mise run update
```

Updates cover installed software, not only the current profile's inventory:
Homebrew packages, machine-managed mise tools, npm and pnpm globals, Mac
App Store apps and Ollama models. Missing tools are skipped. Ubuntu system
updates are not included.

Pass your local configuration files when they contain runtime settings or
saved component choices. To exclude categories for one run:

```bash
mise run update --config "$HOME/.config/dev-machine-setup.toml" \
  --skip app-store --skip gui
```

Update accepts these four exclusions and honours their saved `[steps]` choices:

| Component | Maintenance scope |
|---|---|
| `cli` | Native formulae, CLI casks, non-Node mise tools and Ollama models. |
| `gui` | Other installed casks. |
| `node` | Managed Node, npm and pnpm. |
| `app-store` | Mac App Store apps through `mas upgrade`. |

Skipping App Store maintenance does not change Apple's automatic updates.
Exclusions filter whole categories. Cleanup is limited to included
packages, but Homebrew can still upgrade their dependencies. Maintenance
preserves Homebrew pinning and non-greedy cask defaults. Non-Node mise
upgrades keep old versions; Node retains its working pin until the new
target and package transfer succeed.

Independent components continue after an error. The command returns failure
if any component failed. Resolve the reported cause, then retry with the
same options. Follow the Node recovery instructions above for pending transfers.

## Customise the package inventory

Each run combines four additive layers in order:

1. `packages/shared/`
2. `packages/shared/<personal|work>/`
3. `packages/<mac|linux>/`
4. `packages/<mac|linux>/<personal|work>/`

Each layer can contain `cli.toml`, `cli-optional.toml`, `gui.toml`,
`gui-optional.toml` and `app-store.toml`. Create only the layers you need;
the shared required CLI inventory must exist. Unknown inventory paths and
malformed declarations stop setup.

Add native packages under `[packages]` with `brew:`, `brew-cask:` or `mas:`
keys. Add mise tools under `[tools]` with their version selectors. Follow
existing declarations in [packages/](packages/) for platform selectors,
App Store IDs and greedy cask upgrades. Keep Mac desktop apps under
`packages/mac/`. Shared CLI casks need `os = "macos"` and separate Linux
providers where needed. Setup generates its Brewfile from this inventory.

Before installing a changed selection, inspect it:

```bash
mise run packages --profile personal
mise run packages --profile work
```

Required CLI failures stop setup. Optional CLI, GUI and App Store failures do
not stop the later steps. At the end, setup lists each failed item with its
probable cause and the next action, then returns failure. Setup skips App
Store apps that are already installed. It reports an App Store ID that has no
Mac app instead of trying to install it. Removing an inventory entry does not
uninstall an existing package. Before a greedy cask upgrade, setup compares
each app's own version with the version Homebrew offers. If every app of the
cask is already at that version or newer, for example because the app updated
itself, setup skips the upgrade so that Homebrew does not replace the app.
Setup upgrades as before when a version is not plain dotted numbers.

### Review package trust

Homebrew formulae and casks can execute Ruby with your user's privileges.
Review third-party sources and use fully qualified names. Setup grants
item-level trust to selected, fully qualified formulae and casks, not whole
taps. Package previews do not change the trust store.

Trust persists for later updates. Maintenance does not grant blanket trust
or restore permissions you revoked. If an update needs a missing permission,
review the package before restoring its item permission. For example, only
if you trust the selected [OMP formula](https://github.com/can1357/homebrew-tap):

```bash
brew trust --formula can1357/tap/omp
```

Then rerun the failed command. Setup does not disable Homebrew's trust
policy or bypass Gatekeeper. On Linux, the vfox 1Password CLI provider
downloads over HTTPS without an upstream checksum; HTTPS transport is not
an upstream checksum check.

## Remote access from an iPhone

Use `./remote-login.sh` to opt in to SSH access from your Tailscale
network (tailnet), for example from an iPhone running Secure ShellFish
or Moshi. The installer does not enable Remote Login. The key-only and
source-address limits apply to normal SSH **after FileVault unlocks**,
not every boot state or every service on the Mac.

### Check prerequisites and risks

Complete bootstrap to install mise and the locked Python. Run the commands
from this repository as your normal ARM64 macOS account, not root. Do not
prefix the mise commands with `sudo`: enablement and revocation request
sudo when needed. Enablement and its read-only readiness check need
connected Tailscale and phone public keys. Revocation needs neither.
Remote Login uses the configured Homebrew prefix in its SSH command path
but does not require the Homebrew executable.

Read these limits before enabling access:

- **FileVault has a separate pre-unlock SSH path.** After a restart, macOS
  can accept an SSH password to unlock the disk. The managed settings are
  on the locked data volume and do not apply then. See
  `man apple_ssh_and_filevault`. Use a strong login password. If you need
  key-only access in every boot state, do not enable the built-in Remote
  Login service with this command.
- **SSH listens beyond the tailnet.** Remote Login uses wildcard listeners
  and advertises SSH on the local area network (LAN) through Bonjour. `remote_login_sources`
  restricts authentication, not listener exposure. Configure and verify a
  local firewall before enablement. Do not assume a post-unlock application
  firewall protects FileVault's pre-unlock SSH.
- **Shields Up is not a LAN firewall.** Keep it on until setup and the
  policy checks succeed. No Remote Login command changes it. Releasing it
  allows inbound traffic to every service permitted by the full tailnet
  policy, including development servers if broad rules remain.
- **Use a fresh local terminal for changes.** Enablement, key changes and
  revocation must run at the Mac's local console, not over SSH or mosh.
  Commands reject detected SSH sessions using `SSH_CONNECTION`,
  `SSH_CLIENT` and `SSH_TTY`. Never clear these variables to bypass the
  check. Reused terminals can retain or omit them, so this guard cannot
  prove local-console use. The read-only `mise run remote-login-check`
  may run remotely.
- **Setup interrupts access and replaces keys.** It disables and unloads
  Remote Login before replacing its live configuration. It backs up and
  replaces all of `~/.ssh/authorized_keys` with the configured phone keys
  and limits Remote Login to your account. Existing SSH or mosh sessions
  may be interrupted, but listener shutdown and key removal do not reliably
  terminate them.

Install the Tailscale app on the Mac and iPhone, then sign in to the same
tailnet. While preparing access, explicitly block inbound tailnet traffic
on the Mac:

```bash
tailscale set --shields-up=true
```

Install Secure ShellFish, Moshi, or both on the iPhone. Moshi supports herdr;
in Secure ShellFish, you start herdr yourself. For mosh connections, install
mosh on the Mac from the personal CLI inventory:

```bash
mise run cli --profile personal
```

Install herdr from [herdr.dev](https://herdr.dev). SSH commands search
`~/.local/bin`, mise's shims, Homebrew's `bin` directory and `/usr/local/bin`.
Setup warns if it cannot find `mosh-server` or `herdr` on that path.

### Restrict the network policy and firewall

Before enabling SSH or releasing Shields Up, review the **whole** Tailscale
or Headscale access policy. Grants and legacy ACLs are additive: a narrow
rule does not cancel a broad allow rule. Remove or narrow every matching
broad grant and ACL, including access through groups or tags and rules
allowing all devices or all ports. This repository never changes the
control-server policy.

Allow only the intended iPhone to reach this Mac on TCP 22 for SSH and
UDP 60000–61000 for mosh. The following grant is illustrative, not a
complete policy. `100.100.100.10` and `100.100.100.20` are fictional;
replace them with your devices' addresses and include IPv6 identities
where applicable:

```jsonc
"hosts": { "iphone-example": "100.100.100.10", "mac-example": "100.100.100.20" },
"grants": [{ "src": ["iphone-example"], "dst": ["mac-example"], "ip": ["tcp:22", "udp:60000-61000"] }]
```

Run your control server's policy tests for both allowed and denied traffic:

- The intended iPhone may reach this Mac's SSH and mosh ports.
- Other devices may not reach those ports.
- The iPhone may not reach unrelated services on the Mac.

If you cannot inspect the full policy or run its tests, ask the provider
or control-server administrator to do so and confirm the results before
proceeding. Adding the example grant does not prove isolation.

Configure a local firewall, such as Little Snitch, before setup. Allow
incoming TCP 22 and UDP 60000–61000 only from the intended iPhone's tailnet
addresses. Block other sources, including LAN addresses. Review existing
rules and their precedence so a broad allow cannot override these limits.
Verify IPv4 and IPv6 rules. The setup command does not configure your
firewall. Allowing SSH is not a substitute for reviewing other exposed
services.

### Prepare phone keys and enable access

Complete the network policy and firewall checks first. Leave Shields Up on.
Only prepare keys for the phone apps you will use:

1. In Secure ShellFish, create a key on the iPhone's Secure Enclave. Its
   private key cannot leave the phone.
2. In Moshi, create an Ed25519 key. Enable **Biometric for keys** and keep
   credential sync off.
3. Copy each public key into this repository's `.ssh/` directory. Each file
   must contain exactly one public key line, without authorised-key
   options. Never copy a private key into the repository. For example,
   with Universal Clipboard available, copy the ShellFish public key on
   the iPhone and run this on the Mac:

   ```bash
   pbpaste > .ssh/iphone-shellfish.pub
   ```

4. In your local configuration file, list only the public key files you
   prepared. Put these settings at the root, before any table heading.
   For example, if you prepared both keys:

   ```toml
   # ~/.config/dev-machine-setup.toml
   remote_login_public_keys = ["iphone-shellfish.pub", "iphone-moshi.pub"]
   ```

5. Narrow `remote_login_sources` to the iPhone's Tailscale IPv4 and IPv6
   addresses if only that device should log in. The default accepts all
   tailnet addresses: `100.64.0.0/10` and `fd7a:115c:a1e0::/48`. If the
   phone's addresses change, update the list at the Mac. This authentication
   limit does not replace policy or firewall restrictions.
6. Review the complete key list. Every enablement replaces all of
   `~/.ssh/authorized_keys`; hand-added keys and Moshi Easy Pair keys not
   listed here will be removed. From a fresh local terminal, run:

   ```bash
   ./remote-login.sh --config "$HOME/.config/dev-machine-setup.toml"
   ```

   `mise run remote-login` is also available. The command checks keys,
   Tailscale and the SSH command path before requesting sudo or changing
   services, configuration or keys. Enter your sudo password if asked.
   Keep the reported connection details and SSH host key fingerprints.
   If setup fails, fix the reported cause and rerun locally. Do not enable
   Remote Login manually in System Settings or with `launchctl` to bypass
   a failed run.
7. Only after enablement succeeds and the full policy and firewall checks
   pass, manually release Shields Up:

   ```bash
   tailscale set --shields-up=false
   ```

8. Configure the phone as described below. Verify an actual phone
   connection, denied connections from other devices including LAN
   sources, and that unrelated Mac services remain unreachable. Setup or
   policy checks alone do not establish end-to-end access and isolation.
   If any result differs from the intended rules, restore Shields Up and
   [revoke access locally](#revoke-remote-access-including-offline) while
   you fix the policy or firewall. Shields Up alone does not block LAN access.

For an optional read-only readiness check before enablement, run:

```bash
mise run remote-login-check --config "$HOME/.config/dev-machine-setup.toml"
```

This checks keys, Tailscale and the SSH command path without sudo, writes
or service changes. It does not deploy configuration, validate effective
SSH settings, activate SSH, prove network isolation or guarantee that
enablement will succeed.

### SSH configuration restrictions and failure recovery

Setup uses macOS's native `/usr/sbin/sshd` and `/usr/bin/ssh-keygen` by
default, not Homebrew OpenSSH with its different configuration paths.
It creates host keys if needed and configures normal post-unlock SSH to
use keys only from `~/.ssh/authorized_keys`, for your account and the
configured source addresses. It also sets the SSH command path for mosh
and herdr.

The server configuration must not contain any `Match` block outside the
managed `010-remote-login.conf`. It must not set `DenyUsers`, `DenyGroups`,
`AllowGroups`, `RefuseConnection`, `ForceCommand`, `ChrootDirectory`,
`PermitTTY no` or `MaxSessions 0`. These rules could weaken access limits
or block your login. Setup rejects them rather than overriding them.
It also refuses a symlink or non-regular file at the managed configuration
path, `/etc/ssh/sshd_config.d/010-remote-login.conf` by default.

Setup disables startup and unloads the SSH listener before changing the
configuration. Native `sshd -t` and `sshd -T` checks must confirm that sshd
reads the managed file and that other settings do not weaken its limits
or block your account. Only after these checks pass does setup replace
keys and restrict the Remote Login access list to your account, removing
nested groups too.

If deployment or the effective-settings checks fail, setup restores the
previous managed file's content, owner, group and mode, or removes the new
file if none existed. It leaves Remote Login disabled and reports the
original failure. If activation or the SSH port check fails, it disables
startup and unloads the listener again. This is not a promise to undo all
changes from the run. Correct the reported cause and rerun locally; never
bypass the checks with manual enablement.

### Connect from the iPhone

1. In Tailscale, open Settings > VPN On Demand. Set Wi-Fi and Cellular to
   **Always**.
2. In each SSH app, add a server using the host name reported by
   `./remote-login.sh`, your Mac account name and port 22. Select the key
   you configured for that app.
3. In Moshi, leave the connection type at **Auto**.
4. Connect and compare the host key fingerprint with the fingerprints
   reported by setup. If they differ, stop and investigate before
   continuing.
5. In Moshi's session picker, open **Herdr** and tap a running session.
   If none exists, tap **Skip**, then run `herdr` to start one.
6. In Secure ShellFish, leave the tmux option off. Run `herdr` to attach to
   the default session, or `herdr session attach <name>` for a named session.

Work inside herdr keeps running on the Mac when the phone disconnects.
If `~/.ssh/config` uses the 1Password agent, outgoing SSH from a phone
session, such as `git push`, waits for approval on the Mac screen.

If the phone cannot connect, check Tailscale on both devices, the selected
key and account, and the reviewed policy and firewall rules. Do not widen
rules merely to get a connection. Investigate fingerprint mismatches
rather than accepting a changed host key blindly.

### Keep the Mac available

- Keep the Mac connected to power.
- For closed-lid use, start an Amphetamine session that prevents system
  sleep with the display closed. Never leave a closed, running Mac in a
  bag: it can overheat.
- After a restart, normal tailnet access needs someone to unlock FileVault
  and log in locally so the Tailscale app starts. This does not mean
  pre-unlock password SSH is unavailable through other network paths.
  Install macOS updates while you are at the Mac.
- Sign in to Tailscale again before the Mac's node key expires.
  `tailscale status --json` reports the date in `Self.KeyExpiry`.

### Replace or remove phone keys

For changes that leave at least one trusted key, add or remove filenames
in `remote_login_public_keys`, then rerun the enablement command above
with the same configuration file from a fresh local terminal.
It checks the revised inputs before changing access and
interrupts the listener while validating the effective SSH configuration.

Each enablement replaces all of `~/.ssh/authorized_keys`. Before changing
a differing nonempty file, it saves a backup at:

```text
~/.dev-setup-backups/<timestamp>/remote-login-<previous-content-hash>/authorized_keys
```

Backups are not active key files. Never restore a revoked phone key.
Hand-added keys and Moshi Easy Pair keys disappear unless included in the
configured list.

To remove the final key, [revoke remote access](#revoke-remote-access-including-offline).
Then remove its filename from `remote_login_public_keys` so later setup
cannot reinstall it. An empty key list deliberately fails enablement; it does
not request revocation. Removing a key blocks new authentication, not
access through an existing SSH or mosh session.

### Revoke remote access, including offline

Setting `steps.remote-login` to false does not undo earlier enablement.
Revocation needs the bootstrapped mise/Python command interface and sudo,
but no Homebrew executable, phone keys or working Tailscale connection.
From a fresh local terminal as your normal user, run:

```bash
mise run remote-login-revoke --config "$HOME/.config/dev-machine-setup.toml"
```

This explicitly sets `revoke_remote_login=true`, disables SSH startup,
unloads the listener if present, and backs up then clears your account's
`~/.ssh/authorized_keys`. It retains the managed SSH server configuration.
Revocation takes precedence if both enablement and revocation are selected.
Neither normal full setup nor a false revoke flag revokes access.

If Tailscale is available, also block inbound tailnet traffic:

```bash
tailscale set --shields-up=true
```

Revocation does not change Shields Up or the control-server policy.
**Listener shutdown and key removal do not end all existing SSH or mosh
sessions.** Follow the incident steps if an active session is untrusted.

### Respond to a lost or compromised phone

1. Revoke or remove the iPhone in the tailnet control server. Ask its
   administrator if you cannot do this yourself. Do not rely on device
   removal alone to terminate existing Mac sessions.
2. At the Mac's local console, run the revocation command above. If
   Tailscale is available, also run `tailscale set --shields-up=true`.
   Remove the lost phone's key filenames from `remote_login_public_keys`.
3. Before terminating anything, identify established SSH connections,
   mosh UDP listeners and their process trees:

   ```bash
   sudo lsof -nP -iTCP -sTCP:ESTABLISHED
   sudo lsof -nP -iUDP
   ps ax -o pid=,ppid=,user=,tty=,command=
   ```

   Match remote addresses and ports to the affected account's `sshd`
   child processes and `mosh-server` processes. Inspect their child shells
   and jobs too: stopping one parent may not end every child. If you
   cannot attribute the connection, treat all remote sessions for that
   account as suspect and review them individually.
4. For each confirmed remote-session PID, verify it immediately before
   signalling it. Replace `<PID>` with the numeric PID; do not paste the
   placeholder literally:

   ```bash
   ps -p <PID> -o pid=,ppid=,user=,tty=,command=
   sudo kill -TERM <PID>
   ps -p <PID> -o pid=,ppid=,user=,tty=,command=
   ```

   Repeat the connection and process listings to confirm that the
   affected transports have gone. If a process remains, inspect it again
   before considering `sudo kill -KILL <PID>`: forced termination can
   lose work. Do not kill all account processes, terminal sessions or
   herdr wholesale. Herdr work can survive transport disconnection;
   inspect suspect work separately and preserve unrelated local sessions.
5. Review what the compromised session could access, including credentials
   and jobs it started. Rotate affected credentials where needed.
   Re-enable access only with trusted replacement keys, reviewed policy
   and firewall rules, and a successful `./remote-login.sh` run. Then
   release Shields Up manually and repeat the real connection and denial
   checks described above.

## Check the setup files

The checks do not install packages or change machine settings. They use
temporary directories and substitute privileged commands. On macOS, they
also validate temporary SSH configurations with native `sshd -T`. These
checks do not prove that every package installs, or that a phone can connect
while other network paths remain blocked.

Complete bootstrap first. Checks require Python 3.11 or newer and
[Bats](https://github.com/bats-core/bats-core), the Bash Automated Testing
System. Both Mac profiles include `bats-core`. On Ubuntu, or before Mac CLI
installation, install it explicitly through Homebrew:

```bash
brew install bats-core
```

Run the full checks, or the shell suite alone:

```bash
mise run check
mise run check-shell
```

Without mise, use `python3 -B scripts/check.py` or `bats tests/shell`.
The full command fails if Bats is missing; it does not silently skip the
shell suite.

## Troubleshoot setup

| Symptom | Action |
|---|---|
| Unsupported platform or root refusal | Use native ARM64 macOS or Ubuntu as a normal user with sudo access. Do not bypass the guard. |
| Missing mise or helper Python | Complete `./install.sh --bootstrap-only`, then start a fresh login shell. |
| Profile conflict | Make the command, `DEVSETUP_PROFILE` and supplied files agree. |
| A local setting is ignored | Pass its file with `--config` on every relevant command. Check file order and platform tables. |
| Dotfiles update refused | Save local work, resolve divergent history, or correct the configured repository. Do not discard work to bypass the check. |
| Shell still runs old hooks | Start a fresh login shell with `exec zsh -l`. Sourcing `.zshrc` does not remove previously registered hooks. |
| Node transfer failed | Preserve the old runtime and pending state. Correct the error, then rerun with the same configuration. |
| Package or App Store installation failed | Follow the advice in the list at the end of the output, for example remove a leftover upgrade backup or sign in to the App Store. Then retry the affected component. |
| Remote Login refuses a session or fails its checks | Use a fresh local Mac terminal and follow the remote access guide. Never bypass a failed run by enabling SSH manually. |

Repository maintenance guidance is in [AGENTS.md](AGENTS.md).
