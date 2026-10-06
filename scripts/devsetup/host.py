"""Ordinary user configuration: shell bootstrap, Git, Zsh, fzf, macOS defaults, Dock, dotfiles.

Every command is an argument array. Failures raise RuntimeError with the failed
command; Dock entries are best effort, as before. Privileged steps use one
``sudo`` call each (``sudo -A`` when the askpass wrapper exported SUDO_ASKPASS).
Homebrew formulae and casks are installed with Homebrew itself (``config["brew"]``).
"""
from __future__ import annotations

import datetime
import os
import shlex
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

OH_MY_ZSH_INSTALLER = "https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh"
ZSH_AUTOSUGGESTIONS = "https://github.com/zsh-users/zsh-autosuggestions.git"
GLOBAL_GITIGNORE = Path(__file__).with_name("global_gitignore")

GIT_SETTINGS = (
    ("pull.rebase", "true"),
    ("core.excludesfile", "~/.global_gitignore"),
    ("fetch.prune", "true"),
    ("init.defaultBranch", "main"),
    ("push.autoSetupRemote", "true"),
)

MACOS_DEFAULTS = (
    ("com.apple.finder", "ShowPathbar", "-bool", "true"),
    ("com.apple.finder", "ShowStatusBar", "-bool", "true"),
    ("com.apple.finder", "ShowExternalHardDrivesOnDesktop", "-bool", "true"),
    ("com.apple.finder", "ShowHardDrivesOnDesktop", "-bool", "true"),
    ("com.apple.finder", "ShowMountedServersOnDesktop", "-bool", "true"),
    ("com.apple.finder", "ShowRemovableMediaOnDesktop", "-bool", "true"),
    ("com.apple.finder", "_FXShowPosixPathInTitle", "-bool", "YES"),
    None,  # chflags nohidden ~/Library
    ("com.apple.finder", "NewWindowTarget", "-string", "PfLo"),
    ("com.apple.finder", "NewWindowTargetPath", "-string", "file://{home}"),
    ("com.apple.finder", "FXDefaultSearchScope", "-string", "SCcf"),
    ("NSGlobalDomain", "AppleShowAllExtensions", "-bool", "true"),
    ("com.apple.finder", "FXEnableExtensionChangeWarning", "-bool", "false"),
    ("NSGlobalDomain", "AppleShowScrollBars", "-string", "Always"),
    ("NSGlobalDomain", "KeyRepeat", "-int", "0"),
    ("com.apple.dock", "orientation", "left"),
    ("com.apple.dock", "show-process-indicators", "-bool", "true"),
    ("com.apple.dock", "showhidden", "-bool", "true"),
    ("com.apple.dock", "launchanim", "-bool", "false"),
    ("com.apple.dock", "mineffect", "scale"),
    ("com.apple.dock", "expose-animation-duration", "-float", "0.1"),
    ("com.apple.dock", "autohide", "-bool", "false"),
    ("com.apple.dock", "autohide-delay", "-float", "0"),
    ("com.apple.finder", "EmptyTrashSecurely", "-bool", "true"),
    ("com.apple.finder", "DisableAllAnimations", "-bool", "true"),
    ("com.apple.finder", "QuitMenuItem", "-bool", "true"),
    ("com.apple.finder", "AppleShowAllFiles", "-bool", "true"),
    ("com.apple.finder", "FXPreferredViewStyle", "-string", "Nlsv"),
    ("NSGlobalDomain", "NSNavPanelExpandedStateForSaveMode", "-bool", "true"),
    ("NSGlobalDomain", "PMPrintingExpandedStateForPrint", "-bool", "true"),
    ("com.apple.LaunchServices", "LSQuarantine", "-bool", "false"),
    ("NSGlobalDomain", "AppleKeyboardUIMode", "-int", "3"),
    ("com.apple.screensaver", "askForPassword", "-int", "1"),
    ("com.apple.screensaver", "askForPasswordDelay", "-int", "0"),
    ("com.apple.screencapture", "location", "-string", "{home}/Desktop"),
    ("com.apple.screencapture", "disable-shadow", "-bool", "true"),
    ("NSGlobalDomain", "AppleFontSmoothing", "-int", "2"),
    ("com.apple.spotlight", "DictionaryLookupEnabled", "-bool", "false"),
    ("NSGlobalDomain", "NSAutomaticSpellingCorrectionEnabled", "-bool", "false"),
    ("com.apple.Terminal", "NewTabWorkingDirectoryBehavior", "-bool", "true"),
)
SOFTWARE_UPDATE_PLIST = "/Library/Preferences/com.apple.SoftwareUpdate"

# Each entry is the dockutil --add argument list; '' is a spacer tile.
DOCK_ITEMS = (
    ["/System/Applications/Home.app"],
    ["", "--type", "spacer", "--section", "apps", "--after", "Home"],
    ["/Applications/Cursor.app"],
    ["/Applications/Warp.app"],
    ["/Applications/Xcode.app"],
    ["/Applications/Figma.app"],
    ["/Applications/Bruno.app"],
    ["", "--type", "spacer", "--section", "apps", "--after", "Bruno"],
    ["/Applications/ChatGPT.app"],
    ["/Applications/Claude.app"],
    ["/Applications/Open Design.app"],
    ["", "--type", "spacer", "--section", "apps", "--after", "Open Design"],
    ["/Applications/Safari.app"],
    ["/Applications/Helium.app"],
    ["", "--type", "spacer", "--section", "apps", "--after", "Helium"],
    ["/Applications/Drafts.app"],
    ["/Applications/Notion.app"],
    ["/Applications/Obsidian.app"],
    ["/Applications/1Password.app"],
    ["/Applications/Things3.app"],
    ["", "--type", "spacer", "--section", "apps", "--after", "Things"],
    ["/System/Applications/Mail.app"],
    ["/Applications/Proton Mail.app"],
    ["/System/Applications/Calendar.app"],
    ["", "--type", "spacer", "--section", "apps", "--after", "Calendar"],
    ["/System/Applications/Messages.app"],
    ["/Applications/Slack.app"],
    ["/Applications/GatherV2.app"],
    ["/Applications/Discord.app"],
    ["", "--type", "spacer", "--section", "apps", "--after", "Discord"],
    ["/System/Applications/Music.app"],
    ["/System/Applications/Podcasts.app"],
)


def run(action: str, config: dict, *, check: bool = False) -> None:
    """Apply one host action: preflight, bootstrap, git, zsh, fzf, osx, dock, dotfiles.

    With ``check`` preflight validates prerequisites without refreshing Homebrew,
    bootstrap and git report what they would change, and the other actions only
    say they are not previewed.
    """
    actions = {"preflight": preflight, "bootstrap": bootstrap, "git": git, "zsh": zsh,
               "fzf": fzf, "osx": osx, "dock": dock, "dotfiles": dotfiles}
    if action not in actions:
        raise ValueError(f"Unknown host action {action!r}")
    if action == "preflight":
        preflight(config)
        if not check:
            _brew(config, "update")
    elif not check:
        actions[action](config)
    elif action in ("bootstrap", "git"):
        actions[action](config, check=True)
    else:
        print(f"{action}: not previewed in check mode; nothing changed.")


# Command helpers -----------------------------------------------------------

def _run(argv, *, capture: bool = False, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([str(part) for part in argv], check=True, text=True,
                              stdout=subprocess.PIPE if capture else None, **kwargs)
    except FileNotFoundError as error:
        raise RuntimeError(f"{argv[0]} is not installed or not on PATH.") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"{shlex.join(map(str, argv))} failed with exit status {error.returncode}.") from error


def _sudo(*argv) -> list:
    return ["sudo", "-A", *argv] if os.environ.get("SUDO_ASKPASS") else ["sudo", *argv]


def _brew(config: dict, *args, capture: bool = False) -> subprocess.CompletedProcess:
    return _run([config["brew"], *args], capture=capture)


def _brew_has(config: dict, kind: str, name: str) -> bool:
    """True when ``brew list --formula|--cask NAME`` finds an installed package."""
    return subprocess.run([config["brew"], "list", kind, name], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def _formula(config: dict, name: str, *, latest: bool = False) -> None:
    """Install a Homebrew formula if missing; with ``latest`` also upgrade an installed one."""
    if not _brew_has(config, "--formula", name):
        _brew(config, "install", "--formula", name)
    elif latest:
        _brew(config, "upgrade", "--formula", name)


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")


def _unique_dir(parent: Path, name: str) -> Path:
    """Create and return a new directory that no earlier run used."""
    parent.mkdir(parents=True, exist_ok=True)
    for suffix in range(1000):
        candidate = parent / (name if suffix == 0 else f"{name}-{suffix}")
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"Cannot create a unique backup directory in {parent}.")


def _write_if_changed(path: Path, content: str, mode: int) -> bool:
    if path.is_file() and path.read_text() == content:
        if path.stat().st_mode & 0o777 != mode:
            path.chmod(mode)
        return False
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(content)
    os.chmod(handle.name, mode)
    os.replace(handle.name, path)
    return True


def _is_external(path: Path) -> bool:
    """Shell files that are symlinks belong to another repository, such as the dotfiles."""
    return path.is_symlink()


def ensure_block(path: Path, marker: str, lines: list[str], *, check: bool = False) -> bool:
    """Insert or replace '# BEGIN/END <marker>' lines, like Ansible blockinfile.

    Symlinked files are reported and left untouched so setup never edits the
    external repository they point into.
    """
    if _is_external(path):
        print(f"{path}: left unchanged because it is a symlink to externally managed configuration.")
        return False
    begin, end = f"# BEGIN {marker}", f"# END {marker}"
    block = [begin, *lines, end]
    current = path.read_text().splitlines() if path.exists() else []
    if begin in current and end in current[current.index(begin):]:
        start = current.index(begin)
        stop = current.index(end, start)
        updated = current[:start] + block + current[stop + 1:]
    else:
        updated = current + block
    if updated == current:
        return False
    if check:
        print(f"{path}: would update the {marker} block.")
        return True
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    _write_if_changed(path, "\n".join(updated) + "\n", mode)
    print(f"{path}: updated the {marker} block.")
    return True


def _shell_files(config: dict) -> list[str]:
    return [".zshrc"] if config["platform"] == "mac" else [".bashrc", ".zshrc"]


# Actions -------------------------------------------------------------------

def preflight(config: dict) -> None:
    """Require brew, git and curl, stop above 90% disk use, and warn above 80%."""
    for command in ("git", "curl"):
        if shutil.which(command) is None:
            raise RuntimeError(f"Required command '{command}' is missing. Complete bootstrap first.")
    if not os.access(config["brew"], os.X_OK):
        raise RuntimeError(f"Homebrew is missing at {config['brew']}. Run ./install.sh --bootstrap-only first.")
    _brew(config, "--version", capture=True)
    usage = shutil.disk_usage("/")
    percent = -(-usage.used * 100 // (usage.used + usage.free))
    if percent > 90:
        raise RuntimeError(f"Disk usage is {percent}%. Free up space before running setup.")
    if percent > 80:
        print(f"Disk usage is {percent}%. Consider freeing up space before proceeding.")


def bootstrap(config: dict, check: bool = False) -> None:
    """First-run user setup after mise: SSH/GnuPG folders, shell activation, early 1Password."""
    home = Path(config["home"])
    if not check:
        for folder in (".ssh", ".gnupg"):
            (home / folder).mkdir(exist_ok=True)
    for name in _shell_files(config):
        shell = "zsh" if name == ".zshrc" else "bash"
        ensure_block(home / name, "dev-machine mise", [
            f'eval "$({shlex.quote(config["brew"])} shellenv)"',
            f'eval "$({shlex.quote(config["mise"])} activate {shell})"',
        ], check=check)
    if config["platform"] == "mac" and config["manage_ssh_config"]:
        installed = Path("/Applications/1Password.app").exists() or _brew_has(config, "--cask", "1password")
        if not installed and check:
            print("1Password: would install the desktop app (brew install --cask 1password).")
        elif not installed:
            _brew(config, "install", "--cask", "1password")
        print("Open 1Password, sign in, and enable its SSH agent before using Git over SSH.")


def git(config: dict, check: bool = False) -> None:
    """Install the latest Git and set the global identity, ignore file, and defaults."""
    if check:
        print("Git: would install or upgrade the Homebrew git formula.")
    else:
        _formula(config, "git", latest=True)
    target = Path(config["home"], ".global_gitignore")
    if _is_external(target):
        print(f"{target}: left unchanged because it is a symlink to externally managed configuration.")
    elif check:
        if not target.is_file() or target.read_text() != GLOBAL_GITIGNORE.read_text():
            print(f"{target}: would be replaced with the managed global ignore file.")
    elif _write_if_changed(target, GLOBAL_GITIGNORE.read_text(), 0o644):
        print(f"Updated {target}.")
    settings = (("user.email", config["git_email"]), ("user.name", config["git_name"])) + GIT_SETTINGS
    for name, value in settings:
        current = subprocess.run(["git", "config", "--global", "--get", name],
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if current.returncode != 0 or current.stdout.rstrip("\n") != value:
            if check:
                print(f"Git: would set {name} = {value}")
            else:
                _run(["git", "config", "--global", name, value])
    print("Git: check complete; nothing changed." if check else "Git: identity and global settings applied.")


def _checkout(repo: str, dest: Path, version: str) -> None:
    """Clone or update a Git checkout without discarding local work.

    Tracked modifications stop the run. Branches only fast-forward. A tag or
    commit selects that exact revision, without moving existing branch refs.
    Refuse to leave detached commits that no branch or tag preserves.
    """
    env = dict(os.environ)
    env.setdefault("GIT_SSH_COMMAND", "ssh -o StrictHostKeyChecking=accept-new")
    git_in = ["git", "-C", dest]
    fresh = not dest.exists()
    if fresh:
        _run(["git", "clone", "--recursive", repo, dest], env=env)
    elif not (dest / ".git").exists():
        raise RuntimeError(f"{dest} exists but is not a Git checkout. Move it aside and run again.")
    else:
        changes = _run([*git_in, "status", "--porcelain", "--untracked-files=no"], capture=True).stdout
        if changes.strip():
            raise RuntimeError(f"{dest} has local changes. Commit or stash them; setup never discards them.")
        _run([*git_in, "fetch", "--tags", "origin"], env=env)

    remote_branch = subprocess.run(["git", "-C", str(dest), "show-ref", "--verify", "--quiet",
                                    f"refs/remotes/origin/{version}"]).returncode == 0
    target = f"refs/remotes/origin/{version}" if remote_branch else version
    commit = _run([*git_in, "rev-parse", "--verify", f"{target}^{{commit}}"], capture=True).stdout.strip()
    current_commit = _run([*git_in, "rev-parse", "HEAD"], capture=True).stdout.strip()
    detached = subprocess.run(["git", "-C", str(dest), "symbolic-ref", "-q", "HEAD"],
                              stdout=subprocess.DEVNULL).returncode != 0
    if detached and current_commit != commit:
        containing_refs = _run([*git_in, "for-each-ref", "--contains", "HEAD",
                                "--format=%(refname)"], capture=True).stdout.strip()
        if not containing_refs:
            raise RuntimeError(f"{dest} has detached commits that no branch or tag preserves. "
                               "Put them on a branch before selecting another revision.")
    if remote_branch:
        current = _run([*git_in, "rev-parse", "--abbrev-ref", "HEAD"], capture=True).stdout.strip()
        if current != version:
            _run([*git_in, "checkout", version])
        try:
            _run([*git_in, "merge", "--ff-only", f"origin/{version}"])
        except RuntimeError as error:
            raise RuntimeError(f"{dest} branch {version} has diverged from origin. "
                               "Reconcile it manually; setup never resets local commits.") from error
    elif current_commit != commit:
        _run([*git_in, "checkout", "--detach", commit])
    _run([*git_in, "submodule", "update", "--init", "--recursive"], env=env)


def zsh(config: dict) -> None:
    """Make zsh the login shell and install oh-my-zsh with zsh-autosuggestions."""
    home = Path(config["home"])
    if config["platform"] == "mac":
        _formula(config, "zsh")
    if Path(os.environ.get("SHELL", "")).name != "zsh":
        _run(_sudo("chsh", "-s", config["shell_path"], config["user"]))
    oh_my_zsh = home / ".oh-my-zsh"
    if not oh_my_zsh.exists():
        cache = home / ".cache"
        cache.mkdir(exist_ok=True)
        cache.chmod(0o700)
        installer = cache / "oh-my-zsh-install.sh"
        try:
            with urllib.request.urlopen(OH_MY_ZSH_INSTALLER, timeout=60) as response:
                installer.write_bytes(response.read())
            installer.chmod(0o700)
            _run(["sh", installer], env=dict(os.environ, RUNZSH="no", CHSH="no", KEEP_ZSHRC="yes"))
        except OSError as error:
            raise RuntimeError(f"Could not download the oh-my-zsh installer: {error}") from error
        finally:
            installer.unlink(missing_ok=True)
    _checkout(ZSH_AUTOSUGGESTIONS, oh_my_zsh / "custom/plugins/zsh-autosuggestions", "master")
    if config["platform"] == "linux":
        ensure_block(home / ".zshrc", "dev-machine oh-my-zsh", [
            'export ZSH="$HOME/.oh-my-zsh"',
            "plugins=(git zsh-autosuggestions)",
            'source "$ZSH/oh-my-zsh.sh"',
        ])
    print("Zsh: login shell, oh-my-zsh, and zsh-autosuggestions ready.")


def fzf(config: dict) -> None:
    """Install fzf key bindings and completion; never edit symlinked shell files."""
    root = Path(_brew(config, "--prefix", capture=True).stdout.strip(), "opt", "fzf")
    home = Path(config["home"])
    if any(_is_external(home / name) for name in (".bashrc", ".zshrc")):
        print("fzf: shell files are externally managed; they must source ~/.fzf.zsh or ~/.fzf.bash.")
        _run([Path(root, "install"), "--key-bindings", "--completion", "--no-update-rc"])
    else:
        _run([Path(root, "install"), "--all"])


def osx(config: dict) -> None:
    """Apply the macOS preferences, the automatic update check, and restart Finder."""
    home = config["home"]
    for entry in MACOS_DEFAULTS:
        if entry is None:
            _run(["chflags", "nohidden", Path(home, "Library")])
            continue
        _run(["defaults", "write", *(part.format(home=home) for part in entry)])
    current = subprocess.run(["defaults", "read", SOFTWARE_UPDATE_PLIST, "AutomaticCheckEnabled"],
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if current.returncode != 0 or current.stdout.strip() != "1":
        _run(_sudo("defaults", "write", SOFTWARE_UPDATE_PLIST, "AutomaticCheckEnabled", "-int", "1"))
    _run(["killall", "Finder"])
    print("macOS: preferences applied.")


def dock(config: dict) -> None:
    """Replace the Dock layout with dockutil; missing apps are reported and skipped."""
    _formula(config, "dockutil")
    if shutil.which("dockutil") is None:
        print("dockutil is not available; skipping Dock configuration.")
        return
    _run(["dockutil", "--remove", "all", "--no-restart"])
    for item in DOCK_ITEMS:
        result = subprocess.run(["dockutil", "--add", *item, "--no-restart"])
        if result.returncode != 0:
            print(f"Dock: could not add {item[0] or 'spacer'}; continuing.")
    _run(["killall", "Dock"])


def dotfiles(config: dict) -> None:
    """Clone or fast-forward ~/.dotfiles, back up conflicts, and run its install.sh."""
    home = Path(config["home"])
    checkout = home / ".dotfiles"
    _formula(config, "stow")
    _checkout(config["dotfiles_repo"], checkout, config["dotfiles_version"])
    for metadata in checkout.rglob(".DS_Store"):
        if metadata.is_file() and not metadata.is_symlink():
            metadata.unlink()
    backup_root = None
    for relative in config["dotfiles_conflict_paths"]:
        target = home / relative
        if target.exists() and not target.is_symlink():
            if backup_root is None:
                backup_root = _unique_dir(home / ".dev-setup-backups", _timestamp()) / "dotfiles"
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
            print(f"{target} -> {backup}")
    _run(["./install.sh"], cwd=checkout)
    print("Dotfiles: installed from", config["dotfiles_repo"], "at", config["dotfiles_version"])
