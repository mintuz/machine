# Machine provisioning: keep mise, replace generic helpers selectively

## Finding and evidence boundary

**Mise is not the wrong tool. The repository uses only part of its current capability.** Keep Homebrew Bundle for native packages. Evaluate mise bootstrap for ordinary host configuration. Keep the small, explicit security subsystem until another implementation proves its exact safety contract.

This is research, not an implemented migration. I read `AGENTS.md`, `README.md`, `ARCHITECTURE-REPORT.md`, `mise.toml`, `defaults.toml`, `install.sh`, `scripts/devsetup/{cli,software,host}.py` and `scripts/with-sudo-askpass.sh`. I fetched the upstream sources linked below. I ran no installation, provisioning, privileged command or project test. Live documentation establishes advertised capability, not compatibility with the repository's pinned mise 2026.10.3 or proof on a clean machine.

The important current boundaries are already sound:

- `AGENTS.md:164-216` assigns native packages to Homebrew and runtimes to mise. `software.py` composes four inventory layers and records tools in a separate global fragment.
- `cli.py:51-126` owns ordering and different fatal/non-fatal failure policies. `install.sh:112-169` owns consent and always excludes Remote Login from installation.
- `host.py` also implements generic file updates, repository checks, shell blocks, defaults and Dock operations. These are the main candidates for upstream replacement.
- `AGENTS.md:229-314` specifies a security transaction, not merely an SSH configuration file. It requires stop-before-write, effective-settings gates, metadata rollback, account restrictions and offline revocation.

The historical report already recognised mise bootstrap. It also records the failed native-bottle experiment: missing Git certificate configuration on clean Ubuntu (`ARCHITECTURE-REPORT.md:3-13`; `AGENTS.md:178-185`). That observed failure remains evidence against cutover. Broader current documentation does not invalidate it.

## What good provisioning looks like in 2025–2026

There is no single demonstrated industry-standard personal stack. Published configurations show several durable patterns:

- [Jeff Geerling's Mac Dev Playbook](https://github.com/geerlingguy/mac-dev-playbook) uses Ansible, Homebrew, mas, Dock roles and external dotfiles. Its author reports use on roughly 20 Macs and documents remaining manual steps.
- [Dustin Lyons' Nix configuration](https://github.com/dustinlyons/nixos-config) combines flakes, nix-darwin, Home Manager and Homebrew. It includes custom scripts and a Dock module. Its Linux target is **NixOS**, not evidence of Ubuntu host management.
- [Tom Payne's dotfiles](https://github.com/twpayne/dotfiles) use chezmoi, 1Password and separate macOS/Linux scripts for packages and settings. Even the chezmoi author's setup retains imperative scripts.

[INFERENCE] The common lesson is clear ownership, declarative inventories and tested escape hatches. It is not zero custom code. Team-managed work machines add central policy and reporting; a personal installer should not compete with that authority.

## Mise: more than runtimes, less than this security contract

### Established responsibilities

Mise owns `[tools]`, environment variables and named tasks. [Tasks](https://mise.jdx.dev/tasks/) run commands with the configured tools and environment. Task dependencies may run concurrently; listing dependencies does not preserve the repository's setup sequence. [Settings](https://mise.jdx.dev/configuration/settings.html) configure mise itself, not application settings. `mise settings set` writes global configuration by default. Keep the current auto-install exclusions for read-only commands (`mise.toml:3-10`).

[`mise use -g`](https://mise.jdx.dev/cli/use.html) installs and records global tool requests. `--path` can target a specific configuration file instead. It does not by itself reproduce the repository's protected, additive fragment policy. [`mise.lock`](https://mise.jdx.dev/dev-tools/mise-lock.html) records concrete resolutions and backend-dependent verification data; `mise install --locked` requires the applicable entries. It is not an operating-system or application-dependency lockfile.

[Backends](https://mise.jdx.dev/dev-tools/backends/) cover `npm:` CLIs, isolated Python CLIs through `pipx:`/`pypi:`, curated `aqua:` recipes and release assets. Current documentation deprecates `ubi:` in favour of release-specific backends. [`pipx:` remains supported](https://mise.jdx.dev/dev-tools/backends/pipx.html), with `pypi:` the current documented spelling. Platform artefacts and locking differ by backend. Do not migrate working providers merely to reduce the number of names.

[Hooks](https://mise.jdx.dev/hooks.html) can run on directory entry or tool installation. They are executable scripts, not automatic idempotence. Privileged provisioning should remain explicitly invoked, never hidden in an `enter` hook.

### The important correction: bootstrap already owns host resources

It would be incorrect to say mise explicitly does **not** manage system settings, privileged operations or idempotent files. Its current [bootstrap documentation](https://mise.jdx.dev/bootstrap.html) explicitly includes them:

| Resource | Documented capability | Repository-specific gap |
|---|---|---|
| Packages | apt, native Homebrew-compatible formulae/casks, mas and other managers | Native `brew:` is not `brew bundle`; semantics and coverage differ. |
| Files/directories | Content, templates, mode, owner/group, atomic replacement and narrow privilege escalation | User-writable paths can follow symlinked parents, unlike the fragment's stricter prohibition. |
| Repositories | Clone, origin checks, clean-worktree checks and safe updates | Exact local-origin equivalence, detached-commit preservation and external installer hand-off need comparison. |
| macOS defaults | Typed user preferences, current-host values and Dock application ordering | No privileged system defaults; Dock semantics differ. |
| Shell/user | Managed activation blocks and login-shell changes | Existing external-repository ownership guards must remain. |
| Services | User services on macOS/Linux; existing Linux systemd system services | No equivalent Mac system Remote Login transaction. |

Sources: [files](https://mise.jdx.dev/bootstrap/files.html), [repositories](https://mise.jdx.dev/bootstrap/repos.html), [defaults](https://mise.jdx.dev/bootstrap/macos-defaults.html), [shell](https://mise.jdx.dev/bootstrap/shell.html), [login shell](https://mise.jdx.dev/bootstrap/user.html), [services](https://mise.jdx.dev/bootstrap/services.html).

Bootstrap supplies `status`, `--dry-run` and a structured `plan`. The plan covers only the resource families listed in its documentation. Dry runs do not execute hooks or the final task. Protected-file inspection can require elevation. **Bootstrap is explicitly a sequence, not a transaction**: earlier successful changes survive later failure. History checkpoints are not evidence of whole-machine rollback. These limits exclude using generic bootstrap as proof of the Remote Login safety contract.

### Can it replace the three existing helpers?

**`host.py`: substantially, not wholesale.** Defaults, activation, simple files and login shell have native replacements. Keep guarded repository integration until equivalence is demonstrated. Keep custom Library visibility, system automatic-update preference, fzf/Oh My Zsh integration and application restarts where needed. The native Dock `apps` list requires every app to exist, preserves non-application tiles and clears apps for `[]`. Current `dock()` tolerates missing apps, creates positioned spacers and leaves an empty list untouched (`host.py:342-395`; `defaults.toml:90-124`). Retain dockutil rather than silently changing those behaviours.

**`software.py`: simplify orchestration; do not replace Bundle with `brew:` now.** [Mise's native installer](https://mise.jdx.dev/bootstrap/packages/brew.html) downloads bottles and evaluates its own Formula/Cask DSL. It never invokes Homebrew for core formulae. Unsupported DSL/artifacts fail, `brew services` is not implemented, and Homebrew-owned casks remain Homebrew-owned: mise skips upgrading them. The separate `macos-app:` manager needs a declared URL/version/checksum and supports app bundles, not arbitrary pkg installers ([packages](https://mise.jdx.dev/bootstrap/packages/)).

Moreover, bootstrap package `latest` accepts already-installed versions; Bundle normally upgrades outdated entries. Mise package upgrade targets configured installed packages, not the repository's update-all contract. Replacing calls without preserving these differences changes behaviour (`software.py:226-238`; `AGENTS.md:218-227`). Keep Brewfiles and invoke Bundle from thin ordered tasks.

**`with-sudo-askpass.sh`: not a proven drop-in replacement.** Mise documents interactive sudo prompts, non-interactive failure without passwordless access and a setting forbidding escalation ([sudo rules](https://mise.jdx.dev/bootstrap/packages/#sudo)). It does not document this wrapper's full one-prompt keepalive, NOPASSWD verification fallback and cleanup contract. It also does not supply credentials to arbitrary custom tasks automatically. Native resources reduce the calls needing the wrapper, but do not justify deleting it yet.

[INFERENCE] Maintenance is low for conventional tool/task use and moderate for bootstrap adoption because of semantic verification. Lock-in is moderate: TOML and commands are portable data, but resource behaviour depends on mise. “Just mise” still leaves custom policy and, with native packages, transfers substantial package-manager compatibility responsibility to mise upstream.

## Other tools: ownership, gaps and cost

### Homebrew Bundle and focused macOS utilities

[Homebrew Bundle](https://docs.brew.sh/Brew-Bundle-and-Brewfile) already supplies declarative installation through `brew`, `cask`, `tap`, `mas "Name", id: N` and `vscode` entries. `greedy: true` deliberately upgrades otherwise self-updating/unversioned casks. `brew bundle check` reports unmet dependencies; it is not a general host preview. Brewfiles are Ruby, so executable expressions can run during checking. Keep this repository's inventories literal.

`brew bundle cleanup` removes software absent from its selected inventory and can reset the global trust store to that file. Do not run it against additive personal/work subsets. Bundle explicitly rejects the idea of a version-pinning Brewfile lockfile. It manages rolling native packages, not exact reproducibility.

Older examples contain `whalebrew` lines. Do not adopt them: [Homebrew issue 20758](https://github.com/Homebrew/brew/issues/20758) records support disabled in September 2025, and current Bundle documentation omits it. `vscode` remains documented. Bundle itself is now part of Homebrew, not a separate tap ([upstream](https://github.com/Homebrew/homebrew-bundle)).

[`mas`](https://github.com/mas-cli/mas) owns App Store automation. It still needs the relevant signed-in account, purchases and Spotlight visibility. It cannot purchase paid apps or manage iOS/iPadOS apps. [`dockutil`](https://github.com/kcrawford/dockutil) owns application tiles, spacers, folders and ordering. [`macos-defaults`](https://macos-defaults.com/) is a reference catalogue with demonstrations, not a convergence engine. None owns profiles, consent or SSH rollback.

[INFERENCE] Keep these tools. Their lock-in is low: Brewfiles and native preferences remain understandable. Maintenance is low for inventory and moderate for macOS-version compatibility. Moving `defaults write` lines into another language cannot prove that Apple still honours every key.

### chezmoi

[Chezmoi](https://www.chezmoi.io/) is a strong cross-OS user-file owner. [Templates and machine data](https://www.chezmoi.io/user-guide/manage-machine-to-machine-differences/) express personal/work and macOS/Ubuntu differences. [1Password functions](https://www.chezmoi.io/user-guide/password-managers/1password/) retrieve data through `op`; they do not enable or sign in to the desktop SSH agent.

[`run_once_` and `run_onchange_`](https://www.chezmoi.io/user-guide/use-scripts-to-perform-actions/) key execution to successful content hashes, not actual host drift. A manually removed package can therefore remain missing until the script changes. Scripts still need idempotence. [`.chezmoiexternal`](https://raw.githubusercontent.com/twpayne/chezmoi/master/assets/chezmoi.io/docs/reference/special-files/chezmoiexternal-format.md) fetches files, archives and Git repositories, with optional checksums and refresh periods. It is not proof of this repository's guarded external-checkout contract.

[INFERENCE] Chezmoi offers moderate maintenance and moderate template/source-state lock-in. It is attractive if user-file management is the main problem. Here the external dotfiles repository already owns that territory (`AGENTS.md:121-144`). Adding chezmoi only around a few machine-owned files risks a second configuration owner. It cannot remove the custom security transaction or make defaults/Dock scripts declarative automatically.

### Nix, nix-darwin, Home Manager and nix-homebrew

[Nix flakes](https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-flake.html) package configuration and lock inputs. [nix-darwin](https://github.com/nix-darwin/nix-darwin) supplies declarative Mac system modules. [Home Manager](https://github.com/nix-community/home-manager) supplies user packages and files, including standalone use outside NixOS. It explicitly warns about Nix expertise and compatibility on other Linux distributions. Ubuntu remains Ubuntu; Home Manager does not become its system provisioner.

[`nix-homebrew`](https://github.com/zhaofengli/nix-homebrew) pins/installs Homebrew and optionally taps. It **does not manage installed packages**; nix-darwin's `homebrew.*` options do that. Homebrew casks and mas remain mutable external operations. [INFERENCE] A generation rollback cannot be assumed to undo their effects or the Remote Login transaction.

[Determinate's installer](https://github.com/DeterminateSystems/nix-installer) supports ARM64 Mac/Linux and uninstall. It now defaults to **Determinate Nix**, not simply upstream Nix. [Its nix-darwin guide](https://docs.determinate.systems/guides/nix-darwin/) requires disabling nix-darwin's Nix management or using the Determinate module. Choose that owner explicitly. Nix-darwin's own README currently recommends the Lix installer instead.

[INFERENCE] This has the highest configuration-language and activation-model lock-in. Maintenance shifts from Python to Nix modules, input updates and package exceptions. It is worthwhile for a team already committed to Nix or genuinely reproducible development closures. It is not the cheapest route to fewer lines on these two operating systems. Keep external dotfiles untouched and security separately invoked.

### Ansible

Ansible supplies the mature middle ground. [`community.general.homebrew`](https://raw.githubusercontent.com/ansible-collections/community.general/main/plugins/modules/homebrew.py) manages Homebrew package states with check mode. [`osx_defaults`](https://raw.githubusercontent.com/ansible-collections/community.general/main/plugins/modules/osx_defaults.py) manages typed preferences and supports privilege escalation for system preference paths. [`geerlingguy.mac`](https://github.com/geerlingguy/ansible-collection-mac) supplies Homebrew, mas and Dock roles.

[INFERENCE] Ansible can replace more generic host plumbing than chezmoi, across Mac and Ubuntu, while retaining normal-user execution and selective escalation. Security rollback still needs deliberately authored tasks or the existing helper. Maintenance is moderate: Python, collections, role versions and YAML remain dependencies. Lock-in is moderate. It would reverse the explicit current no-Ansible decision (`AGENTS.md:3-7,38-43`), so recommend it only as an authorised future architecture choice, not a parallel path.

### Dotbot, comtrya and Pkl

- [Dotbot](https://github.com/anishathalye/dotbot) is good at links, directories and ordered shell commands. It deliberately does not manage the repository itself. [INFERENCE] Low lock-in and low core maintenance, but packages, settings and SSH would remain scripts/plugins. It belongs inside the external dotfiles installer, not as this repository's new host engine.
- [Comtrya](https://github.com/comtrya/comtrya) targets local packages and files. Its README announces archival after failing to find maintainers. [INFERENCE] Reject it: adopting maintenance responsibility defeats the goal. Its manifests add moderate lock-in without a supported route through the security contract.
- [Pkl](https://pkl-lang.org/main/current/introduction/index.html) is a typed configuration language with validation and generation tooling. [INFERENCE] It could replace TOML parsing, but not host convergence. Reject it here: another evaluator and schema language leave the provisioner intact. Low output-format lock-in does not compensate for new authoring complexity.

### Apple management, Fleet, Kolide and Kandji

[Apple declarative device management](https://support.apple.com/en-ca/guide/deployment/depc30268577/web) lets enrolled devices apply and maintain declarations autonomously, including software-update and configuration policy. It extends the existing management protocol; it is not a local Brewfile runner or an Ubuntu solution.

[Fleet](https://fleetdm.com/) advertises cross-platform device/software management and GitOps, with hosted or self-hosted deployment. [Kolide](https://www.kolide.com/) focuses on device posture, access decisions and user remediation, not personal package convergence. [Kandji now redirects to Iru](https://www.iru.com/kandji-mdm), whose Apple capabilities cover enrolment, applications, settings and update enforcement.

[INFERENCE] For work, let the employer's existing service own security controls and managed apps. Do not purchase or deploy another service merely to replace this personal repository. Fleet adds server/service operations; Kolide adds identity-policy integration; Kandji/Iru adds commercial service dependence. Their policy/API lock-in is higher than local manifests. None establishes the exact phone-key rollback flow, and corporate policy may prohibit personal Remote Login entirely.

### Tailscale SSH and sudo

[Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh) can remove public-key distribution for supported servers. Linux is supported. Mac servers require the open-source `tailscaled` variant, not the current GUI app. It intercepts tailnet port 22 and authorises through tailnet identity, using SSH authentication type `none`. Existing non-tailnet sshd remains unchanged.

**It is not a valid drop-in architecture under the current hard requirements.** It changes phone public-key authentication, Mac client variant and revocation semantics. Merely enabling it does not disable a LAN sshd listener. [INFERENCE] Operational maintenance is lower after a deliberate security-model change, but policy/control-plane dependence increases. Keep ordinary OpenSSH over Tailscale for this assignment.

The [sudo manual](https://raw.githubusercontent.com/sudo-project/sudo/main/docs/sudo.man.in) defines `-A`/`SUDO_ASKPASS` and cached authorisation refreshed with `-v`. Askpass does not require storing the password in a file; that is the current wrapper's implementation (`scripts/with-sudo-askpass.sh:40-65`). [INFERENCE] A timestamp-only or standard graphical-helper design could reduce credential handling, but must prove terminal, headless, NOPASSWD and timeout behaviour before replacement. Never run the complete provisioner as root.

## Three candidate target architectures

All candidates retain ARM64 Mac/Ubuntu, both profiles, explicit 1Password consent, the external dotfiles installer, mas, Dock/preferences and separately invoked transactional Remote Login. None may delete the security checks simply to improve a line count.

The ranges below are **[INFERENCE] planning estimates**, not measured implementations. They count executable custom Python/shell plus separate tests, excluding inventories, templates and declarative TOML/Nix. The task supplies approximately 4,900 current lines including checks. Savings must be assessed against replacement configuration too.

| Candidate | What disappears or shrinks | What remains custom | Estimated retained custom lines | Risk and platform handling |
|---|---|---|---|---|
| **A: Homebrew Bundle + mise + chezmoi** | Replace file-writing parts of `host.py`; shrink `config.py` and `cli.py`; retain Bundle/tool adapter in `software.py`. No honest wholesale file deletion yet. | Consent/bootstrap, profile/step policy, external-checkout safeguards, defaults/Dock scripts, sudo, security, update-all. | 1,600–2,100 production; 1,600–2,300 checks; 3,200–4,400 total. | Medium. Both OSes use chezmoi data/conditions. Keep its ownership strictly outside the external dotfiles paths. |
| **B: nix-darwin + Home Manager + nix-homebrew** | Retire generic `host.py`/`software.py` after moving retained exceptions into focused helpers; replace generic `config.py`/`cli.py` with Nix modules and thin entry points. Migrate inventories, not duplicate them. | Consent, normal-user launcher, Ubuntu bootstrap/system gaps, external installer integration, security, maintenance exceptions. | 1,200–1,800 production; 1,500–2,200 checks; 2,700–4,000 total, plus substantial Nix. | High. Darwin uses system modules; Ubuntu uses standalone Home Manager and apt/bootstrap. Keep mise only for project runtimes with no competing Nix owner. Privileged activation remains explicit. |
| **C: Homebrew Bundle + mise bootstrap + narrow policy helpers** | Replace ordinary defaults/files/activation/login-shell portions of `host.py`; remove redundant tool selection code where native config proves equivalent; shrink `software.py`, `cli.py` and `config.py`. | Security unchanged initially; consent/bootstrap; ordered Bundle adapter; protected additive fragment; external-repository guards; dockutil/system-default exceptions; sudo and update-all. | 1,400–1,900 production; 1,500–2,200 checks; 2,900–4,100 total. | Low-to-medium. Shared mise configuration with explicit platform/profile selection; Bundle on both OSes; apt only for existing Ubuntu prerequisites. |

For C, keep `install.sh`, bootstrap helpers, `mise.toml`, `mise.lock`, `defaults.toml`, inventories, `remote-login.sh`, security/templates, the sudo wrapper and `update.sh`, initially. No whole-file deletion is justified by capability research alone. Delete functions and their implementation-only tests only after upstream behaviour covers them. This is less dramatic than deleting the Python directory, but preserves the actual requirements.

## Migration gates

1. Write a resource ownership matrix. Distinguish native packages, runtimes, ordinary files, external dotfiles and security.
2. Compare the selected pinned mise release against live bootstrap documentation. Start with typed user defaults. Preserve system defaults and Dock exceptions.
3. Prove all four OS/profile combinations on disposable machines. Include dirty/detached external repositories, symlinked configuration ancestors, missing GUI apps and additive profile switching.
4. Keep Remote Login isolated. Its eventual replacement needs stop-before-write, failed-gate rollback, partial-activation shutdown, offline revocation and real permitted/denied connection evidence. Never validate it by provisioning the development host (`AGENTS.md:338-357`).

## Ranked recommendation

1. **C — Homebrew Bundle plus mise bootstrap and narrow policy helpers.** It removes generic mechanisms without adding another configuration framework. It respects the observed native-package failure and keeps the security transaction explicit.
2. **A — Add chezmoi only if machine-owned user-file complexity grows materially.** It has excellent templates and secret integration, but the external dotfiles boundary limits its benefit here. Avoid using content-hash scripts as a substitute for convergence.
3. **B — Choose Nix only for a stronger reproducibility goal, not line-count reduction.** Its declarative model is capable, but Ubuntu system management, mutable Mac applications and security exceptions prevent the promised one-tool simplification.

Do not adopt comtrya, Pkl, a second MDM service or Tailscale SSH as shortcuts around the present requirements. Do not reintroduce Ansible without an explicit change of architectural direction. The correct answer to “why not just mise?” is: **use more of mise where its semantics match; retain Homebrew's package expertise and the repository's genuinely distinctive safety policy.**
