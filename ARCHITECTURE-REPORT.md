# Machine provisioning architecture report

> **Research snapshot and subsequent decision.** This report describes the
> repository at commit `b41c976b3849fc85eb742f4b6df0c6bbd38de2dc`.
> After reviewing it, the owner confirmed that all target machines are ARM64
> and chose a single-release mise cutover rather than the staged migration
> proposed below. The owner also authorised a separate, linked dotfiles PR
> to replace its Homebrew/nvm shell assumptions. Dotfiles and agent skills
> remain in their own repositories. Real installation testing retained
> Homebrew for native packages: mise 2026.10.3's bottle installer omitted
> certificate configuration needed by Git on clean Ubuntu. Make, Ansible
> and nvm were removed as provisioning engines. See `README.md` for the
> completed command surface and verification evidence.

## Recommendation

**Adopt a mise-first architecture, not an immediate mise-only rewrite.**

Use mise to own developer tool versions and the command interface. Evaluate
its current bootstrap resources as the replacement for ordinary Ansible
provisioning. Keep native package managers where their coverage is valuable.
Retain the existing Ansible safety workflows until a replacement proves the
same guarantees.

Keep three independent repositories:

1. **Machine setup:** installed software, OS configuration and explicit
   privileged operations.
2. **Dotfiles:** shell/editor configuration and portable user scripts.
3. **Agent skills:** skill content, supporting files and agent-specific
   installation mappings.

Do not migrate dotfiles or skills into this repository to make the command
count smaller. Sharing mise as an implementation tool does not require
sharing a repository or release cycle.

The main architectural goal is **one owner for each resource**, not one
executable for every operation. A single command that hides three competing
installers is not simpler than three tools with clear responsibilities.

This report proposes changes. It does not implement a migration or establish
that mise can provision the complete current inventory.

## 1. Start with the required outcome

A successful system should turn a supported machine into a usable development
environment with a small number of explicit decisions:

- Which platform and CPU architecture is this?
- Is this a personal or work machine?
- Is a desktop environment available?
- Which sensitive operations has the user explicitly requested?

The system should then provide:

- **Repeatable setup:** reapplying desired configuration repairs missing
  resources without unrelated changes.
- **Visible selection:** show which tools, applications and configurations
  belong to the selected machine.
- **Safe maintenance:** distinguish installation, upgrades and removal.
- **Clear failures:** distinguish required failures, optional failures and
  unsupported resources. Do not report a skipped package as installed.
- **Portable user configuration:** dotfiles and skills work without this
  checkout and without privileged machine provisioning.
- **Recovery:** preserve local edits and backups. Define recovery for each
  operation rather than promise whole-machine rollback.

Repeatability is not exact reproducibility. Tool lockfiles can fix many
runtime versions. Desktop applications, App Store availability, package
repositories, app self-updaters and OS changes remain external inputs.

### Preserve the existing guarantees

A migration must retain:

- All four current macOS/Ubuntu × personal/work combinations.
- Additive profiles: switching profiles does not uninstall earlier packages.
- Required versus optional installation failure handling.
- Per-run SSH and Remote Login consent; declining leaves existing access
  unchanged rather than revoking it.
- Remote Login preflight, stop-before-write ordering, effective SSH checks,
  configuration rollback and explicit revocation.
- Refusal to discard changes in the external dotfiles checkout.
- Maintenance of installed tools beyond the currently selected package layer,
  including the current runtime and Ollama update behaviour.

Reducing or withdrawing any of these behaviours is a separate decision, not
an architectural simplification.

## 2. What the repository does today

The current layers are mostly reasonable:

| Layer | Current owner | Assessment |
| --- | --- | --- |
| Initial platform detection, consent and prerequisites | `install.sh`, bootstrap shell helpers | A small bootstrap is unavoidable because the provisioner is not installed yet. |
| Convenient commands | `makefile` | Mostly a thin interface, not a second configuration engine. |
| State changes and ordering | Ansible playbooks/tasks | Useful for privileges, conditions and safety workflows. Some tasks are imperative shell commands wrapped in YAML. |
| Software inventory | Layered Brewfiles | Good separation of package data from installation logic. |
| Node selection | nvm plus Ansible | Overlaps with Homebrew-provided runtimes and package managers. |
| Dotfiles integration | Ansible calls the external repository's installer | Correct repository separation, but the integration knows some internal conflict paths. |
| Maintenance | `ansible/tasks/update.yaml` | Broader than reapplying the selected inventory. This distinction must survive migration. |

### The strongest reduction opportunity is runtime ownership

The shared inventory declares Yarn, pnpm, nvm, pipx, Deno and Go
([inventory](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/packages/shared/Brewfile.cli#L31)).
The Node task also installs nvm, installs Node LTS, selects its default,
configures pnpm and writes Ubuntu shell blocks
([Node setup](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/ansible/tasks/node.yaml#L1)).

A guarded Homebrew Node unlink operation runs from three paths: CLI package
installation, Node setup and maintenance
([handoff](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/ansible/tasks/brew-unlink-node.yaml#L1)).
That safeguard serves a real purpose. The opportunity is to remove the
ownership conflict that requires it, not simply delete the safeguard.

The maintenance task separately updates npm globals, pnpm globals, Homebrew,
App Store applications and Ollama models
([maintenance](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/ansible/tasks/update.yaml#L1)). npm and pnpm are not duplicate
stores. A replacement must account for their installed packages before
removing either update path.

### The shell boundary needs clarification

Machine setup writes Ubuntu Node/pnpm activation and Oh My Zsh configuration
([Node](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/ansible/tasks/node.yaml#L62),
[Zsh](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/ansible/tasks/zsh.yaml#L70)). It also invokes the external dotfiles
installer ([dotfiles](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/ansible/tasks/dotfiles.yaml#L86)).

The proposed boundary is: machine setup installs a shell and can change the
login shell; dotfiles own shell startup content and shell plugins. Move that
responsibility only through a coordinated change in the separate dotfiles
repository. Do not silently make skipping dotfiles remove currently supported
shell behaviour.

### “Linux” currently means Ubuntu, not every distribution

The installer and platform validation reject other distributions. Linux
setup is headless; Linux desktop application setup is not implemented
([README](https://github.com/mintuz/mac-dev-machine-setup/blob/b41c976b3849fc85eb742f4b6df0c6bbd38de2dc/README.md#L123)).

The README also explicitly warns that installing the external dotfiles does
not establish Linux shell compatibility. Changing the deployment tool does
not remove hardcoded macOS paths from configuration.

No first-party agent-skills provisioning workflow was identified in the
scoped setup code. A skills lockfile appearing in the dotfiles conflict list
is not a complete independent skills installation contract.

## 3. Tool and framework comparison

### Mise: strongest consolidation candidate

Current mise has four relevant capabilities:

1. Versioned development tools.
2. Environment configuration.
3. Task execution.
4. Machine bootstrap resources.

The fourth capability matters. Advice that mise can only replace nvm and
Make is now incomplete. Its documented bootstrap supports packages,
repositories, files, services, shell setup, macOS preferences and other host
resources. It has explicit status and preview commands. [M1]

**Good replacements in this repository:** nvm-managed runtime selection,
some global CLI installations, Make task definitions once mise is installed,
and ordinary desired-state resources currently expressed in Ansible.

**Not automatic replacements:** every Homebrew recipe, every operating-system
integration, the existing SSH safety workflow, or the current upgrade-all
maintenance contract.

Mise bootstrap is explicitly a sequence, not a transaction. Earlier changes
remain if a later phase fails. Hooks and the final bootstrap task run again
on each selected apply; they must be safe to repeat. The structured planner
does not yet represent every bootstrap section. [M1]

### Ansible + Homebrew: credible conservative alternative

Keeping Ansible is not a design failure. It already provides the repository's
platform routing and safety behaviour. You can improve ownership and replace
nvm without replacing the machine provisioner.

This is the lowest migration-risk option. Its cost is retaining Python,
Ansible collections, YAML and shell integration. Prefer it if the mise pilot
requires many custom hooks or recreates existing rollback logic.

Adding mise while leaving Make, nvm and all existing orchestration intact is
an addition, not a simplification. Each migrated responsibility needs an
explicit deletion condition.

### Homebrew Bundle: good inventory engine, not full machine provisioning

Bundle declares formulae, casks and App Store applications, among other
package types. It supports checking and applying inventories. Normal bundle
installation can upgrade packages; `--no-upgrade` changes that behaviour.
Cleanup is an explicit removal operation. [B1]

Homebrew does not by itself replace SSH policy, dotfiles ownership or all OS
configuration. Removing Ansible in favour of a large shell script around
Bundle would move most complexity into code you maintain.

Keep Brewfiles when Homebrew remains the selected installer. Do not maintain
the same package list in both Brewfiles and mise TOML.

### Nix + nix-darwin + Home Manager: stronger reproducibility, more machinery

Nix provides immutable package paths and generation-based package rollback.
nix-darwin adds macOS system configuration. Home Manager manages user packages
and configuration on macOS and ordinary Linux distributions. [N1–N3]

This is attractive when pinned dependency graphs and reproducible development
environments are primary requirements. It is not one replacement binary:

- You maintain Nix, nixpkgs inputs, nix-darwin and Home Manager configuration.
- macOS GUI coverage often still uses Homebrew through nix-darwin.
- Home Manager does not turn Ubuntu into NixOS or take over all Linux system
  configuration.
- Nix installation and macOS integration can require system-level changes
  that an employer may not permit.
- Package-generation rollback does not restore arbitrary app data or undo
  Homebrew and App Store operations. [INFERENCE from the ownership boundaries]

Current Homebrew policy also places Nix-managed installations in Tier 3.
That is a support cost, not proof that they cannot work. [B2]

**Verdict:** a credible alternative if you want to invest in Nix for its own
benefits. Do not select it only to reduce the number of files or languages.

### Pyinfra: an Ansible alternative, not an obvious reduction

Pyinfra expresses desired-state operations in Python and supports local
macOS/Linux deployment and remote shell-based deployment. It has native
package and service operations, including Homebrew. [P1–P2]

It can be preferable when Python is substantially easier for the maintainer
than YAML. It still needs package managers, platform-specific behaviour and
custom handling for unsupported preferences. Rewriting working Ansible into
pyinfra replaces one engine with another; it does not establish fewer
operational mechanisms.

**Verdict:** do not add it here without a specific Ansible limitation that
mise also cannot address.

### Chezmoi, GNU Stow and mise dotfiles: choices for the separate dotfiles repo

Chezmoi is a strong option for machine-specific templates, secrets integration,
diffs and conflict handling. Its documented scope is user configuration, not
whole-system provisioning. Using its scripts to install the entire machine
would hide provisioning inside dotfiles. [C1–C2]

Stow remains adequate when symlinks and a small amount of platform selection
meet the need. Current mise also supports links, copies, templates and
Stow-style groups. [M5]

**Verdict:** keep the current independent installer initially. Select a new
dotfiles tool only to solve a dotfiles problem. Do not add chezmoi merely
because the machine setup starts using mise.

### Devbox: project environments, not workstation provisioning

Devbox provides Nix-backed project development environments through a simpler
configuration interface. It can help where projects need consistent native
libraries as well as runtimes. It does not replace desktop application
installation, host security policy or OS preferences. [D1]

**Verdict:** an optional project-level choice, not the core of this repository.

## 4. Assessment of the supplied mise conversation

The conversation describes real current capabilities, but some conclusions
need qualification.

| Claim or suggestion | Assessment |
| --- | --- |
| OS and personal/work are separate axes | Correct design. Neither Ubuntu nor macOS implies a profile. |
| `auto_env` discovers OS-specific configuration | Supported when enabled. It discovers `linux`, `macos` and architecture variants, not an `ubuntu` distribution environment. Set this explicitly in the early configuration; do not rely on a future default. [M2] |
| Multiple selected environments layer configuration | Supported. Later explicit environments take precedence at the same directory level. Do not treat every section as an identical deep merge. [M2] |
| Package maps merge, but selected dotfile-group lists replace | Confirmed. Reusing a group name also replaces that group's table. Keep group composition inside the dotfiles repository rather than generate its internal selection here. [M3, M5] |
| Mise can install Homebrew bottles without the brew executable | Confirmed. It implements its own installation path using Homebrew metadata and artifacts. This is not equivalent to full upstream Homebrew compatibility. [M4] |
| One changed package means nothing else changes | Too strong. Dependencies, hooks and other selected resources may change. It is a proposed acceptance scenario, not a guarantee. [M1, M4] |
| A missing shell file can be restored | Supported when its declaration and source are available. Existing conflicting files and local edits require separate handling. [M5] |
| Putting shims in `.zshenv` handles SSH, cron and GUI apps | Only partly correct. It helps processes which actually start zsh. A GUI app, scheduler or service may never read that file. Configure those execution environments explicitly or use `mise exec` with a known executable path and context. [M6] |
| Moving npm CLIs out of Brew removes Node conflicts | Plausible for migrated tools, not proof for the whole inventory. Some Brew dependencies may still need their own Node. Prove active command resolution before removing the current handoff. [M7] |

The screenshots' sample personal/work package lists are not the repository's
current selection. For example, Slack and Zoom are currently in the shared
Mac GUI inventory. A framework migration must not silently move them into a
work-only profile.

### Four concrete compatibility issues for this repository

**1. Linux CLI casks do not translate directly.**

The shared Brewfile includes `codex`, `notion-cli`, `1password-cli` and
`claude-code@latest` as casks. Mise's current Linux `brew-cask` implementation
supports font-only casks, not arbitrary CLI casks. Those tools need validated
mise tool backends or another supported provider before Linux Homebrew can
be removed. [M4]

**2. Intel Macs need a separate decision.**

Mise's native Homebrew formula backend supports Apple Silicon macOS and
x86-64/ARM64 Linux, but not Intel macOS. This limitation is not a statement
that the mise tool manager itself excludes Intel Macs. Homebrew's own current
policy also gives Intel macOS reduced support. If Intel machines are part of
the fleet, the target architecture must keep an appropriate provider. [M4, B2]

**3. Existing casks do not become mise-owned on declaration.**

Mise can recognise a qualifying Homebrew-owned cask as installed, but leaves
its lifecycle with Homebrew and skips upgrading it. Declaring those apps and
then deleting Brew would leave an incomplete maintenance path. Cask
migration needs explicit ownership and recovery decisions. [M4]

**4. A package apply is not the existing update command.**

Mise bootstrap package `"latest"` accepts an installed version; ordinary apply
does not upgrade it. Its package upgrade command targets configured installed
packages. The repository's current maintenance covers all installed Brew
packages and runtime globals, plus Ollama models. A one-command substitution
would reduce supported behaviour. [M3]

Other gaps include unsupported formula/cask operations, no native `brew
services` implementation, and macOS defaults support limited to user domains.
The repository currently writes a privileged Software Update preference, so
not every macOS task is a direct defaults-table conversion. [M4, M8]

## 5. Proposed architecture

### Resource ownership

| Resource | Proposed owner |
| --- | --- |
| Developer runtimes and suitable standalone CLIs | Mise tool declarations; project requirements override user defaults. |
| Native libraries, login shells and OS integration packages | The platform's selected package provider. |
| macOS GUI applications | Homebrew initially; native mise installation only after inventory-specific proof. |
| Ordinary machine configuration | Mise bootstrap where supported; retain explicit exceptions rather than hide them. |
| SSH configuration and Remote Login | Existing guarded workflows until equivalent behaviour is proven. |
| Shell/editor settings, activation and user scripts | Independent dotfiles repository. |
| Skill content and agent destination mapping | Independent agent-skills repository. |
| Application project dependencies | Each project and its package manager, not machine setup. |
| Authentication, app licences, OS privacy grants and employer policy | Explicit user/administrator steps. |

For Linux, prefer mise for portable user tools and the distribution package
manager for host integration. Keep Linux Homebrew while any required inventory
entry still depends on it. Removing it is a coverage milestone, not a
prerequisite for adopting mise.

For macOS, retaining Homebrew is the conservative starting point for the
existing commercial apps, installers and taps. Mise's native provider is a
credible later option, not a drop-in assumption.

### Keep the dependency direction one-way

```text
machine-setup
  ├── installs tools and applies machine configuration
  ├── optionally invokes dotfiles' public installer
  └── optionally invokes agent-skills' public installer

 dotfiles ────── does not call machine-setup
 agent-skills ── does not call machine-setup or depend on dotfiles
```

Each external repository should document its own prerequisites, profile
inputs, destination ownership, preview/apply operations and failure status.
Machine setup should know its URL, selected revision and public installer,
not its internal symlink groups or individual file list.

For reproducible setup, use reviewed revisions. Let an explicit update
operation advance them. Do not reset dirty checkouts. Mise's repository
resources already document clean-worktree and origin checks. [M9]

Skills should retain ordinary `SKILL.md` directories, relative references
and declared dependencies. Agent-specific installation paths are adapters,
not the canonical content layout. The Agent Skills format helps portability,
but it does not guarantee that every agent implements the same tools or
permissions. [S1]

Do not synchronise agent credentials, session databases or runtime caches as
skills. Keep work-only material outside any repository cloned to personal
machines when confidentiality requires that boundary; selecting a profile is
not an access-control mechanism.

### A small proposed repository shape

These are proposed paths, not an implemented layout. The existing `packages/`
and `ansible/` trees remain during migration; do not create empty overlays.

```text
machine-setup/
├── install.sh             # minimal prerequisites, platform checks and consent
├── .miserc.toml           # explicit platform-environment behaviour
├── mise.toml              # ordinary setup and named maintenance/check tasks
├── mise.macos.toml        # macOS resources
├── mise.linux.toml        # supported Linux resources
├── mise.personal.toml    # personal-only additions
├── mise.work.toml        # work-only additions
├── packages/              # existing Brewfiles while Brew owns these packages
├── ansible/               # existing safety/system exceptions as migration proceeds
└── scripts/               # existing checks and genuinely necessary helpers
```

Keep package ownership singular: a Brew-owned package stays in its Brewfile;
a mise-owned tool stays in its tool manifest. Do not generate and commit a
second package inventory.

Put personal/work application differences in profiles. Detect the actual OS
and architecture. Add a desktop capability only where it is needed. Do not
introduce an arbitrary host/role/module framework before real machines need
it.

Keep profile selection explicit, as it is today. If a checkout-local default
is later useful, make persistence a deliberate choice. Do not set global
`MISE_ENV=work` merely to select machine setup: it also affects unrelated
projects' mise environment selection. Reject simultaneous work and personal
selection rather than allowing their union accidentally.

Do not use an OS override to bypass platform checks during real provisioning.
Use isolated test environments for cross-platform validation.

### Tool availability outside this checkout

A root `mise.toml` alone does not provide a machine-wide default when the user
leaves this repository. Mise configuration is directory-sensitive. [M2]

Publish the machine's runtime defaults through one dedicated global mise
configuration fragment, with one authoritative source. Leave the remaining
user mise configuration to the dotfiles repository. Do not make both
repositories own the same global file or runtime declaration.

Validate lockfile placement and selection for this arrangement during the
pilot. Provisioning must work when dotfiles are skipped, using explicit mise
execution where necessary. Independently installed dotfiles should activate
mise when available without failing when it is absent.

### Keep operation semantics explicit

Use separate operations for:

- **Preview/status:** inspect the selected configuration without applying it.
- **Apply:** establish the chosen configuration.
- **Update:** refresh installed software under the documented maintenance
  contract and report partial failures.
- **Removal:** an explicit, reviewed operation; never implicit profile cleanup.
- **Remote access:** distinct check, enable and revoke operations.

Do not turn a task named `plan` into `bootstrap` unless its read-only behaviour
is enforced. Mise tasks can install missing tools before running, so wrapping
a preview in a task does not automatically make it read-only. [M10]

Do not express security ordering as a list of task dependencies and assume
that list is sequential. Mise prerequisites may run concurrently. [M10]

Keep secrets in the existing credential systems. Review configuration before
trusting it. A pinned tool version or checksum is not proof that the tool is
safe, and a trusted config can execute commands. [M11]

## 6. Migration plan and proof obligations

### Stage 1: pilot mise without changing machine ownership

Use a disposable Ubuntu environment and a disposable Mac/runner. Do not
activate or revoke real Remote Login on the development host.

Pin the mise version under evaluation. Check every currently required package
and app against its proposed provider, including taps and CLI casks. Test the
actual CPU architectures in the fleet.

The pilot must pass these gates:

1. All four current OS/profile combinations select the intended inventory.
   No personal-only package appears on a fresh work machine.
2. A second apply makes no unintended changes. Hooks are checked separately;
   a success exit code alone is not evidence of convergence.
3. A deleted managed resource is restored, while conflicting user files and
   dirty external checkouts remain protected.
4. Runtime versions resolve correctly in interactive shells, non-interactive
   execution, SSH commands, services and relevant GUI/editor processes.
5. Required failures stop/report correctly; optional failures remain visible
   without silently becoming required. Unsupported managers cannot produce a
   false success.
6. Apply, update and profile changes retain their distinct behaviours.
   Existing unmanaged/installed tools are not silently excluded from the
   documented update contract.
7. Existing Homebrew casks retain a working update owner. Any ownership
   transfer has an app-specific recovery procedure.
8. SSH and Remote Login retain their opt-in, ordering, effective-settings,
   rollback and revocation guarantees. A generic bootstrap dry run is not
   equivalent to those checks.

An Ubuntu container can prove package/configuration paths, but not a normal
systemd session, GUI behaviour or real network access. macOS runner results
also do not prove phone connectivity, firewall isolation, FileVault behaviour
or employer approval. Use the appropriate machine-level evidence for those
claims.

### Stage 2: replace runtime selection and the task interface

Move Node and suitable runtime/CLI declarations to mise. Preserve npm/pnpm
application dependency workflows; replacing nvm does not remove the need for
project package managers.

Only after the new runtime works should the migration remove old nvm
activation and configuration. Check every execution context before deleting
the Brew Node handoff. A Brew dependency may retain its own runtime without
becoming the user's active Node provider.

Replace Make task definitions after bootstrap can provide mise. Retain one
small installer for the pre-mise state. Move all named operations, not just
full setup, before deleting the old command surface.

### Stage 3: replace ordinary provisioning where mise wins

Move resources in complete slices: package application, repository checkouts,
user defaults and other supported operations. For each slice, remove the old
owner after equivalent behaviour is proven.

Preserve the current optional-install policy and maintenance failure summary.
If supporting these requires substantial new orchestration, compare that cost
with retaining the existing Ansible implementation.

Keep SSH/Remote Login and unsupported privileged preferences in their existing
implementation. This is an explicit architectural exception, not permission
to leave two general provisioners managing the same resources indefinitely.

### Stage 4: consider removing additional providers

Remove Linux Homebrew only after every required package has a working provider.
Consider mise's native macOS package installer only after the complete app
inventory and ownership transitions pass. Removing the Brew executable still
leaves a dependency on Homebrew metadata and artifact distribution.

Remove the final Ansible dependency only if its remaining behaviours have an
equally safe, smaller implementation. Do not rewrite the Remote Login system
into shell solely to claim fewer frameworks.

### Concrete reduction ledger

These are proposed counts for named mechanisms, not measured migration results.
No whole-system equivalence or line-count reduction is claimed.

| Scope | Before | Proposed after | Proof and rollback boundary |
| --- | --- | --- | --- |
| Separate Node version-manager dependencies | nvm: 1 | nvm: 0; mise takes this responsibility | Prove Node/CLI resolution; restore prior activation/provider if this slice fails. |
| Brew Node handoff invocation sites | 3 | 0, conditional on runtime proof | Exercise setup and upgrades across shell contexts; retain the existing handoff until the condition is met. |
| Make task-definition systems | 1 | 0; mise tasks: 1 | This is a replacement, not a reduction by itself. Move every named operation; rollback only task dispatch if required. |
| General machine desired-state owners | Ansible: 1 | mise bootstrap: 1 | Temporary overlap during migration: 2. Cut over one resource at a time; retained Ansible safety exceptions are counted separately. |
| Ansible engine dependency | 1 | 1 while safety exceptions remain | No dependency reduction claimed. Remove only after all remaining guarantees have equivalent evidence. |
| Linux Homebrew installations required by setup | 1 | 0, conditional on package coverage | Test the full inventory; retain Brew for unmigrated packages rather than silently skip them. |
| Independent machine/dotfiles/skills sources in the target | Three responsibilities | Three independent repositories | Separation is retained, not counted as a reduction. Each external installer must work without machine setup. |

A configuration rollback cannot reliably undo arbitrary package or app changes.
Use VM snapshots for destructive pilot recovery. For an existing machine,
define provider-specific recovery before changing ownership; do not assume a
Git revert restores the machine.

## 7. Long-term maintenance rules

1. Give each installed command, file and service one declared owner.
2. Keep OS/profile selection separate from package installation logic.
3. Keep machine-wide defaults separate from project requirements.
4. Review tool/installer updates before applying them across all machines.
5. Record the supported distribution, OS-version and CPU matrix. Add support
   only when its bootstrap and actual package paths pass.
6. Run fresh-machine and second-apply checks in addition to fast routing and
   safety checks. Retain the existing safety suite through migration.
7. Preserve explicit opt-ins and do not make profile switching destructive.
8. Add a dependency only when it removes more owned behaviour than it adds.

## 8. Evidence and limitations

Repository inspection covered entrypoints, inventories, runtime setup,
maintenance, shell integration, dotfiles integration and the documented safety
contracts. The external dotfiles and skills repositories were not modified or
audited for full portability.

Executed on the current host:

- `make packages PROFILE=personal`: passed; Ansible reported `changed=0`,
  `failed=0` and selected seven inventory files.
- `make packages PROFILE=work`: passed; Ansible reported `changed=0`,
  `failed=0` and selected six inventory files.

Both runs emitted an Ansible interpreter-discovery warning. They were inventory
previews, not installation tests.

Mise was not installed in the command environment. Its capabilities in this
report come from current official documentation and release evidence, not a
local mise provisioning run. No package installation, system setting change,
SSH activation/revocation or full setup was performed. No claim is made that
the proposed architecture has passed the pilot gates.

The research added this report only; it did not change provisioning code.

## Sources

### Mise

- [M1: Bootstrap behaviour, phases and preview limits](https://mise.jdx.dev/bootstrap.html)
- [M2: Configuration](https://mise.jdx.dev/configuration.html) and [environment selection](https://mise.jdx.dev/configuration/environments.html)
- [M3: Host package providers and apply/upgrade semantics](https://mise.jdx.dev/bootstrap/packages/)
- [M4: Native Homebrew formula/cask installer, ownership and limitations](https://mise.jdx.dev/bootstrap/packages/brew.html)
- [M5: Dotfiles and group selection](https://mise.jdx.dev/dotfiles.html)
- [M6: Shims and process-environment limits](https://mise.jdx.dev/dev-tools/shims.html) and [shell activation](https://mise.jdx.dev/bootstrap/shell.html)
- [M7: npm tool backend](https://mise.jdx.dev/dev-tools/backends/npm.html)
- [M8: macOS defaults and Dock support](https://mise.jdx.dev/bootstrap/macos-defaults.html)
- [M9: Repository checkout and update rules](https://mise.jdx.dev/bootstrap/repos.html)
- [M10: Task execution and dependency ordering](https://mise.jdx.dev/tasks/)
- [M11: Trust and verification boundaries](https://mise.jdx.dev/security.html)
- [Tool lockfiles and backend-specific guarantees](https://mise.jdx.dev/dev-tools/mise-lock.html)
- [Release evidence: v2026.10.3, including dotfile groups](https://github.com/jdx/mise/releases/tag/v2026.10.3)

### Alternatives and portability

- [B1: Homebrew Bundle](https://docs.brew.sh/Brew-Bundle-and-Brewfile)
- [B2: Homebrew support tiers](https://docs.brew.sh/Support-Tiers) and [Linux requirements](https://docs.brew.sh/Homebrew-on-Linux)
- [N1: Nix model and guarantees](https://nix.dev/manual/nix/stable/introduction)
- [N2: nix-darwin](https://github.com/nix-darwin/nix-darwin) and [Homebrew integration](https://nix-darwin.github.io/nix-darwin/manual/index.html#opt-homebrew.enable)
- [N3: Home Manager installation and rollback](https://nix-community.github.io/home-manager/print.html)
- [Nix installation requirements](https://nix.dev/manual/nix/stable/installation/installing-binary)
- [P1: Pyinfra compatibility](https://docs.pyinfra.com/en/latest/compatibility.html)
- [P2: Pyinfra deployment model](https://docs.pyinfra.com/en/latest/deploy-process.html) and [Brew operations](https://docs.pyinfra.com/en/latest/operations/brew.html)
- [C1: Chezmoi purpose](https://www.chezmoi.io/why-use-chezmoi/)
- [C2: Chezmoi design boundaries](https://www.chezmoi.io/user-guide/frequently-asked-questions/design/)
- [D1: Devbox](https://github.com/jetify-com/devbox)
- [S1: Agent Skills format and compatibility metadata](https://agentskills.io/specification.md)
