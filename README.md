# Development Machine Setup

Set up **ARM64 macOS and headless Ubuntu** development machines with
[mise](https://mise.jdx.dev), Homebrew and small Python standard-library helpers.
Both operating systems support personal and work profiles. Intel machines,
Rosetta execution and other Linux distributions are not supported.

Mise owns runtime versions and the command interface. Homebrew owns native
formulae and Mac applications, including their post-install steps. Ansible,
Make and nvm are no longer provisioning dependencies. This is a single-release
cutover, not a second setup path alongside the old one.

Homebrew remains necessary: a real clean Ubuntu test with mise 2026.10.3's
native bottle installer linked Git but omitted certificate configuration,
so Git could not clone over HTTPS. Using Homebrew preserves formula
post-install behaviour without reproducing it in this repository.
The [architecture report](ARCHITECTURE-REPORT.md) records the earlier research.

## Quick start

Run these commands from the checkout as your normal user with sudo access:

```bash
./install.sh personal
# or
./install.sh work
```

On macOS, complete the Command Line Tools installation if bootstrap requests
it, then rerun the command. Bootstrap installs Homebrew, a checksummed
mise **2026.10.3** binary and the Python **3.14.8** release locked for both ARM
platforms in `mise.lock`. Ubuntu uses apt for bootstrap prerequisites and zsh.

For an existing installation, run the new `install.sh` once before using
targeted tasks such as `node` or `update`. The old bootstrap does not provide
the new mise/Python prerequisites. Commit or otherwise preserve local changes
in your dotfiles checkout first; setup refuses to discard them. Use
`--skip-dotfiles` if you want to migrate that checkout separately.

The 1Password SSH prompt defaults to **No**. No preserves existing SSH
configuration and agents, including configuration from an earlier opt-in.
Yes makes a unique backup, then replaces SSH configuration with the
1Password agent and the configured personal/work GitHub public keys.
Review `.ssh/` before opting in. The choice is not saved.

Without a terminal or an explicit flag, setup preserves SSH:

```bash
./install.sh work --1password-ssh
./install.sh personal --keep-ssh
```

**Remote Login is a separate step after installation.** The installer
does not prompt for it, run its preflight or enable it, even if a local
file sets `steps.remote-login = true`.

The default GUI step includes Tailscale. After setup, sign in and complete
the [Remote Login prerequisites](#before-you-start), network policy,
firewall and [phone-key preparation](#set-up-the-mac). A skipped or failed
GUI installation does not satisfy those prerequisites. Read the FileVault
limits before enabling access, and keep Shields Up on.

Enablement backs up and replaces your authorised keys and can interrupt
existing SSH sessions. From the Mac's local console, run one command:

```bash
./remote-login.sh
```

The command checks prerequisites before requesting sudo or changing access.
It then validates and enables Remote Login. You do not need to run a
separate preflight command first. To use a local configuration file:

```bash
./remote-login.sh --config ./local.toml
```

The launcher uses the bootstrapped mise/Python installation. Relative
configuration paths resolve from your current directory. For a read-only
readiness check without enablement, `mise run remote-login-check` remains
available.

Dotfiles install by default. On Ubuntu, interactive full setup asks
`Install your dotfiles? [Y/n]` before bootstrap. Enter and unattended runs
keep the default. These flags work on both operating systems:

```bash
./install.sh work --skip-dotfiles
./install.sh personal --dotfiles
```

Bootstrap-only runs do not ask about or install dotfiles. Install them later
with `mise run dotfiles`. See [Dotfiles and runtimes](#dotfiles-and-runtimes)
before migrating an existing checkout.

If you want 1Password SSH on a Mac that is not yet signed in:

```bash
./install.sh --bootstrap-only --1password-ssh
# Open 1Password, sign in, and enable its SSH agent.
./install.sh personal --1password-ssh
```

Sign in to the Mac App Store before installing its apps. `new-mac.sh` remains
the Mac bootstrap-only shortcut.

On Ubuntu, an existing `SSH_AUTH_SOCK` selects the literal
`IdentityAgent "SSH_AUTH_SOCK"`, not the session's temporary socket path.
Otherwise setup uses `~/.1password/agent.sock`. Headless users must
[forward their client agent](https://www.1password.dev/ssh/agent/forwarding).
Setup does not install the Linux desktop app, sign in to 1Password or enable
its agent. The SSH choice does not remove 1Password from the software
inventory: the Mac app and the CLI remain available independently.

For unattended setup, provide passwordless sudo for the setup user. The
wrapper reuses available authorisation and keeps it alive during the command.
If a password is needed, run from a terminal. The wrapper refuses to continue
without a terminal and removes temporary credential files on exit. Do not
run the whole installer or Python CLI as root.

## Commands

Except for setup and bootstrap-only, these commands require completed
bootstrap and do not prompt for feature choices.

| Command | Action |
| --- | --- |
| `mise run setup personal` / `mise run setup work` | Prompt, bootstrap and configure the selected profile |
| `mise run bootstrap-only` | Install prerequisites and shell activation |
| `mise run install --profile work` | Run full setup without bootstrap or prompts |
| `mise run packages --profile work` | Preview inventory selection without changes |
| `mise run cli --profile work` | Install native/non-Node CLI tools and fzf integration |
| `mise run gui` | Install or upgrade Mac applications |
| `mise run app-store` | Install Mac App Store apps |
| `mise run osx` / `mise run dock` | Apply macOS preferences / Dock layout |
| `mise run git` | Install Git and apply the configured identity and settings |
| `mise run zsh` | Configure the login shell, Oh My Zsh and autosuggestions |
| `mise run node` | Install Node, pnpm and npm-backed mise tools; preserve globals and configure pnpm |
| `mise run dotfiles` | Install or refresh the separate dotfiles repository |
| `mise run ssh --profile work` | Explicitly back up and configure 1Password SSH |
| `mise run remote-login-check` | Check Remote Login prerequisites read-only, without sudo |
| `./remote-login.sh` | Check prerequisites, then enable key-only tailnet Remote Login from the local console |
| `mise run remote-login-revoke` | Disable SSH startup/listener and back up then clear your authorised keys |
| `mise run update` | Update installed packages, runtimes, global packages and models |
| `mise run check` | Run shell behaviour, syntax, configuration and safety checks |
| `mise run check-shell` | Run only the Bats shell behaviour suite |

GUI, App Store, preferences and Dock actions skip Ubuntu. Remote Login
mutations are Mac-only and require their own explicit opt-in. Full setup
leaves SSH and Remote Login alone unless selected.

Use `--profile personal|work` or `DEVSETUP_PROFILE`. The default is personal;
selection is not remembered between runs. Conflicting or invalid selections
fail before bootstrap. `install.sh` takes the profile as a positional argument.
To pass help to a task rather than mise, use `mise run cli -- --help`.

The direct interface uses the same dispatcher:

```bash
mise exec -- python scripts/setup.py packages --profile work
mise run cli --check
```

`--check` does not install packages or change configuration. It is a limited
preview: several host actions report that they are not previewed. In
particular, Remote Login check mode does not deploy configuration, run the
effective-settings gate or activate SSH. Task auto-install is disabled;
bootstrap must install the locked Python before these tasks can run.

## Package inventory

Each run combines these additive layers, in order:

1. `packages/shared/`
2. `packages/shared/<personal|work>/`
3. `packages/<mac|linux>/`
4. `packages/<mac|linux>/<personal|work>/`

Each layer may contain `cli.toml`, `cli-optional.toml`, `gui.toml`,
`gui-optional.toml` and `app-store.toml`. Missing optional layers need no
placeholder files. The shared required CLI inventory must exist. Unknown
inventory paths and malformed declarations stop setup.

For example, put a shared work CLI in `packages/shared/work/cli.toml`:

```toml
[packages]
"brew:example-formula" = "latest"

[tools]
"example-mise-tool" = "latest"
```

These names are illustrative, not installable recommendations. Native package
keys use `brew:`, `brew-cask:` or `mas:`. Runtime declarations use `[tools]`
and mise version selectors. An entry can restrict itself to `os = "macos"`
or `os = "linux"`. CLI casks that need greedy upgrades use `greedy = true`.
App Store entries use their numeric ID and display name.

The runner generates a Brewfile from the selected TOML; there is no second
maintained Brewfile. Keep Mac desktop apps under `packages/mac/`. Shared CLI
casks have Mac selectors and separate Linux tool providers where needed.
A personal Ubuntu-only tool belongs in `packages/linux/personal/cli.toml`.

Required CLI failures stop setup. Optional CLI, GUI and App Store installation
failures are reported while setup continues. Profile changes and inventory
removals do not uninstall existing packages. `tlrc` replaces the disabled
`tldr` formula and provides the same
`tldr` command. Ansible and nvm leave the inventory. Node, pnpm, Yarn, Deno,
Go and xcodes use mise; xcodes uses its published release rather than a
third-party Homebrew formula. The other native package declarations remain.

[OMP](https://omp.sh/) is a required shared CLI package for both profiles
on macOS and Ubuntu, installed through
[`can1357/tap/omp`](https://github.com/can1357/homebrew-tap).

The generated Brewfile grants item-level Homebrew trust to each selected,
fully qualified formula or cask, such as `can1357/tap/omp`. Use fully
qualified names for third-party packages; do not rely on a previously
tapped repository to resolve a short name. Setup does not trust whole taps
or disable Homebrew's trust checks. Formulae and casks can execute Ruby code
with your user's privileges; review third-party sources before adding them.

Trust persists for later updates. Maintenance does not grant blanket trust
to other installed taps or restore permissions that you revoked. Review
and restore a missing item permission explicitly if an update needs it.

If an older checkout stops with an untrusted `can1357/tap/omp` error, and
you trust that formula, grant permission to that item:

```bash
brew trust --formula can1357/tap/omp
```

Then rerun the original setup command with the same profile and options.

The [Tailscale Mac app](https://formulae.brew.sh/cask/tailscale-app) is in
the shared Mac GUI inventory as `tailscale-app`, not the App Store
inventory. Skipping `app-store` does not skip it; skipping `gui` does.
Tailscale sign-in and any required macOS extension approval remain manual.

Authy and Gas Mask are no longer in the installation inventory. Authy is
absent from the official cask catalogue, and
[`gas-mask`](https://formulae.brew.sh/cask/gas-mask) is disabled because it
fails Gatekeeper checks. This removal leaves existing installations
untouched. Setup does not bypass Gatekeeper or use another tap to install
these unavailable packages.

## Configuration

`defaults.toml` contains shared preferences and `[mac]` / `[linux]` defaults.
Pass repeatable `--config PATH` options to load explicit local TOML overrides.
Within each file, the selected platform table overrides shared values.
Later files override earlier files; command-line feature flags take precedence.

```bash
mise run git --profile work --config "$HOME/.config/dev-machine-setup.toml"
```

- `git_name` and `git_email` set one Git identity. A profile selects package
  layers and the primary managed GitHub SSH key, not a different Git identity.
- `steps.ssh` defaults to false. `mise run ssh` is the explicit
  standalone opt-in. `ssh_agent_socket` and the public key filenames remain
  configurable. Each managed write has a unique backup.
- `steps.dotfiles` defaults to true. Use `--skip dotfiles` or
  `--skip-dotfiles` for one setup run. `dotfiles_repo` and
  `dotfiles_version` select the external checkout.
- `steps.remote-login` and `revoke_remote_login` default to false.
  Disabling the step leaves earlier access unchanged. Explicit revocation
  wins, including with `remote-login --revoke-remote-login`.
  Phone keys, source ranges and `tailscale_cli` remain configurable.
- `pnpm_home` and `pnpm_global_packages` control pnpm global packages.
- `brew_prefix` and `brew` select the native package prefix and executable.
  Defaults are `/opt/homebrew` on macOS and `/home/linuxbrew/.linuxbrew` on
  Ubuntu. Bootstrap uses these standard ARM prefixes.
- `macos_preferences` and `dock_items` under `[mac]` hold the arguments for
  macOS preferences and Dock entries. Override these lists in your local
  file instead of editing Python. `{home}` in preference values expands to
  your home directory. Dock paths may start with `~/`.
  An empty Dock list leaves the Dock untouched. An empty preferences list
  skips configurable defaults, but Library visibility and automatic-update
  checks still run; skip `osx` to leave all macOS preferences untouched.
  Setup no longer writes `LSQuarantine=false`; it does not undo that setting
  if an earlier run applied it.

Unknown settings, unknown steps and non-boolean step choices are errors.
The former root settings `manage_ssh_config`, `install_dotfiles` and
`manage_remote_login` are replaced by the corresponding `[steps]` entries;
update local files before running this version.

### Select setup and maintenance components

Skip named components for one run:

```bash
./install.sh personal --skip app-store --skip dock
mise run install --profile work --skip app-store
mise run update --skip app-store
```

For saved choices, create a local file and pass it explicitly to each run:

```toml
# ~/.config/dev-machine-setup.toml
[mac.steps]
app-store = false
dock = false
```

```bash
./install.sh personal --config "$HOME/.config/dev-machine-setup.toml"
mise run update --config "$HOME/.config/dev-machine-setup.toml"
mise run packages --config "$HOME/.config/dev-machine-setup.toml"
```

Supported names are `ssh`, `git`, `cli`, `remote-login`, `gui`, `zsh`,
`app-store`, `osx`, `node`, `dotfiles` and `dock`. The `[steps]` table merges
by key: shared values, then the selected platform, then each explicit file.
Command-line choices take precedence. Ordinary lists replace earlier lists.
Relative configuration paths resolve from the directory where you invoked
the command, including paths supplied through mise.

The installer preserves its pre-bootstrap SSH consent prompt. No, Enter
and unattended defaults preserve SSH client configuration, even if a file
enables that step. Remote Login enablement is always excluded by the
installer; use `./remote-login.sh` afterwards. Enter at the dotfiles prompt keeps the configured
choice; an explicit Yes or No overrides it. If no profile argument or
environment value was supplied, the file may select the profile.
The locked Python validates TOML after bootstrap, so malformed configuration
does not promise zero bootstrap changes.

Skipping means leave the component's current state alone. It does not
uninstall packages, undo settings or prevent retained components from
installing their native prerequisites. For example, skipping `git` skips
Git configuration, not the Git executable needed for dotfiles. Skipping
`cli` also skips fzf integration. The separate `node` step owns Node, pnpm,
all `npm:` mise providers and npm migration; skipping it does not run those
operations inside `cli`. Homebrew dependencies and the external dotfiles
installer can still have their own effects.

`update` accepts `--skip cli`, `gui`, `node` and `app-store`, and honours the
same saved choices. `app-store = false` excludes both app installation and
`mas upgrade`; it does not change Apple's own automatic updates. `cli`
owns native formulae, CLI casks, non-Node mise tools and Ollama models.
`gui` owns other installed casks. `node` owns managed Node/npm/pnpm updates.
Other setup components have no maintenance operation.

A direct component command is an explicit one-off request:
`mise run app-store --config PATH` runs even when the file excludes
App Store from aggregate setup. The command reports this override.
Contradictory explicit flags are errors. Mandatory bootstrap and preflight
checks are not selectable steps, and no exclusion suppresses revocation.
`--check` uses the selected components but remains a limited preview.


Backups use `~/.dev-setup-backups`. Existing `~/.mac-setup-backups` directories
remain untouched.

## Dotfiles and runtimes

Dotfiles and agent skills remain separate repositories. This repository
delegates dotfiles installation to that repository's `install.sh`.
By default, each enabled dotfiles run fetches and fast-forwards the checkout
to the latest `master` branch before running the installer. There is no
fixed commit pin in `defaults.toml`.

Explicit `dotfiles_version` overrides are still honoured. Remove any old
commit override from your local configuration to follow `master`.

Merge the [portable dotfiles PR](https://github.com/mintuz/.dotfiles/pull/8)
before releasing this provisioning migration. Until it merges, dotfiles
`master` still contains the old nvm startup hook. Testing this repository's
branch alone does not select the companion dotfiles branch.

After bootstrap and Node installation succeed, test the companion branch
from this repository's directory with a temporary configuration override:

```bash
dotfiles_test_config="$(mktemp)"
export dotfiles_test_config
printf 'dotfiles_version = "feat/portable-mise-shell"\n' > "$dotfiles_test_config"
printf 'Override file: %s\n' "$dotfiles_test_config"
mise run dotfiles --config "$dotfiles_test_config"
```

Keep the same profile and configuration options used for setup, and pass
this override last. Preserve local dotfiles changes if setup refuses the
checkout; do not reset them. After a successful installation, run
`exec zsh -l` to replace the old shell and its registered hooks. Sourcing
the new `.zshrc` alone does not remove the old `load-nvmrc` hook.
Until the companion PR merges, pass the override on later setup or dotfiles
runs too. Keep the printed file path for use in new terminal sessions.
After the PR merges, remove the temporary file and omit the override to
follow `master`.

Setup refuses a dirty dotfiles checkout. Branch updates are fast-forward
only. An exact revision checks out that commit without deleting local
branches. Before moving away from an unreferenced detached commit, setup
requires you to save it on a branch. It never resets or discards your work.
An existing checkout's origin must also match `dotfiles_repo`. A mismatch
stops before fetching or running its installer. Save your local work, then
move the checkout aside or select its actual repository; setup never
rewrites origin silently.


The dotfiles shell detects the platform, activates mise, preserves a custom
`PNPM_HOME` and reads project `.nvmrc` / `.node-version` files. Its
`~/.config/mise/conf.d/dotfiles.toml` holds portable shell behaviour. This
repository owns the adjacent `dev-machine-setup.toml` runtime fragment and
does not overwrite user configuration or write through symlinked config
directories. Existing tools from another profile remain in the fragment.

When dotfiles are skipped, setup adds Homebrew and mise activation to regular
shell files. It does not edit shell files that are symlinks into another
repository. Externally managed shell files must activate mise and source the
fzf integration themselves.

Node must run and its default configuration must be saved before Homebrew
Node is unlinked. Setup transfers npm globals at their installed versions
from the previous mise runtime, nvm's default runtime and Homebrew Node.
Existing target packages win, then earlier sources win; conflicts and
packages that cannot be transferred are reported. Legacy providers transfer
only before the machine fragment first declares Node. Later runs do not
restore packages you uninstall. Other nvm versions are reported, not removed.
A transfer or configuration failure keeps the old provider available and
returns failure. A failed probe of the previous npm directory is an error,
not an empty package list. Custom npm prefixes are honoured; `.npmrc` is not
rewritten. Old nvm installations are not deleted.
Node probes must match mise's installed-runtime metadata. A Node executable
found only on `PATH` is not accepted as a mise migration source or target.
When mise reports no usable installed Node runtime, setup skips the
previous-runtime execution probe. It still installs and verifies the
requested target. Failed metadata queries and target checks remain errors.

The managed fragment pins the successfully transferred Node version.
The adjacent `dev-machine-setup.node.json` retains the requested selector
(such as `lts`) and the original source while a transfer is pending.
Rerun the failed command to resume from that source. If the recorded source
was removed, restore it before retrying; setup preserves the pending state
and working pin. Do not delete the pending state to bypass a migration
failure. A committed transfer does not replay legacy globals, even if
clearing its pending state was interrupted.
Conflicting user mise configuration is reported before the old provider is
retired; setup does not rewrite that configuration.

With the default component choices, `mise run update` maintains all
installed Homebrew packages, not just the selected profile, plus managed
mise runtimes, npm/pnpm globals, Mac App Store apps and Ollama models.
Exclusions filter categories, not just the current profile's inventory;
cleanup is scoped to included packages. Maintenance preserves Homebrew's
pinning and non-greedy defaults. Filtered cask maintenance selects eligible
outdated apps instead of naming every installed app. Homebrew can still
update a native dependency of an included package.
Independent components continue after a failure, then the command returns
failure with a summary. Missing tools are skipped, not reported as updated.
Non-Node mise upgrades use `--no-prune`; Node installs its requested target
without changing the working pin until transfer succeeds. This command does
not run Ubuntu system upgrades.

## Remote access from an iPhone

`./remote-login.sh` configures SSH access to this Mac from your Tailscale
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

Use your normal macOS account, not root. Complete bootstrap to install mise
and the locked Python. Enablement and its read-only preflight also require
connected Tailscale and phone public keys. Revocation requires neither.
Remote Login uses the configured Homebrew prefix in SSH's command path but
does not require the Homebrew executable.

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
  The read-only `mise run remote-login-check` does not require a local console.
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
support; in Secure ShellFish you start herdr yourself. Run
`mise run cli --profile personal` to install mosh from the personal Mac
inventory. Install herdr from [herdr.dev](https://herdr.dev); SSH commands
search `~/.local/bin`, mise's shims, Homebrew's `bin` directory and
`/usr/local/bin`.

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

5. List only those key files in `defaults.toml`:

   ```toml
   remote_login_public_keys = ["iphone-shellfish.pub", "iphone-moshi.pub"]
   ```

   By default, `remote_login_sources` accepts SSH logins from all tailnet
   addresses. Narrow it to the iPhone's Tailscale IPv4 and IPv6 addresses
   if only that device should log in. If its addresses change, update the
   list at the Mac. This authentication limit does not replace the policy
   or firewall checks.
6. Before enabling, review the key list: each run backs up and **replaces
   all of `~/.ssh/authorized_keys`** with these keys. Hand-added keys and
   Moshi Easy Pair keys not in the list will be removed. Setup also limits
   Remote Login to your account. Existing SSH or mosh sessions may be
   interrupted, but are not reliably terminated.
   At the Mac's local console, run:

   ```bash
   ./remote-login.sh
   ```

   This command checks phone keys, Tailscale and the SSH command path before
   requesting sudo or changing services, configuration or keys. It then
   deploys and validates the effective SSH settings before enabling access.
   A prerequisite pass alone is not proof of network isolation.
   Enter your sudo password if asked. Keep the connection details and
   host key fingerprints. If the run fails, do not enable Remote Login
   manually; fix the reported cause and rerun locally.
7. Only after enablement succeeds and the full policy and firewall checks pass,
   explicitly allow inbound tailnet traffic:

   ```bash
   tailscale set --shields-up=false
   ```

8. Set up the iPhone as described below. Then verify an actual iPhone
   connection and denied connections from other devices, including LAN sources.
   Check that unrelated Mac services are still unreachable.
   If any result differs from the intended rules,
   restore Shields Up and use `mise run remote-login-revoke` locally while you
   fix the policy or firewall. Shields Up alone does not block LAN access.

For an optional read-only readiness check, run `mise run remote-login-check`.
This does not deploy configuration, run the effective SSH settings gate or
activate SSH. It is not a full configuration preview or proof that
enablement will succeed.

### Set up the iPhone

1. In the Tailscale app, open Settings > VPN On Demand. Set Wi-Fi and
   Cellular to **Always**.
2. In each app, add a server. Use the host name that `./remote-login.sh`
   showed, your Mac account name, and port 22.
3. In Moshi, keep the connection type at **Auto**.
4. Connect. Compare the host key fingerprint with the fingerprints that
   `./remote-login.sh` showed. If they are different, do not continue.
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
2. Run `./remote-login.sh` from the local console. It checks the revised
   inputs before changing access. Enablement interrupts the listener while
   it rechecks the effective SSH configuration.

Each enable run replaces `~/.ssh/authorized_keys` with the listed keys. Keys added
by hand or by Moshi's Easy Pair are removed. Before each change to a nonempty
file, it is backed up under
`~/.dev-setup-backups/<timestamp>/remote-login-<previous-content-hash>/authorized_keys`.
Backups are not active key files; do not restore a revoked phone key.

To remove the final key, use `mise run remote-login-revoke` instead. Then remove
its filename from `remote_login_public_keys` so a later setup cannot
reinstall it. An empty list deliberately fails the enable command; it is
not a revocation request. Removing a key prevents new authentication, not
access through an already authenticated SSH or mosh session.

### Turn off remote access

Setting `steps.remote-login` to false does not undo an earlier run. At the
local console, run:

```bash
mise run remote-login-revoke
```

This Mac-only command opts in with `revoke_remote_login=true`. It disables
SSH startup, unloads the listener if present, and backs up then clears the
invoking user's `~/.ssh/authorized_keys`. It retains the managed SSH
configuration. It needs sudo and the bootstrapped mise/Python command
interface, but not Homebrew, phone keys or a working Tailscale connection.
Neither a normal full setup nor a false revoke flag revokes access.

If Tailscale is available, also run `tailscale set --shields-up=true`.
Revocation itself does not change Shields Up or the control-server policy.
**Listener shutdown and key removal do not end all existing SSH or mosh
sessions.** Use the incident steps below if an active session is untrusted.

### If the iPhone is lost or compromised

1. Revoke or remove the iPhone device in the tailnet control server. Ask its
   administrator if you cannot do this yourself. Do not rely on this alone
   to terminate existing Mac sessions.
2. At the Mac's local console, run `mise run remote-login-revoke`. If available,
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
   rules, and a successful `./remote-login.sh` run; then release Shields Up
   manually as in setup.

### Remote Login troubleshooting

- **Wrong platform, root, or missing mise/Python:** use a normal ARM64 macOS
  account and complete bootstrap. Do not run the mise commands with `sudo`;
  enablement and revocation request it when needed.
- **Local-console refusal:** move to a local terminal on the Mac. Do not
  bypass the SSH environment check. Read-only preflight can run remotely.
- **Preflight fails:** correct the reported phone-key or Tailscale
  prerequisite, then rerun `mise run remote-login-check`. Each key file must
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
  login. `mise run remote-login` stops when it finds them.
- The key-only promise applies to normal post-unlock SSH. Review the
  FileVault, wildcard-listener, Bonjour, and firewall warnings
  [before setup](#before-you-start).
- If `~/.ssh/config` sends SSH to the 1Password agent, outgoing SSH from an
  iPhone session, for example `git push`, waits for approval on the Mac
  screen.

### What setup changes

`mise run remote-login` performs these steps and stops on failure:

1. Checks that the phone key list is nonempty, that each file holds one public
   key line without options, and that Tailscale is connected. Reports the SSH
   command path.
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

`install.sh` validates the OS, architecture and profile before bootstrap.
The bootstrap scripts install prerequisites; `scripts/setup.py` dispatches
configuration and maintenance. `mise.toml` exposes that same dispatcher.
The `devsetup` modules separate configuration, host settings, software and
SSH security. Package selection reads the four additive TOML layers.

Checks require [Bats (Bash Automated Testing System)](https://github.com/bats-core/bats-core)
and Python 3.11 or newer. `bats-core` is included in both Mac profiles'
required CLI inventory. On Ubuntu, or before Mac CLI installation, install
the test dependency explicitly:

```bash
brew install bats-core
```

Run all checks, or just the shell suite:

```bash
mise run check
mise run check-shell
```

Without mise, use `python3 -B scripts/check.py` for all checks or
`bats tests/shell` for the shell suite. The full check command fails with
an installation hint if Bats is missing; it never silently skips that suite.

The Bats tests in `tests/shell/` exercise public script behaviour:
input and platform refusals before bootstrap, bootstrap-only isolation,
Remote Login launcher failures and configuration selection, sudo-free
previews, headless authorisation, command exit status, and private
credential-file cleanup. They use isolated homes and substituted privileged
commands, not real package installation or service changes. Host-dependent
integration cases skip unsupported hosts; the pure shell cases remain
portable. Python tests retain configuration, domain and service-state coverage.

`mise run check` does not install packages or change machine settings.
It checks shell/Python syntax, TOML, all four OS/profile combinations,
prompt and flag behaviour, read-only previews, headless sudo, package failure
policies, npm migration, safe dotfiles updates and SSH safeguards. Temporary
directories and substituted executables isolate changes. On macOS it also
runs the real `/usr/sbin/sshd -T` gate against temporary configurations.

Validation for the component-selection and Node-recovery changes:

- `python3 -B scripts/check.py` passed on macOS, including failed-transfer
  retries, failed source inspection, interrupted journal cleanup, symlink
  guards, component exclusions and revocation precedence.
- An isolated smoke run exercised the actual Bash installer, Python
  dispatcher and Git with temporary configuration and substituted package,
  bootstrap and sudo commands. It verified layered paths containing spaces,
  App Store exclusions during setup and maintenance, explicit component
  overrides, saved dotfiles exclusions and a file-selected work profile.
- Read-only package selection succeeded for both Mac profiles.
- An isolated run used the checksummed, pinned mise executable with temporary
  fake Node executables. It confirmed actual `PATH` fallback, rejection of
  unregistered sources and targets, concrete pin selection with a newer
  version present, and preservation of the pin when a pending source vanished.
- Actual update CLI runs with stateful package substitutes verified CLI-only
  and GUI-only maintenance. Excluded packages, pinned versions, unavailable
  packages and self-updating casks remained unchanged.

These checks did not install real runtimes or packages, change host services,
or rerun fresh-machine provisioning. They do not establish a complete
runtime installation, package migration and recovery cycle on a disposable machine.

Earlier validation on 2026-10-06, before these changes:

- `python3 -B scripts/check.py` passed on macOS. `mise run check` passed in
  Ubuntu 24.04 ARM64. Checks cover stop-before-write, configuration rollback,
  partial activation failure and offline final-key revocation without changing
  real SSH services.
- A fresh Ubuntu 24.04 ARM64 container completed
  `./install.sh work --keep-ssh --skip-dotfiles`, then a personal full rerun.
  Actual Homebrew packages, mise runtimes, Git settings and shell setup ran.
  The pinned dotfiles installation and `mise run update` also completed.
- An isolated macOS 26.6.2 ARM64 VM completed bootstrap, both CLI profiles,
  Zsh, Node and pinned dotfiles installation. Native formulae and CLI casks
  installed through Homebrew. The optional xcodes release installed through
  Aqua; its CLI ran successfully without trusting an entire Homebrew tap.
- Real Zsh sessions on both platforms selected Node 24 outside a project,
  installed/selected Node 22 from `.nvmrc`, and restored Node 24 on leaving.
  Dotfiles and machine configuration fragments coexisted. The independent
  dotfiles installer tests passed.
- Real Ubuntu npm migration preserved `semver@7.7.2` and `cowsay@1.6.0`
  from earlier runtimes, retained their old installations and respected a
  custom npm prefix. A repeat run did not restore a package deliberately
  uninstalled after migration.

These results do not prove the entire GUI catalogue, App Store sign-in,
interactive 1Password authentication, Xcode installation, macOS preference
effects or Dock appearance. Non-terminal Zsh smoke commands emitted fzf
line-editor warnings; they are not visual terminal tests. Linux's vfox
1Password provider downloads over HTTPS without an upstream checksum.
Only isolated checks exercised privileged SSH state transitions. Real phone
connections, denied network paths, firewall rules, FileVault boot and actual
Remote Login activation/revocation remain manual validation steps.

The host's provisioning and live dotfiles checkout were not changed.
Repeat disposable-machine checks after changing inventories or platform
support. Other Ubuntu releases are not runtime-tested; Intel is unsupported.
The [pre-cutover validation history](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/README.md#implementation-and-validation)
records the earlier Ansible implementation, not evidence for this release.

Repository maintenance instructions live in [AGENTS.md](AGENTS.md).

[Dotfiles](https://github.com/mintuz/.dotfiles) ·
[Homebrew on Linux](https://docs.brew.sh/Homebrew-on-Linux) ·
[1Password SSH agent](https://developer.1password.com/docs/ssh)

