# Development Machine Setup

Configure and maintain an ARM64 development machine running macOS or
headless Ubuntu. Choose a `personal` or `work` profile, then use the same
commands to install software, configure your environment and keep it updated.

The repository aims to:

- Provide repeatable setup with Brewfiles and a mise tools file you can review and customise.
- Let you run the full setup or select individual components.
- Keep SSH client changes and Mac Remote Login opt-in.
- Preserve local dotfiles work and your own mise settings.

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
macOS preferences and Dock layout. Read [mise.toml](mise.toml),
[mise.macos.toml](mise.macos.toml), [mise.linux.toml](mise.linux.toml),
[mise.ssh.toml](mise.ssh.toml), [the package inventories](packages/) and
[mise/conf.d/tools.toml](mise/conf.d/tools.toml). Use
[local settings](#configure-your-machine) to supply your own values or
exclude components you do not want.

## Set up a machine

### Run the installer

1. Download and extract the repository, then open a terminal in its directory.
   If Git is already available, you can clone it instead:

   ```bash
   git clone https://github.com/mintuz/machine.git
   cd machine
   ```

2. Review the defaults and prepare any local settings before continuing.
   For a personal machine, run:

   ```bash
   ./install.sh personal
   ```

   For a work machine, use `./install.sh work` instead.

3. Review the SSH and dotfiles choices before bootstrap. The SSH prompt
   defaults to **No**. Ubuntu also asks whether to install dotfiles.
   Dotfiles default to enabled; Enter keeps that choice. Unattended runs
   preserve SSH unless `--1password-ssh` is explicit and install dotfiles
   unless `--skip-dotfiles` is explicit.

4. Follow the bootstrap prompts. Setup installs OS prerequisites,
   Homebrew, a checksum-verified mise executable and the locked helper Python.
   If macOS requests Command Line Tools, finish that installation, then
   rerun the same command. Ubuntu uses `apt` for bootstrap prerequisites
   and Zsh; it does not run a system upgrade. Setup asks for your sudo
   password once, for the login shell and the Mac update check.

To preserve SSH settings and omit the external dotfiles installation:

```bash
./install.sh personal --keep-ssh --skip-dotfiles
```

This does not prevent setup from configuring regular shell files. Use
[component exclusions](#choose-what-to-install) to control those
operations too. Explicit `--dotfiles` and `--skip-dotfiles` work on both OSes.

After the prerequisites, full setup is one `mise bootstrap` run from the
checkout. In order it installs the selected Brewfiles and the fzf
integration, creates `~/.ssh` and `~/.gnupg`, installs Oh My Zsh, clones or
updates `~/.dotfiles` and the zsh-autosuggestions plugin, writes the managed
files (tools link, global Git ignore file and, when chosen, the SSH client
files), applies the Git settings and on macOS the preferences and Dock,
sets the login shell, adds the shell startup blocks, installs the mise
tools and runs the dotfiles installer. Mac-only parts do not run on Ubuntu.

The installer **never enables Remote Login**. Set up
[remote access](#remote-access-from-an-iphone) separately. Installing
Tailscale or 1Password does not grant consent to configure SSH. Sign-in and
agent or network configuration remain manual.

### Install bootstrap tools only

To prepare the command interface without running full setup:

```bash
./install.sh --bootstrap-only
```

On macOS, `./new-mac.sh` is a shortcut for this operation. It installs the
prerequisites, then applies only the private directories, the login shell
and the shell startup blocks. It does not install packages or apps, does
not configure SSH and does not ask about or install external dotfiles.
After bootstrap, use the commands below to inspect packages or configure
selected components.

## Command reference

After bootstrap, open a fresh login shell so it loads mise. Run these
commands from the repository directory. Except for `setup` and
`bootstrap-only`, tasks do not prompt for feature choices; each one applies
a set of `mise bootstrap` parts for the profile.

| Command | Purpose |
|---|---|
| `mise run setup personal` | Run the installer, including bootstrap and consent prompts. |
| `mise run bootstrap-only` | Run bootstrap without full setup. |
| `mise run packages --profile work` | Show everything full setup would do for the profile, without changes. |
| `mise run install --profile work` | Apply every part for the profile without prerequisites, prompts or SSH. |
| `mise run cli --profile work` | Install every selected Brewfile (CLI, GUI and App Store) and the fzf integration, write the managed files and install every mise tool. |
| `mise run git` | Copy the global Git ignore file and apply the global Git settings. |
| `mise run zsh` | Set the login shell, install Oh My Zsh and its plugin and refresh the shell startup blocks (also refreshes `~/.dotfiles`). |
| `mise run dotfiles` | Clone or fast-forward the external dotfiles and run their installer. |
| `mise run osx` | Apply the macOS preferences, Library visibility, update check and Dock layout. |
| `mise run ssh` | Configure the 1Password SSH client setup; the previous `~/.ssh/config` stays in mise history. |
| `mise run update` | Update all installed software, regardless of profile. |
| `mise run remote-login-check` | Check Mac Remote Login prerequisites without changes. |
| `mise run remote-login` | Enable Mac remote access after the security prerequisites are met. |
| `mise run remote-login-revoke` | Disable Mac Remote Login and clear this account's authorised keys. |
| `mise run check` | Run the non-installing repository checks. |
| `mise run check-shell` | Run the shell behaviour checks. |

Use `--profile personal|work` with component tasks. The installer uses a
positional profile instead. For task-specific help:

```bash
mise run cli --help
```

To inspect both selections before changing anything:

```bash
mise run packages --profile personal
mise run packages --profile work
```

The preview prints every hook command, file, repository, preference and
tool that `mise bootstrap` would apply; hooks are printed, not run. Tasks do
not automatically install missing runtimes, so complete bootstrap first.
The `install`, `zsh` and `osx` tasks ask for sudo once; the others need no
sudo. None of them touch Remote Login; follow the
[remote access guide](#remote-access-from-an-iphone) for that.

## Configure your machine

### Create local settings

Setup values live in the mise files: `[vars]` in `mise.toml` holds the Git
identity; `mise.macos.toml` and `mise.linux.toml` hold the Homebrew prefix,
the 1Password agent socket and, on macOS, the preferences and the Dock
list; `mise.ssh.toml` holds the public-key filenames; `[bootstrap.repos]`
in `mise.toml` holds the dotfiles repository and revision. To use your own
values without editing tracked files, create `mise.local.toml` in the
checkout (Git ignores it). A later file wins for `[vars]`, and a repository
entry with the same path replaces the default one. This example changes
the Git identity and pins the dotfiles to a tag:

```toml
# mise.local.toml
[vars]
git_name = "Your Name"
git_email = "you@example.com"

[bootstrap.repos]
"~/.dotfiles" = { url = "https://github.com/you/dotfiles.git", ref = "v1" }
```

mise loads the file automatically for every task and for the installer;
`mise run packages` shows the result. mise reads `mise.local.toml` before
the platform file, so a value that the platform file sets (the Homebrew
prefix, the agent socket, the Dock list) must be overridden in
`mise.macos.local.toml` or `mise.linux.local.toml` instead; Git ignores
those too. To omit a component for one run, use
[`--skip`](#choose-what-to-install). To leave the Dock alone on every run,
set `dock_items = ""` under `[vars]` in `mise.macos.local.toml`. macOS
preferences cannot be removed from a local file, only overridden with a
different value; remove the entry from `mise.macos.toml` instead.

Only the Remote Login commands read [defaults.toml](defaults.toml) and a
`--config` file. Pass that file on each Remote Login command that needs it;
relative paths resolve from the directory where you invoked the command,
including through mise. Within each file, `[mac]` or `[linux]` overrides
shared settings; your file overrides the defaults; the explicit flags take
precedence. Unknown steps and non-boolean step choices are errors; other
unknown keys are ignored.

### Select a profile

The default profile is `personal`. Select `work` with the installer's
positional argument, `--profile work` on tasks, or `DEVSETUP_PROFILE`.
Configuration files cannot set the profile.

The command-line and environment values must agree. A command-line profile
does not override a conflicting environment variable. Unset
`DEVSETUP_PROFILE` or make these values agree before changing profiles.
Setup does not save your per-run profile choice.

Profiles select additive package layers and the primary managed GitHub
SSH key. They do not select separate Git identities or uninstall packages
from another profile. Set `git_name` and `git_email` explicitly.

### Adjust macOS preferences and the Dock

`mise.macos.toml` declares the preferences as typed
`[bootstrap.macos.defaults]` entries, one table per domain. mise writes a
value only when it is unset or differs, and never deletes a preference.
The two values that contain your home directory (the Finder new-window
target and the screenshot location), `chflags nohidden ~/Library`, the
system-wide automatic update check (with sudo) and `killall Finder` are in
the `post-defaults` hook, together with the Dock:

```toml
[bootstrap.macos.defaults."com.apple.finder"]
ShowPathbar = true

[vars]
dock_items = """
/System/Applications/Home.app
spacer
/Applications/Safari.app
"""
```

`dock_items` has one absolute `.app` path or the word `spacer` per line, in
Dock order. The hook removes every tile, adds each line with `dockutil`,
reports and skips an app that is not installed, and restarts the Dock. An
empty list leaves the Dock unchanged. `mise run check` validates the list.
Skip `osx` to omit the preferences, the hook and the Dock together.

## Choose what to install

Use repeated `--skip` options to omit components for one full setup run:

```bash
./install.sh personal --skip app-store --skip osx
```

Supported names are `ssh`, `cli`, `gui`, `app-store`, `zsh`, `osx` and
`dotfiles`. All default to enabled except `ssh`. Each name maps onto one or
more `mise bootstrap` parts, and a part's hooks are skipped with it:

| Name | mise parts | Also skipped |
|---|---|---|
| `cli` | `packages,tools` | Every Brewfile, the fzf integration and every mise tool. |
| `gui`, `app-store` | `packages` | Every Brewfile, including `Brewfile.cli`, and the fzf integration. A GUI-only or App Store-only exclusion is not available; remove the lines from the Brewfile instead. |
| `zsh` | `user` | The login shell and the shell startup blocks. Oh My Zsh and its plugin still install. |
| `osx` | `macos-defaults` | The preferences, Library visibility, the update check and the Dock. |
| `dotfiles` | `repos,task` | The `~/.dotfiles` checkout and its installer, and the zsh-autosuggestions clone. |
| `ssh` | none | Leaves the `ssh` environment out, like answering No. |

There is no separate exclusion for the Git settings, the global Git ignore
file, the private directories or the fzf integration. Contradictory
explicit flags fail. Bootstrap and the prerequisite check cannot be
skipped. `--skip` is for the installer, not the tasks or `update`. To omit
a part from a task run, call mise directly, for example
`mise -E work bootstrap --skip macos-defaults --yes`.

**Skipping is not uninstalling or revoking.** It leaves previous settings
and installed software in place. Included components may still install
native prerequisites. Homebrew dependencies and the external dotfiles
installer can have their own effects.

`mise run cli` installs every selected Brewfile, the fzf shell integration
and every mise tool, including Node, pnpm and the `npm:` providers.
Tailscale is a Mac GUI package, not an App Store package. Its sign-in and
required macOS extension approval remain manual.

## Configure SSH with 1Password

SSH client setup controls outgoing connections, such as GitHub access. It
is separate from the Mac's incoming Remote Login service.

The installer's SSH prompt defaults to No. Declining leaves existing SSH
files and agents untouched, including settings from an earlier opt-in.
The choice is not saved for the next invocation.

Before opting in, review the public-key filenames in `mise.ssh.toml` and
the template in `templates/ssh_config`. Only public keys belong in this
repository's `.ssh/` directory. Opting in selects the `ssh` mise
environment: `mise bootstrap` renders `~/.ssh/config` (mode 0600) and
copies the two public keys, with the profile's key as the primary GitHub
key and the other key for `github-alt.com`. When `~/.ssh/config` already
exists, setup first runs `mise dot track ~/.ssh/config`, so the previous
file stays in mise history: `mise dot history --path ~/.ssh/config` lists
the versions and `mise dot rollback ~/.ssh/config` restores one. Tracking
adds one entry to your global mise configuration. Nothing else in `~/.ssh`
is backed up.

Full setup installs the 1Password app on macOS from `Brewfile.gui`
before it writes the SSH files. Sign in to 1Password and enable its SSH
agent manually. Run full setup with `--1password-ssh`, or configure SSH
afterwards:

```bash
mise run ssh --profile personal
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

Setup delegates to the external dotfiles repository's `install.sh`, which
`mise bootstrap` runs as its last step. Review that repository before
running it. Its shell configuration must support your platform and
activate mise. To omit it, use `--skip-dotfiles` during setup; to install
it later, run:

```bash
mise run dotfiles --profile personal
```

`[bootstrap.repos]` in `mise.toml` declares `~/.dotfiles` with
`ref = "master"`. Each enabled run clones a missing checkout, or fetches and
fast-forwards a clean one to that ref. To select a reviewed branch, tag or
commit, replace the entry in `mise.local.toml` (see
[local settings](#create-local-settings)).

mise refuses a checkout with local changes or untracked files, an origin
that differs from the declared URL, a directory that is not a Git
checkout and a branch that cannot fast-forward. Save local work and resolve
the reported condition before retrying; mise does not reset local work or
rewrite origin. mise does not check for unreferenced detached commits
before moving a pinned checkout: put such commits on a branch yourself
before changing the ref.

The external installer backs up the files it replaces. This repository
makes no backup of its own before running it.

After installation, start a fresh login shell:

```bash
exec zsh -l
```

### Understand shell and runtime settings

The tools this repository installs with mise are declared in
`mise/conf.d/tools.toml`. `mise bootstrap` links that file to
`~/.config/mise/conf.d/dev-machine-setup.toml`, so the tools are active in
every directory. Compatible dotfiles use an adjacent `dotfiles.toml` file.
mise refuses to replace an existing regular file at the link target and
leaves your other mise files alone. The link always goes to
`~/.config/mise/conf.d`; a custom `MISE_CONFIG_DIR` or `XDG_CONFIG_HOME` is
not followed. If an earlier version of this repository wrote a regular
`dev-machine-setup.toml` there, remove that file once before running setup
again.

Setup keeps one `# BEGIN dev-machine mise` block in `~/.zshrc` (both
platforms) and `~/.bashrc` (Ubuntu) with the Homebrew environment, mise
activation and the fzf source line. Ubuntu also gets a
`dev-machine oh-my-zsh` block in `~/.zshrc` and a `dev-machine Node and
pnpm` block in `~/.bashrc` (the external dotfiles export `PNPM_HOME` for
zsh). A block is added once and updated in place. A shell file that is a
symlink belongs to another repository, usually the external dotfiles:
setup prints a notice and leaves it unchanged, so those files must
activate mise and source fzf themselves. Compatible dotfiles should also
support project `.node-version` files.

## Update installed software

Run:

```bash
mise run update
```

This runs `scripts/update.sh`. It updates installed software, not only the
current profile's selection, and ignores configuration files and `--skip`.
In order, it runs `brew update`, `brew upgrade`, `brew cleanup -s`,
`mise upgrade --no-prune`, `npm update -g`, `pnpm update -g`, `mas upgrade`
on macOS and `ollama pull` for each downloaded Ollama model. Ubuntu system
updates are not included.

A component whose tool is missing is skipped and reported as skipped. pnpm
is skipped when `PNPM_HOME` is not set. Homebrew keeps its own semantics:
pinned packages stay pinned and `brew upgrade` is not greedy, so
self-updating apps are left alone. Mise upgrades keep old versions.

Each component runs even if an earlier one failed. The summary at the end
lists each component as completed, failed or skipped. The command returns
failure if any component failed. Resolve the reported cause, then rerun.

## Customise the package inventory

Brewfiles live in four additive layers:

1. `packages/shared/`
2. `packages/shared/<personal|work>/`
3. `packages/mac/`
4. `packages/mac/<personal|work>/`

Each layer can contain `Brewfile.cli`, `Brewfile.gui` and
`Brewfile.app-store`. Every file is optional; create only the layers you
need. There is no Linux layer: Ubuntu installs `packages/shared/` only.

Brewfiles use plain [Homebrew Bundle](https://docs.brew.sh/Brew-Bundle-and-Brewfile)
syntax. `mise bootstrap` runs `brew bundle install --file=<layer file>`
once per selected file from the `[bootstrap.hooks.pre-packages]` entries
in `mise.toml` (shared layers), `mise.macos.toml` (the `mac` layer) and
`mise.personal.toml` or `mise.work.toml` (profile layers). mise runs those
files in that order. A new layer file needs a hook line in the matching
mise file. Keep casks in `packages/mac/`:

```ruby
# packages/shared/Brewfile.cli
brew "ripgrep"
tap "can1357/tap"
brew "can1357/tap/omp", trusted: true

# packages/mac/Brewfile.gui
cask "raycast"
cask "claude-code", greedy: true

# packages/mac/Brewfile.app-store
mas "Things", id: 904280696
```

```toml
# mise.macos.toml
[bootstrap.hooks.pre-packages]
run = [
  '{{ vars.brew_bundle }}="{{ config_root }}/packages/mac/Brewfile.cli"',
]
```

mise tools are declared once, in `mise/conf.d/tools.toml`, with an `os`
list on entries for one platform. `mise bootstrap` links the file into your
global mise configuration and installs them with `mise install`. Give a CLI
cask a Linux provider with `os = ["linux"]` where one exists. A tool for
one profile only belongs in `mise.personal.toml` or `mise.work.toml`:

```toml
# mise/conf.d/tools.toml
[tools]
go = "latest"
"aqua:anthropics/claude-code" = { version = "latest", os = ["linux"] }
```

Before installing a changed selection, inspect it:

```bash
mise run packages --profile personal
mise run packages --profile work
```

This prints every hook command, the tools link and the tools that
`mise install` would add, without running them.

`Brewfile.cli` failures stop setup. GUI and App Store failures do not stop
it: the hook records the failure, bootstrap continues, and the final hook
lists the failures and returns failure. `brew bundle` adopts apps that are
already in `/Applications`, upgrades outdated items and leaves
self-updating apps alone unless the item says `greedy: true`. App Store
installation needs sign-in and the Mac app's ID. Removing an entry does not
uninstall an existing package.

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
| Profile conflict | Make the command and `DEVSETUP_PROFILE` agree. |
| A local setting is ignored | Put `[vars]` overrides in `mise.local.toml`, or in `mise.macos.local.toml`/`mise.linux.local.toml` for platform values; check with `mise run packages`. Remote Login settings need `--config` on every relevant command. |
| `mise bootstrap` refused `~/.dotfiles` or the plugin checkout | Commit, stash or remove local changes and untracked files, resolve divergent history, or correct the declared repository. Do not discard work to bypass the check. |
| `~/.zshrc` has no mise block | The file is a symlink to the external dotfiles; setup printed a notice and left it alone. Those dotfiles must activate mise and source fzf themselves. |
| Shell still runs old hooks | Start a fresh login shell with `exec zsh -l`. Sourcing `.zshrc` does not remove previously registered hooks. |
| mise tool installation failed | Correct the reported mise error, then rerun `mise run cli` with the same profile. If the link target already exists as a regular file, remove it first. |
| CLI package installation failed | `mise bootstrap` stops. Read the Homebrew output, fix the cause, then rerun `mise run cli`. A package that an inventory replaced, such as the disabled `tldr` formula or the `claude-code@latest` cask, must be removed by hand with `brew uninstall`. |
| GUI or App Store installation failed | Setup continues and lists the failures at the end from `~/.local/state/dev-machine-setup/bootstrap-issues`. Sign in to the App Store or fix the Homebrew error, then rerun `mise run cli`; `brew bundle` skips what is already installed. |
| Remote Login refuses a session or fails its checks | Use a fresh local Mac terminal and follow the remote access guide. Never bypass a failed run by enabling SSH manually. |

Repository maintenance guidance is in [AGENTS.md](AGENTS.md).
