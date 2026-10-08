# Fable findings: inside-out audit and replacement research

Scope: every file under `scripts/`, `install.sh`, `new-mac.sh`, `remote-login.sh`, `mise.toml`, `defaults.toml`, `templates/`, `packages/` and `tests/shell/`, read in full. External claims cite live documentation fetched on 2026-10-08. Unverified statements are marked `[INFERENCE]`.

## 1. Short answer to "why not just mise?"

mise can own most of this repository today. Its `mise bootstrap` command applies packages, files, repositories, dotfile edits, shell activation, macOS defaults, Dock layout, login shell and a final task, with `--dry-run`, `status` and `plan` previews ([bootstrap](https://mise.jdx.dev/bootstrap.html)). When this repository was designed, the owner chose mise for runtimes and tasks only, and kept custom Python for everything else (`AGENTS.md:3-7`). The custom code exists because the owner needed guarantees that mise did not give at the time, or that the owner did not trust after one failed test on Ubuntu (`ARCHITECTURE-REPORT.md:9-12`).

What mise bootstrap covers today, mapped to this repository:

| Repository responsibility | mise section that covers it | Loss |
| --- | --- | --- |
| Brewfile install (`software.py:_bundle`) | `[bootstrap.packages]` `brew:`/`brew-cask:`/`mas:` via mise's own bottle installer, **or** `brew bundle` from a `[bootstrap.hooks]` entry ([packages](https://mise.jdx.dev/bootstrap/packages/), [brew](https://mise.jdx.dev/bootstrap/packages/brew.html), [mas](https://mise.jdx.dev/bootstrap/packages/mas.html)) | Hook path: none. Bottle-installer path: Homebrew's `post_install` steps are not documented as supported (section 5b) |
| Layer merge of `tools.*.toml` and the `conf.d` fragment (`software.py:tools`, `record_tools`) | `[tools]` with `os = [...]` selectors ([dev-tools](https://mise.jdx.dev/dev-tools/)), profile files `config.work.toml` selected with `-E work` ([environments](https://mise.jdx.dev/configuration/environments.html)) | None |
| Shell activation blocks (`host.py:bootstrap`) | `[bootstrap.mise_shell_activate]` ([shell](https://mise.jdx.dev/bootstrap/shell.html)); `brew shellenv` line via `[dotfiles]` block edit ([dotfiles edit entries](https://mise.jdx.dev/dotfiles.html#edit-entries)) | None |
| macOS preferences (`host.py:osx`) | `[bootstrap.macos.defaults]` typed raw defaults ([macos-defaults](https://mise.jdx.dev/bootstrap/macos-defaults.html)) | `sudo defaults` system domains unsupported; `chflags nohidden` and `killall Finder` need a hook |
| Dock (`host.py:dock`) | `[bootstrap.macos.dock] apps = [...]` | Spacer tiles are not in the `apps` list; keep `dockutil` in a hook if spacers matter |
| Login shell (`host.py:zsh`) | `[bootstrap.user] login_shell` ([user](https://mise.jdx.dev/bootstrap/user.html)) | None |
| Git checkouts (`host.py:_checkout`) | `[bootstrap.repos]` with `ref`, clean-worktree and origin checks ([repos](https://mise.jdx.dev/bootstrap/repos.html)) | Conflict-path backup to `~/.dev-setup-backups` and the detached-commit guard |
| Privileged files (`security.py:_System.deploy_config`) | `[bootstrap.files]` with `owner`/`group`/`mode`, atomic rename, privileged batch ([files](https://mise.jdx.dev/bootstrap/files.html)) | No validation gate before write, no rollback: "Bootstrap is a sequence, not a transaction" |
| Sudo per operation (`with-sudo-askpass.sh`) | `system_packages.sudo` setting: prompt in a terminal, passwordless when headless, each elevated command logged ([settings](https://mise.jdx.dev/configuration/settings.html#system_packages.sudo)) | No keep-alive, no askpass file, no single-prompt guarantee |
| Remote Login enable/gate/rollback/revoke (`security.py` 500+ lines) | Nothing. `[bootstrap.services]` manages user services on macOS, not system daemons ([bootstrap step 5](https://mise.jdx.dev/bootstrap.html)) | Whole contract |

Direct answers to the parent's three questions:

- `host.py` (395 lines): **yes, mise can replace it**, with about 40 lines of TOML and three short hooks. Loss: dotfiles conflict-path backups, Dock spacers unless `dockutil` stays in a hook, the 90% disk-usage preflight.
- `software.py` (341 lines): **yes, mise can replace it completely.** The layer merge and `conf.d` fragment are redundant with mise's own config layering. Package installation can keep Homebrew as the executor through a hook (no loss), or move to mise's bottle installer (risk: see 5b).
- `with-sudo-askpass.sh` (65 lines): **mise replaces it for bootstrap's own operations** but not for the Remote Login Python, which keeps its own `sudo -A` path. The wrapper stays for the security commands only.

The Remote Login flow is the one genuinely custom component. Tailscale SSH cannot replace it on this Mac because the server component requires the open-source `tailscaled` variant, which has no GUI and which Tailscale "only recommend[s] for unattended installs managed by experienced macOS system administrators" ([macOS variants](https://tailscale.com/kb/1065/macos-variants), [Tailscale SSH prerequisites](https://tailscale.com/kb/1193/tailscale-ssh)). The repository installs the GUI `tailscale-app` cask (`packages/mac/Brewfile.gui:21`).

One caution on maturity: the bootstrap documentation describes the current release. `mise.toml:1` pins `min_version = "2026.10.3"`; I could not verify which sections shipped in exactly that version `[INFERENCE: all cited sections exist in 2026.10.3]`. Two relevant mise features are mid-migration: environment-suffixed `conf.d` names are opt-in until 2027.8.10, and `auto_env` platform environments default to off until 2027.6.0 ([environments](https://mise.jdx.dev/configuration/environments.html)). Any migration should set `env_conf_d = true` and `auto_env = true` explicitly in `.miserc.toml`.

## 2. Responsibility inventory

Classification: **A** replaceable with no loss; **B** replaceable with a named loss; **C** genuinely custom, keep; **D** dead weight, delete.

| # | Responsibility | File (approx. lines) | Why it exists (contract) | Class |
| --- | --- | --- | --- | --- |
| 1 | Profile, OS, architecture and root validation | `install.sh:73-110` (38), `config.py:detect_platform`, `_select_profile` (45) | "Reject Intel, Rosetta, non-Ubuntu Linux and root" (`AGENTS.md:40`); profile only from CLI or `DEVSETUP_PROFILE` (`AGENTS.md:61`) | B: mise `os`/`arch` selectors and `-E` cover selection; the explicit refusal of Intel/Rosetta/root needs ~15 lines of shell |
| 2 | Consent prompts (1Password SSH, dotfiles) | `install.sh:112-146` (35) | "The SSH prompt defaults to No" (`AGENTS.md:101`); Ubuntu asks about dotfiles (`AGENTS.md:114-119`) | C: mise has only a yes/no confirmation for the whole apply (`--yes`); per-feature consent is a product decision |
| 3 | Xcode CLT / apt prerequisites | `bootstrap-macos.sh` (11), `bootstrap-ubuntu.sh` (5) | "Keep OS prerequisites, Homebrew installation and the checksummed mise ... in that order" (`AGENTS.md:41-43`) | B: apt list moves to `[bootstrap.packages] "apt:..."` once mise is installed first; the CLT wait loop stays (mise source builds need it: [brew source formulae](https://mise.jdx.dev/bootstrap/packages/brew.html#source-formulae)) |
| 4 | Homebrew bootstrap | `bootstrap-homebrew.sh` (25) | "Homebrew owns native formulae and casks" (`AGENTS.md:5`) | C while Homebrew stays the executor; D if the bottle installer passes validation |
| 5 | mise bootstrap with SHA-256 pin and `~/.local/bin/mise` link | `bootstrap-mise.sh:1-57` (57) | "checksummed mise/locked Python installation" (`AGENTS.md:42`); link for dotfiles (`AGENTS.md:241`) | B: `curl https://mise.run \| MISE_VERSION=... sh` or packslip with a signer pin ([installing](https://mise.jdx.dev/installing-mise.html#packslip)). Loss: the exact SHA-256 you reviewed; gain: Sigstore signature and transparency log |
| 6 | Locked Python | `bootstrap-mise.sh:58-59`, `mise.lock` (18), `mise.toml:12-14` | "locked helper Python" (`AGENTS.md:21`) | D once the Python is gone; A until then (`mise install --locked` is native: [mise.lock](https://mise.jdx.dev/dev-tools/mise-lock.html)) |
| 7 | TOML config layering (`defaults.toml` + `--config`, `[mac]`/`[linux]`, `[steps]` by key, forbidden keys) | `config.py` (252), `defaults.toml` (132) | `AGENTS.md:53-70` | A: mise config hierarchy, `mise.macos.toml`/`mise.linux.toml` with `auto_env`, `mise.local.toml` for the override file, `[vars]` for scalars ([environments](https://mise.jdx.dev/configuration/environments.html)) |
| 8 | Step policy, `--skip`, explicit-command override, fixed order, issue summary | `cli.py` (207), `install.sh:21-72` | `AGENTS.md:62-70, 84-86, 195-205` | B: `mise bootstrap --skip <part>` and `--only` exist, but parts are mise's (packages, dotfiles, tools...), not this repository's steps (gui, app-store, node...). Loss: per-step named skips and the "non-fatal GUI issue list". Hooks stop bootstrap on failure |
| 9 | Brewfile concatenation per layer, `brew bundle --file=-` | `software.py:layer_files`, `brewfile`, `_bundle` (40) | `AGENTS.md:166-172` | A: `brew bundle` takes one `--file` ([manpage](https://docs.brew.sh/Manpage)); call it once per layer file from a hook. Concatenation is only an optimisation |
| 10 | Replaced-package removal (`tldr`, `claude-code@latest`) | `software.py:_remove_replaced_packages` (15) | `AGENTS.md:202-205` | D: one-off migration logic for packages renamed months ago; put two `brew uninstall` lines in a hook or drop |
| 11 | mise tools merge and `conf.d` fragment writer with symlink guard | `software.py:tools`, `_specs`, `fragment_path`, `_guard_fragment_path`, `_fragment_tools`, `_toml_value`, `record_tools`, `_install_tools` (120) | `AGENTS.md:172-176, 134-139` | A: see section 5a. mise merges `[tools]` across files and selects by `os` and `-E`; no generated file is needed |
| 12 | GUI and App Store bundles, `mdimport` | `software.py:_gui`, `_app_store` (30) | `AGENTS.md:196-201` | A: two hook lines on macOS, or `mas:` packages. `mdimport` stays as a hook line |
| 13 | Node, pnpm, `PNPM_HOME` block, `pnpm_global_packages` | `software.py:_node` (25) | `AGENTS.md:207-216` | A for tools; D for `pnpm_global_packages`: the list is empty (`defaults.toml:20`) and `npm:` tools already give global CLIs. `PNPM_HOME` via `[env]` with `_.path` |
| 14 | fzf shell integration | `host.py:fzf` (10) | `AGENTS.md:141-142` | A: hook running `$(brew --prefix)/opt/fzf/install --key-bindings --completion --no-update-rc`, plus a `[dotfiles]` block that sources `~/.fzf.zsh` |
| 15 | Login shell, Oh My Zsh installer, zsh-autosuggestions, Linux `.zshrc` block | `host.py:zsh` (30) | `AGENTS.md:142-143` | A: `[bootstrap.user] login_shell`, `[bootstrap.repos]` for autosuggestions, hook for the Oh My Zsh installer, `[dotfiles]` block |
| 16 | Shell activation blocks (`brew shellenv`, `mise activate`), `.ssh`/`.gnupg` dirs, early 1Password | `host.py:bootstrap`, `ensure_block`, `_write_if_changed` (70) | `AGENTS.md:140-144` | A: `[bootstrap.mise_shell_activate]`, `[dotfiles]` block for `brew shellenv`, `[bootstrap.directories]` for the dirs |
| 17 | Git formula, identity, global gitignore, defaults | `host.py:git`, `global_gitignore` (40 + 207 data) | `AGENTS.md:146-147` | A: `[dotfiles]` copy entry for `~/.global_gitignore`; `git config --global` lines in a hook (a `[dotfiles]` `merge` entry does not support INI, and a block edit fails on a symlinked `~/.gitconfig`: [conflicts](https://mise.jdx.dev/dotfiles.html#conflicts)) |
| 18 | External dotfiles clone, origin check, fast-forward, dirty-check, detached-commit guard, conflict-path backup, `install.sh` run | `host.py:_local_origin`, `_checkout`, `dotfiles` (110) | `AGENTS.md:121-132` | B: `[bootstrap.repos]` enforces clean worktree, origin match (three URL forms compared transport-agnostically), fast-forward only, `ref`. Loss: `file://` origin comparison with Git path semantics, the "unreferenced detached commits" refusal, the `dotfiles_conflict_paths` backup. Hook runs `~/.dotfiles/install.sh` |
| 19 | macOS defaults, Library visibility, automatic-update check, Finder restart | `host.py:osx` (15), `defaults.toml:49-88` (40) | `AGENTS.md:152-157` | B: `[bootstrap.macos.defaults]` for all 38 user-domain entries, typed. Loss: `sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate` and `chflags nohidden` are unsupported and move to a hook (two lines) |
| 20 | Dock layout with spacers | `host.py:dock` (20), `defaults.toml:91-124` (34) | `AGENTS.md:152-154` | B: `[bootstrap.macos.dock] apps` manages order and preserves unrecognised tiles. Loss: spacers are not declared. Keep `dockutil` in a hook for no loss |
| 21 | Preflight (git, curl, brew, disk usage) and `brew update` | `host.py:preflight` (15) | `AGENTS.md:84-90` | D: `mise bootstrap --update` refreshes package metadata; disk-usage warning has no documented contract beyond the old playbook comment (`cli.py:22`) |
| 22 | Managed SSH client config with 1Password agent, `~/.ssh` backup | `security.py:_identity_agent`, `_manage_ssh`, `_skip_agent_and_special_files` (90), `templates/ssh_config` | `AGENTS.md:101-112, 148-150` | B: `[dotfiles]` `template` entry with `{{ mise_env }}`-selected key, `permissions = "0600"`. Loss: full `~/.ssh` copy to `~/.dev-setup-backups`; mise refuses conflicts without `--force` and records history checkpoints for tracked files ([history](https://mise.jdx.dev/history.html)) |
| 23 | Remote Login: preflight (phone keys, Tailscale status, PATH), stop-before-write, `sshd -t`/`-T` gate against two addresses, deploy with metadata restore, access list via `dscl`/`dseditgroup`, activation with port wait and fail-closed, revoke | `security.py:_preflight` ... `_System` (520), `templates/sshd_remote_login.conf` (19) | `AGENTS.md:229-314` | C: no tool implements a validate-then-enable gate with rollback for a macOS system daemon |
| 24 | Sudo askpass keep-alive wrapper | `with-sudo-askpass.sh` (65) | `AGENTS.md:159-162` | B for setup (mise elevates per operation, no keep-alive); C for the security commands |
| 25 | Update all installed software with per-component summary | `update.sh` (74) | `AGENTS.md:218-227` | C: 74 lines, Bash only, tested; `mise bootstrap packages upgrade` covers only declared packages, not "all installed software regardless of profile" |
| 26 | Thin launchers | `new-mac.sh` (7), `remote-login.sh` (13), `setup.py` (14) | `AGENTS.md:44, 237-242` | D for `new-mac.sh` and `setup.py` after migration; C for `remote-login.sh` |
| 27 | Check harness: config/platform/host | `check-platforms.py` (560) | `AGENTS.md:325-341` | D after migration: it tests the TOML merge, `--skip` parsing, prompts and host writes that mise would own |
| 28 | Check harness: software | `check-software.py` (319) | same | D after migration |
| 29 | Check harness: security with fake `launchctl`/`sshd`/`dscl` and real `sshd -T` gate | `check-security.py` (744) | `AGENTS.md:338-343` | C: this is the regression suite for the only custom component |
| 30 | Bats: installer, sudo, remote-login, update | `tests/shell/*.bats` (496), `helpers.bash` (40) | `AGENTS.md:330-336` | C for `sudo.bats`, `remote-login.bats`, `update.bats`; B for `installer.bats` (shrinks with `install.sh`) |
| 31 | Check runner | `check.py` (55) | `AGENTS.md:325-329` | B: a `[tasks.check]` with `depends` replaces it; loss: the "missing Bats must fail" guard becomes one `command -v bats` line |

Totals from `wc -l`: production custom code 2,353 lines (Python 1,925, shell 428); checks 2,214 lines (Python 1,678, Bats 536); configuration 249 lines. Rows classed A or D cover roughly 1,180 production lines and 879 check lines.

## 3. Replacement research for A and B rows

### 3.1 Configuration layering (rows 1, 7, 8)

Replacement: mise's configuration hierarchy. Shared settings go in the repository's `mise.toml`; profile-specific settings go in `mise.personal.toml` and `mise.work.toml`, selected with `mise -E work bootstrap` or a per-machine `~/.config/mise/miserc.local.toml` containing `env = ["work"]` ([environments](https://mise.jdx.dev/configuration/environments.html#personal-environment-selection)). Platform-specific settings go in `mise.macos.toml` and `mise.linux.toml`, loaded when `auto_env = true` is set in `.miserc.toml`. The user's one-off override file becomes `mise.local.toml`, which "take[s] priority" over `mise.toml` and is gitignored.

What this cannot do: refuse a conflicting `DEVSETUP_PROFILE` and `--profile` pair. mise picks the last environment listed. If the owner wants the conflict refused, that is a five-line shell check in the launcher. It also cannot enforce "profile never from a settings file" (`AGENTS.md:61`); `miserc.local.toml` is a settings file. I recommend changing that contract: a per-machine, gitignored `miserc.local.toml` is exactly the "which machine am I" record the repository currently refuses to keep, and it removes the need to pass the profile on every command.

### 3.2 Package inventories (rows 9, 10, 12)

Two options.

Option 1, no loss: keep Homebrew as the executor and the existing `Brewfile.*` files. Replace `software.py` with hooks:

```toml
[bootstrap.hooks.post-packages]
run = [
  "HOMEBREW_NO_AUTO_UPDATE=1 brew bundle install --file=packages/shared/Brewfile.cli",
  "HOMEBREW_NO_AUTO_UPDATE=1 brew bundle install --file=packages/mac/Brewfile.cli",
]
```

Hooks are rendered with Tera and run only during explicit `mise bootstrap`; they stop bootstrap if they fail and are printed instead of run during `--dry-run` ([hooks](https://mise.jdx.dev/bootstrap.html#hooks)). Profile-only files go in `mise.personal.toml` hooks; hooks "merge across the config hierarchy". `brew bundle` is idempotent per file, so running it four times is equivalent to the current concatenation (section 5b). The `trusted: true` and `greedy: true` item syntax keeps working because Homebrew still parses the files.

What this loses: the non-fatal issue list for GUI and App Store failures (`AGENTS.md:198-201`). A failing hook stops bootstrap. To keep "later steps continue", end the GUI and App Store hook commands with `|| true` and read Homebrew's output, or run them as separate `mise run gui` tasks after bootstrap.

Option 2, Homebrew removed: `[bootstrap.packages]` with `brew:`, `brew-cask:` and `mas:` entries. mise "never shells out to brew", pours bottles into `/opt/homebrew` with brew-compatible receipts, supports third-party taps by fetching the Ruby definition at a pinned commit, supports `adopt = true`, follows `auto_updates` semantics, and warns before replacing an app bundle ([brew](https://mise.jdx.dev/bootstrap/packages/brew.html)). `mise bootstrap packages import --manager brew` converts an existing installation; cask import is not implemented.

What this loses or changes: Homebrew's trust policy (`AGENTS.md:189-193`) is replaced by mise's own DSL shim with no per-item trust prompt; `brew services` is not implemented; "formulae without a bottle are built from source" through a DSL subset that "fail[s] with a clear error" for unsupported features. The Ubuntu certificate failure is the main risk (section 5b).

### 3.3 mise tools (rows 11, 13)

See section 5a. The replacement is to declare `[tools]` once in global configuration with `os` selectors, and let `mise install` or `mise bootstrap` step 15 install them.

### 3.4 Host configuration (rows 14-21)

- Shell activation: `[bootstrap.mise_shell_activate] zsh = true` writes marker blocks to `~/.zprofile` (shims) and `~/.zshrc` (activate); `bash = true` likewise. It skips the entry when `[dotfiles]` already manages the file whole ([shell](https://mise.jdx.dev/bootstrap/shell.html)). The `brew shellenv` line becomes `[dotfiles] "~/.zshrc/brew" = { block = 'eval "$(/opt/homebrew/bin/brew shellenv)"' }`. mise refuses block edits on symlinked targets and reports an error; the current `ensure_block` silently skips them (`host.py:ensure_block`). That is a behaviour change: when the external dotfiles repo symlinks `~/.zshrc`, bootstrap would fail instead of printing a notice. Declare those edits only in a profile or platform file where the dotfiles repo does not own the file, or point the edit at the real file.
- Login shell: `[bootstrap.user] login_shell = "/bin/zsh"` in `mise.macos.toml`, `/usr/bin/zsh` in `mise.linux.toml`. mise appends to `/etc/shells` and runs `chsh -s` with its sudo path ([user](https://mise.jdx.dev/bootstrap/user.html)).
- Oh My Zsh: a `post-repos` hook running the upstream installer with `RUNZSH=no CHSH=no KEEP_ZSHRC=yes`, guarded by `[ -d ~/.oh-my-zsh ] ||`. zsh-autosuggestions: `[bootstrap.repos] "~/.oh-my-zsh/custom/plugins/zsh-autosuggestions" = { url = "https://github.com/zsh-users/zsh-autosuggestions.git" }`.
- macOS defaults: every `defaults.toml:49-88` entry maps to `[bootstrap.macos.defaults."<domain>"] key = value` with typed values; `{home}` placeholders become literal paths or a `defaults_entries` template `[INFERENCE: defaults values are "used exactly as written", so no template; write the absolute path]`. `killall Finder` and `killall Dock` become `[bootstrap.hooks] post-defaults`. `chflags nohidden ~/Library` and the `sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled` line are not supported ("sudo defaults system domains are not supported") and go in the same hook.
- Dock: `[bootstrap.macos.dock] apps = [...]` manages the order and "Non-application and unrecognised tiles are preserved". Spacers (`defaults.toml:93,99,...`) are not declared. Either accept no spacers (B) or keep `dockutil` with the existing argument lists in a hook (`brew "dockutil"` stays in `Brewfile.cli`).
- Git: `[dotfiles] "~/.global_gitignore" = { source = "global_gitignore", mode = "copy" }` and a hook with the seven `git config --global` lines. `git` itself is already in `packages/shared/Brewfile.cli:11`; the separate `_formula(config, "git", latest=True)` upgrade is redundant with `brew bundle`'s upgrade of outdated items.
- External dotfiles: `[bootstrap.repos] "~/.dotfiles" = { url = "https://github.com/mintuz/.dotfiles.git", ref = "master" }` then a `post-repos` hook: `cd ~/.dotfiles && ./install.sh`. mise refuses dirty worktrees and mismatched origins and only fast-forwards. Loss: the `dotfiles_conflict_paths` backup (`defaults.toml:10`, `host.py:dotfiles`). The one listed path is `.agents/.skill-lock.json`; that belongs to the dotfiles repository's own installer, which already backs up managed conflicts per `AGENTS.md:128-129` `[INFERENCE: the external install.sh handles this path]`.

### 3.5 SSH client config (row 22)

`[dotfiles] "~/.ssh/config" = { source = "templates/ssh_config.tera", mode = "template", permissions = "0600" }` with the agent socket and primary key chosen from `{{ mise_env }}` and `{{ os() }}`. The Linux `SSH_AUTH_SOCK` rule becomes `{% if env.SSH_AUTH_SOCK %}`. Public keys: two `copy` entries. Consent: declare the entries in `mise.ssh.toml` and select `-E ssh` only when the user says yes, which mirrors `steps.ssh`. Loss: the timestamped `~/.ssh` backup. Mitigation: `mise dot track ~/.ssh/config` before applying gives a checkpoint and `mise dot rollback`.

### 3.6 Bootstrap pin and sudo (rows 5, 24)

mise's official installer accepts `MISE_VERSION` for reproducible installs; packslip verifies the Sigstore signature and transparency log against a pinned repository fingerprint ([installing](https://mise.jdx.dev/installing-mise.html#packslip)). The custom 57-line download with a hard-coded SHA-256 is defensible but duplicates what packslip does with stronger provenance. The sudo wrapper is needed for the Remote Login Python only; for bootstrap, mise prompts in an interactive terminal and requires passwordless sudo when headless, which matches `AGENTS.md:160-161` except for keep-alive.

## 4. Classification summary

| Class | Rows | Production lines | Check lines |
| --- | --- | --- | --- |
| A | 7, 9, 11, 12, 13 (tools), 14, 15, 16, 17 | ~730 | ~560 |
| B | 1, 3, 5, 8, 18, 19, 20, 22, 24, 30 (installer), 31 | ~640 | ~250 |
| C | 2, 4, 23, 25, 26 (remote-login.sh), 29, 30 (sudo, remote-login, update) | ~830 | ~1,110 |
| D | 6, 10, 13 (pnpm globals), 21, 26 (new-mac.sh, setup.py), 27, 28 | ~150 | ~880 |

Rows 27 and 28 are counted in both their current class (checks for A code) and D because they go when the code goes.

## 5. The five attention points

### 5a. Can mise's own layering replace the `conf.d` fragment?

Yes, completely. The fragment exists so tools declared in the checkout "work outside this checkout without replacing the user's own mise configuration" (`software.py:9-12`). mise offers three native ways to get the same result:

1. `mise bootstrap --adopt <repo-url>` clones the repository into `$MISE_CONFIG_DIR` and loads `config.toml`, `config.work.toml`, `conf.d/` and `tasks/` from it ([bootstrap --adopt](https://mise.jdx.dev/bootstrap.html#global-mise-configuration)). The repository becomes the global config. The dotfiles repo's `dotfiles.toml` fragment still coexists in `conf.d/` as an untracked file. This is the cleanest option and removes the "which directory am I in" problem for every `mise run` task.
2. A `[dotfiles]` symlink entry that links `~/.config/mise/conf.d/dev-machine-setup.toml` to a static file in the checkout. No generation, no merge code, no symlink-ancestor guard. The guard (`software.py:_guard_fragment_path`) exists to avoid writing through another repository's symlinked `.config`; a symlink entry that mise creates has no such write.
3. `mise use -g` writes to `~/.config/mise/config.toml` ([use](https://mise.jdx.dev/cli/use.html)). Not recommended: it mutates a file the user owns, which `AGENTS.md:138` forbids.

Layer selection: `[tools]` entries accept `os = ["macos"]` or `os = ["linux"]` ([dev-tools os field](https://mise.jdx.dev/dev-tools/)). Profile layers become `config.work.toml` / `config.personal.toml`. The four-directory layout in `packages/` collapses to one `tools.toml` fragment with `os` selectors plus two profile files. The `aqua:` Linux providers (`packages/linux/tools.cli.toml`) become `"aqua:openai/codex" = { version = "latest", os = ["linux"] }`.

Caveat: environment-suffixed `conf.d` names need `env_conf_d = true` in `miserc.toml` until 2027.8.10, and dots in unconditional fragment names are deprecated ("Rename them to use hyphens"). The current fragment name `dev-machine-setup.toml` has no dot, so it is unaffected; the inventory names `tools.cli.toml` would need renaming if moved into `conf.d`.

### 5b. Does `brew bundle` take multiple Brewfiles?

No. The manpage documents one `--file` (or `-` for stdin) and `HOMEBREW_BUNDLE_FILE`; there is no multi-file option ([brew(1) bundle](https://docs.brew.sh/Manpage)). Two correct replacements for concatenation:

- Run `brew bundle install --file=<layer file>` once per selected layer. Each run installs missing items and upgrades outdated ones; the result after four runs equals one concatenated run. Cost: Homebrew's start-up time four times (a few seconds each `[INFERENCE]`), and `tap` lines must appear in the file that first uses them, which they already do.
- Declare `[bootstrap.packages]` and let mise install. This removes Homebrew entirely.

On the Ubuntu certificate failure that stopped the earlier cutover (`ARCHITECTURE-REPORT.md:9-12`): the Homebrew `ca-certificates` formula builds `etc/ca-certificates/cert.pem` in a `post_install_steps` block that merges the system bundle and the Mozilla bundle ([ca-certificates.rb](https://raw.githubusercontent.com/Homebrew/homebrew-core/HEAD/Formula/c/ca-certificates.rb)). The mise brew page describes fetch, extract, relocate, re-sign, receipt and link steps, and does not mention `post_install` or `post_install_steps` anywhere ([brew: how pouring works](https://mise.jdx.dev/bootstrap/packages/brew.html#how-pouring-works)). `[INFERENCE]` The failure the owner saw is this gap: without `cert.pem`, Homebrew's `openssl@3` and everything linked to it (`git`, `curl`, `gh`, `wget`, `httpie`) has no CA store. The same gap would exist on macOS for brew-installed TLS clients, where the formula merges the keychain. That makes the bottle installer unsuitable for this inventory until mise documents `post_install_steps` support. Keep Homebrew as the executor; re-test when the docs change.

### 5c. Could Tailscale SSH replace the Remote Login flow?

No, not on this Mac, and not without dropping the repository's own guarantees.

- Platform: the Tailscale SSH server runs on "Linux" and "macOS open source `tailscale` + `tailscaled` CLI devices" only ([prerequisites](https://tailscale.com/kb/1193/tailscale-ssh)). The App Store and Standalone variants, which the `tailscale-app` cask installs, show "Can be a Tailscale SSH server: no" ([comparison table](https://tailscale.com/kb/1065/macos-variants)). The open-source variant has no GUI, no auto-updates and no MDM support, and Tailscale recommends it "only ... for unattended installs managed by experienced macOS system administrators".
- Semantics: Tailscale SSH replaces key authentication with tailnet identity ("the SSH client and server will still create an encrypted SSH connection, but it will not be further authenticated"). The repository's contract is "key-only and limited to tailnet source addresses" with phone public keys checked by `ssh-keygen` (`AGENTS.md:265-266`, `security.py:_preflight`). Those are different threat models, not one being a superset.
- It also does not solve the parts of `security.py` that are about macOS: stopping `system/com.openssh.sshd` before writes, `dseditgroup` for `com.apple.access_ssh`, `sshd -T` gating, metadata rollback and offline revocation.

Verdict: `security.py` rows 23 and 29 stay. They are 715 + 744 lines because the contract in `AGENTS.md:229-314` is long, and every clause maps to code I read. Two small trims are possible without touching the contract: `_remote_login_path` and `TOOL_HINTS` (herdr/mosh hints, ~30 lines) are convenience, and `_CommandError` output trimming is cosmetic.

### 5d. Are 2,100 lines of checks proportionate?

Today the ratio is 2,214 check lines to 2,353 production lines. Split by subject:

| Subject | Production | Checks | Ratio |
| --- | --- | --- | --- |
| Security (Remote Login, SSH client) | 715 | 744 + 105 (remote-login.bats) | 1.2 |
| Config, CLI, installer prompts, host | 170 + 207 + 252 + 395 = 1,024 | 560 + 132 (installer.bats) | 0.7 |
| Software | 341 | 319 | 0.9 |
| Sudo wrapper | 65 | 157 | 2.4 |
| Update | 74 | 102 | 1.4 |

The security ratio is proportionate: the checks model `launchctl` state, run a real unprivileged `sshd -T` gate on macOS, and cover rollback, partial activation and offline revocation (`AGENTS.md:338-343`). The config/host/software checks (879 lines) test behaviour that mise owns after migration: TOML merging, layer order, fragment safety, block editing, `brew bundle` argument forwarding. Those are "copies and forwarding" tests of the kind the repository's own guidance warns against (`AGENTS.md:332-336`).

Leaner strategy after the custom code shrinks:

1. Keep `check-security.py`, `sudo.bats`, `remote-login.bats`, `update.bats` unchanged (about 1,110 lines).
2. Delete `check-platforms.py` and `check-software.py`.
3. Replace them with three read-only commands in a `[tasks.check]`: `mise config` for each `-E` to prove file selection; `mise bootstrap plan --detailed-exitcode` and `mise bootstrap --dry-run` on the dev host to prove the declarations parse and the plan is sane (dry runs "record nothing" and do not execute hooks); `bash -n` on the remaining shell. These replace about 880 lines with about 15.
4. Keep `installer.bats` for the consent prompts and the Intel/root refusals, trimmed to the lines that survive.
5. Keep real provisioning validation in disposable VMs, as `AGENTS.md:347-351` already requires. No harness proves a fresh machine.

Expected check total: about 1,250 lines, almost all of it the security contract.

### 5e. Is dual Mac + Ubuntu support expensive, and is there a better tool for both?

The current cost is spread thinly: `[mac]`/`[linux]` tables (`defaults.toml:39-46,126-132`), `MAC_ONLY` lists in `cli.py:17` and `software.py:28`, platform branches in `host.py:_shell_files`, `zsh`, `software.py:_node`, two bootstrap shell files and the `install.sh` `uname` case. About 80 lines in total, plus the four-directory `packages/` layout. It is not the main source of size.

mise handles both platforms natively and more cheaply than the current code: `os` selectors on tools and packages; `mise.macos.toml`/`mise.linux.toml` through `auto_env`; `variants = [{ os = "macos", target = ... }]` on dotfiles; `[bootstrap.user]` on both; macOS sections "inert" on Linux and listed as skipped; `apt:` packages for the Ubuntu prerequisites. The one Ubuntu-specific prerequisite that must precede mise is `curl`, which Ubuntu ships.

Tools I would not pick for the dual target:

- nix-darwin + home-manager: covers `system.defaults` including `dock.persistent-apps` ([dock.nix](https://github.com/LnL7/nix-darwin/blob/master/modules/system/defaults/dock.nix)) and `programs.ssh`, but it makes Nix the owner of Homebrew (`nix-homebrew`), requires the Nix language, and still does nothing for the sshd gate. The owner has just removed Ansible for being a second engine; Nix is a heavier one.
- chezmoi: excellent for templated dotfiles and `run_onchange_` scripts with `.chezmoidata` ([scripts](https://www.chezmoi.io/user-guide/use-scripts-to-perform-actions/)), but packages, defaults and Dock would still be shell inside scripts, and it would compete with the external dotfiles repository that already owns `~/.*` through its own installer (`AGENTS.md:121-124`).
- Ansible: already removed; re-adding it contradicts `AGENTS.md:7, 43`.

## 6. Target architecture

### Primary: mise bootstrap as the engine, Homebrew as the package executor, Python only for Remote Login

```
repo/
  .miserc.toml            auto_env = true, env_conf_d = true
  mise.toml               [settings], [tools] (os selectors), [bootstrap.*] shared, [dotfiles], [bootstrap.hooks], [tasks]
  mise.macos.toml         [bootstrap.user], [bootstrap.macos.defaults], [bootstrap.macos.dock], mac hooks (brew bundle, mdimport, dockutil)
  mise.linux.toml         [bootstrap.packages] apt prerequisites, [bootstrap.user], linux hooks
  mise.personal.toml      personal-only Brewfile hooks and tools
  mise.work.toml          work-only hooks and tools
  mise.ssh.toml           [dotfiles] ~/.ssh/config template and public keys (selected with -E ssh after consent)
  mise.lock
  packages/               Brewfile.cli, Brewfile.gui, Brewfile.app-store per layer (unchanged files)
  templates/              ssh_config.tera, sshd_remote_login.conf
  install.sh              ~70 lines: root/Intel/Ubuntu refusal, two consent prompts, CLT wait, Homebrew installer, mise install, `mise bootstrap`
  remote-login.sh, scripts/with-sudo-askpass.sh, scripts/update.sh
  scripts/devsetup/security.py (+ ~100 lines of config/CLI it still needs)
  scripts/check-security.py, tests/shell/{sudo,remote-login,update,installer}.bats
```

Flow: `install.sh` validates and asks consent, installs CLT (mac) and Homebrew, installs mise pinned, then runs `mise -E <profile>[,ssh] bootstrap`. mise applies apt packages (Linux), runs the `brew bundle` hooks, clones repos, applies dotfile blocks and the SSH template, sets the login shell, writes macOS defaults, installs `[tools]`, and runs `[tasks.bootstrap]` for the dotfiles installer. `mise run remote-login` stays a task that invokes the Python.

Where the repository's config lives: either `mise bootstrap --adopt` (the checkout is `~/.config/mise`) or a `[dotfiles]` symlink for one `conf.d` fragment. I recommend `--adopt`: it removes the fragment concept, and `mise run <task>` works from any directory.

Contract changes this requires (list for the owner to approve): profile may be recorded per machine in `miserc.local.toml`; GUI/App Store failures stop bootstrap unless the hook tolerates them; dotfile block edits fail rather than skip on symlinked rc files; Dock spacers need `dockutil` in a hook; `--skip` names become mise part names; `--check` becomes `mise bootstrap --dry-run`, which prints hooks instead of running them (a better preview than today's "not previewed" messages, `host.py:51`).

### Alternative: keep the Python, cut the duplication

If the owner does not want to depend on a fast-moving bootstrap feature set (two migrations in progress until 2027), the conservative plan is:

1. Delete rows 6, 10, 13 (pnpm globals), 21 and the fragment writer; declare tools in a static `conf.d` fragment symlinked by `install.sh` (~150 lines removed).
2. Replace `config.py`'s TOML layering with mise `[vars]` read through `mise exec`? No; that is a half-measure. Instead keep `config.py` and delete only the forbidden-key machinery once `TEST_ONLY_KEYS` are moved to environment variables (~60 lines).
3. Delete `check-software.py` and the host half of `check-platforms.py` and replace them with a VM smoke run (~600 lines removed).

This lands at about 2,000 production lines and 1,500 check lines. It is safer this quarter and worse in two years, because every new tool or preference still needs Python.

## 7. Phased migration

Every phase leaves `./install.sh` able to provision a fresh machine. Line counts are production custom code (shell + Python), excluding TOML, Brewfiles, templates and checks; check lines in brackets.

| Phase | Change | Remaining custom lines (checks) |
| --- | --- | --- |
| 0 (today) | — | 2,353 (2,214) |
| 1. Tools and fragment | Add `[tools]` with `os` selectors to the repository config; `mise bootstrap --adopt` or a `[dotfiles]` symlink for the fragment. Delete `software.py:tools/_specs/fragment_path/_guard_fragment_path/_fragment_tools/_toml_value/record_tools/_install_tools` and the `node` step's tool half; delete `pnpm_global_packages`. Delete `packages/*/tools.*.toml`. Delete the fragment and node checks in `check-software.py`. Validate in an Ubuntu container and a Mac VM. | ~2,200 (~2,050) |
| 2. Packages | Add `brew bundle` hooks per layer file to `mise.toml`, `mise.macos.toml`, `mise.personal.toml`, `mise.work.toml`; `mdimport` and the two `brew uninstall` lines in the mac hook. Delete the rest of `software.py`, the `packages`/`cli`/`gui`/`app-store`/`node` actions in `cli.py`, and `check-software.py`. `mise run packages` becomes `mise bootstrap --dry-run`. | ~1,850 (~1,730) |
| 3. Host | Add `[bootstrap.mise_shell_activate]`, `[dotfiles]` blocks and copies, `[bootstrap.user]`, `[bootstrap.repos]`, `[bootstrap.macos.defaults]`, Dock (mise `apps` or `dockutil` hook), post-defaults hook, Oh My Zsh and fzf hooks, dotfiles `install.sh` in `[tasks.bootstrap]`. Delete `host.py`, the host actions in `cli.py`, the host section of `check-platforms.py`. | ~1,400 (~1,450) |
| 4. Config and entry points | Move `defaults.toml` scalars to `[vars]` and platform files; `--config` becomes `mise.local.toml`; `[steps]` becomes `-E` selection plus `--skip <part>`. Shrink `config.py` to the platform guard and the keys `security.py` reads (~80 lines) and `cli.py` to the four security actions (~60 lines). Shrink `install.sh` to validation, consent, CLT, Homebrew, mise install and `mise bootstrap`. Delete `new-mac.sh`, `setup.py` (fold into `cli.py` `__main__`), `check.py` (becomes `[tasks.check]`), the rest of `check-platforms.py`; trim `installer.bats`. | ~1,100 (~1,250) |
| 5. Optional: bootstrap pin | Replace the 57-line download with packslip or `mise.run` + `MISE_VERSION`. Decide after reviewing packslip's trust model. | ~1,050 (~1,250) |
| 6. Optional: bottle installer | Only after mise documents `post_install_steps` support and a clean Ubuntu run proves `git`, `curl` and `gh` can reach GitHub. Then `[bootstrap.packages]` replaces the hooks and `bootstrap-homebrew.sh` goes. | ~1,000 (~1,250) |

What remains at the end: `security.py` and its templates, `check-security.py`, the sudo wrapper, `update.sh`, three Bats files, and about 150 lines of shell and Python glue. Roughly 90% of what is left is the Remote Login contract the owner wrote on purpose.

Gates for each phase, taken from `ARCHITECTURE-REPORT.md:473-493` and still valid: all four OS/profile pairs select the intended inventory (`mise -E work config`, `mise bootstrap plan --json`); a second apply makes no changes (`mise bootstrap plan --detailed-exitcode` exits 0); a dirty `~/.dotfiles` is refused; SSH and Remote Login keep opt-in, ordering, gate, rollback and revocation. Never run any of this on the development host to validate an edit (`AGENTS.md:348`).

## 8. What I would not recommend

- Rewriting `security.py` into mise `[bootstrap.files]` plus `[bootstrap.services]`. Files has no pre-write validation and no rollback; services does not manage system daemons on macOS. The contract would be silently weakened.
- Moving to mise's bottle installer before the `post_install_steps` gap is closed. The owner already observed the failure; the documentation explains why.
- Adopting nix-darwin, chezmoi or Ansible as a second engine. Each solves part of the problem and adds a language or an installer the repository just removed.
- Keeping `check-platforms.py` and `check-software.py` after their subjects move to mise. They would test mise, which mise's own `--dry-run` and `plan` already do.
- Keeping the `conf.d` fragment generator in any form. mise's hierarchy, `os` selectors and `-E` make it unnecessary, and the symlink-ancestor guard exists only because the code writes a file it does not own.

## 9. Sources

Repository: `AGENTS.md`, `README.md:19-900` (headings), `ARCHITECTURE-REPORT.md:1-43,153-179,464-540`, `install.sh`, `new-mac.sh`, `remote-login.sh`, `mise.toml`, `mise.lock`, `defaults.toml`, `scripts/bootstrap-*.sh`, `scripts/update.sh`, `scripts/with-sudo-askpass.sh`, `scripts/setup.py`, `scripts/check.py`, `scripts/check-platforms.py`, `scripts/check-software.py`, `scripts/check-security.py`, `scripts/devsetup/{cli,config,software,host,security}.py`, `templates/*`, `packages/**`, `tests/shell/*`. Line counts from `wc -l`.

External:
- mise bootstrap: https://mise.jdx.dev/bootstrap.html
- mise packages, brew, mas: https://mise.jdx.dev/bootstrap/packages/ , https://mise.jdx.dev/bootstrap/packages/brew.html , https://mise.jdx.dev/bootstrap/packages/mas.html
- mise macOS defaults and Dock: https://mise.jdx.dev/bootstrap/macos-defaults.html
- mise login shell: https://mise.jdx.dev/bootstrap/user.html
- mise repos: https://mise.jdx.dev/bootstrap/repos.html
- mise files: https://mise.jdx.dev/bootstrap/files.html
- mise shell activation: https://mise.jdx.dev/bootstrap/shell.html
- mise dotfiles (edit entries, conflicts, root-owned files): https://mise.jdx.dev/dotfiles.html
- mise config environments, conf.d, auto_env: https://mise.jdx.dev/configuration/environments.html
- mise settings (`system_packages.sudo`): https://mise.jdx.dev/configuration/settings.html
- mise tools `os` field: https://mise.jdx.dev/dev-tools/
- mise use -g: https://mise.jdx.dev/cli/use.html
- mise.lock and `--locked`: https://mise.jdx.dev/dev-tools/mise-lock.html
- mise installation, `MISE_VERSION`, packslip: https://mise.jdx.dev/installing-mise.html
- Homebrew manpage (`brew bundle --file`, `--no-upgrade`): https://docs.brew.sh/Manpage
- Homebrew ca-certificates formula (`post_install_steps`): https://raw.githubusercontent.com/Homebrew/homebrew-core/HEAD/Formula/c/ca-certificates.rb
- Tailscale SSH: https://tailscale.com/kb/1193/tailscale-ssh
- Tailscale macOS variants: https://tailscale.com/kb/1065/macos-variants
- chezmoi scripts: https://www.chezmoi.io/user-guide/use-scripts-to-perform-actions/
- dockutil: https://github.com/kcrawford/dockutil
- nix-darwin dock options: https://github.com/LnL7/nix-darwin/blob/master/modules/system/defaults/dock.nix
