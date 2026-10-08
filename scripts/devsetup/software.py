"""Package inventories, Homebrew installation and the mise tool installation.

Brewfiles live in packages/<layer>/. Layers apply in order: shared,
shared/<profile>, <platform>, <platform>/<profile>. Each layer may contain
Brewfile.cli, Brewfile.gui and Brewfile.app-store in Homebrew Bundle syntax.
The Brewfiles of one kind are concatenated in layer order and piped to
`brew bundle install`.

mise tools are declared once in mise/conf.d/tools.toml with `os` selectors.
The [dotfiles] entry in mise.toml links that file into the global mise
configuration so the tools work outside this checkout; `mise install` then
installs the selection for this platform and profile.
"""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess

from .host import ensure_block

BREWFILES = {"cli": "Brewfile.cli", "gui": "Brewfile.gui", "app-store": "Brewfile.app-store"}
MAC_ONLY = ("gui", "app-store")
BREW_PREFIX = {"mac": "/opt/homebrew", "linux": "/home/linuxbrew/.linuxbrew"}
# The [dotfiles] target in mise.toml; mise expands ~ itself.
GLOBAL_TOOLS_FILE = "~/.config/mise/conf.d/dev-machine-setup.toml"
SHELL_BLOCK = "dev-machine Node and pnpm"


def run(action: str, config: dict, *, check: bool = False) -> list[str]:
    """Run one software action. check=True prints commands without running them.

    Return the non-fatal problems that let later setup steps continue.
    """
    handlers = {
        "packages": _packages,
        "cli": _cli,
        "gui": _gui,
        "app-store": _app_store,
        "node": _node,
    }
    if action not in handlers:
        raise RuntimeError(f"Unknown software action: {action}")
    if config.get("platform") not in BREW_PREFIX or config.get("profile") not in ("personal", "work"):
        raise RuntimeError("Software setup needs platform mac|linux and profile personal|work.")
    return handlers[action](config, _Shell(config, check)) or []


class _Shell:
    """Runs argument arrays, printing each one; check mode prints only."""

    def __init__(self, config, check):
        self.check = check
        self.env = dict(os.environ)
        prefix = brew_prefix(config)
        paths = self.env.get("PATH", "").split(os.pathsep)
        preferred = [str(Path(config["mise"]).parent), f"{prefix}/bin", f"{prefix}/sbin"]
        self.env["PATH"] = os.pathsep.join(dict.fromkeys([*preferred, *paths]))

    def run(self, argv, *, env=None, cwd="/", input=None):
        print("$ " + shlex.join(str(part) for part in argv), flush=True)
        if input is not None:
            print("".join(f"  | {line}\n" for line in input.splitlines()), end="", flush=True)
        if self.check:
            print("  (check: not run)", flush=True)
            return 0
        try:
            return subprocess.run([str(part) for part in argv], env=env or self.env, cwd=cwd,
                                  input=input, text=input is not None).returncode
        except OSError as error:
            print(f"  {error}", flush=True)
            return 127

    def query(self, argv, *, env=None, cwd="/"):
        """Run a read-only command, also in check mode, and return (status, stdout)."""
        try:
            result = subprocess.run([str(part) for part in argv], env=env or self.env, cwd=cwd,
                                    text=True, stdout=subprocess.PIPE)
        except OSError:
            return 127, ""
        return result.returncode, result.stdout

    def which(self, name):
        return shutil.which(name, path=self.env["PATH"])


# Inventory

def layer_files(config, name):
    """The existing files called ``name`` in the selected layers, in apply order."""
    root = Path(config["repo_dir"]) / "packages"
    platform, profile = config["platform"], config["profile"]
    layers = ("shared", f"shared/{profile}", platform, f"{platform}/{profile}")
    return [root / layer / name for layer in layers if (root / layer / name).is_file()]


def brewfile(config, kind):
    """The selected Brewfiles of one kind, concatenated in layer order."""
    repo = Path(config["repo_dir"])
    parts = []
    for path in layer_files(config, BREWFILES[kind]):
        parts.append(f"# {path.relative_to(repo).as_posix()}\n{path.read_text()}")
    return "\n".join(parts)


# Paths and helpers

def brew_prefix(config):
    return Path(config.get("brew_prefix") or BREW_PREFIX[config["platform"]])


def _brew(config):
    """The Homebrew executable when it is installed, otherwise None."""
    path = Path(config.get("brew") or brew_prefix(config) / "bin/brew")
    return path if os.access(path, os.X_OK) else None


def _require_brew(config):
    brew = _brew(config)
    if not brew:
        raise RuntimeError(f"Homebrew is needed to install packages but was not found at "
                           f"{config.get('brew') or brew_prefix(config) / 'bin/brew'}. Run the bootstrap first.")
    return brew


def _bundle(shell, brew, text):
    """Install missing and upgrade outdated packages with `brew bundle`."""
    return shell.run([brew, "bundle", "install", "--file=-"], input=text,
                     env=dict(shell.env, HOMEBREW_NO_AUTO_UPDATE="1"))


def _install_tools(config, shell):
    """Link the tools file into the global mise configuration, then install every declared tool."""
    mise = [config["mise"], "-E", config["profile"]]
    if shell.run([*mise, "dot", "apply", "--yes", GLOBAL_TOOLS_FILE], cwd=config["repo_dir"]) != 0:
        raise RuntimeError(f"Could not link {GLOBAL_TOOLS_FILE} to mise/conf.d/tools.toml. "
                           "See the mise output above.")
    if shell.run([*mise, "install"], cwd=config["repo_dir"]) != 0:
        raise RuntimeError("mise tools failed to install. See the mise output above.")


def _rerun(config, action):
    return f"`mise run {action} --profile {config['profile']}`"


# Actions

def _packages(config, shell):
    repo = Path(config["repo_dir"])
    print(f"Selected package inventories for {config['platform']}/{config['profile']}:")
    for kind, name in BREWFILES.items():
        if kind in MAC_ONLY and config["platform"] != "mac":
            continue
        for path in layer_files(config, name):
            state = "" if config["steps"][kind] else " (skipped by configuration)"
            print(f"  {path.relative_to(repo).as_posix()}{state}")
    for kind in BREWFILES:
        if config["steps"][kind] and (kind not in MAC_ONLY or config["platform"] == "mac"):
            lines = [line for line in brewfile(config, kind).splitlines()
                     if line.strip() and not line.lstrip().startswith("#")]
            if lines:
                print(f"\n{BREWFILES[kind]} for `brew bundle install` ({len(lines)}):")
                print("".join(f"  {line}\n" for line in lines), end="")
    if config["platform"] != "mac":
        print("\nGUI and App Store inventories apply only on macOS.")
    state = "" if config["steps"]["cli"] else " (skipped by configuration)"
    print(f"\nmise tools from mise/conf.d/tools.toml for `mise install`{state}:")
    status, listing = shell.query([config["mise"], "-E", config["profile"], "ls", "--current"], cwd=repo)
    print(listing, end="")
    if status != 0:
        raise RuntimeError("mise could not list the declared tools. See the mise output above.")


def _cli(config, shell):
    brew = _require_brew(config)
    _remove_replaced_packages(config, shell, brew)
    text = brewfile(config, "cli")
    if text and _bundle(shell, brew, text) != 0:
        raise RuntimeError("CLI packages failed to install or upgrade. See the Homebrew output above.")
    _install_tools(config, shell)


def _remove_replaced_packages(config, shell, brew):
    """Uninstall packages that conflict with their inventory replacements.

    tlrc replaces the disabled tldr formula, which also provides `tldr`. The stable
    claude-code cask replaces the claude-code@latest channel; Homebrew refuses to
    install a cask that conflicts with an installed one.
    """
    if (brew_prefix(config) / "Cellar/tldr").exists() and shell.run([brew, "uninstall", "tldr"]) != 0:
        raise RuntimeError("Could not uninstall the disabled tldr formula.")
    old_cask = "claude-code@latest"
    installed, _ = shell.query([brew, "list", "--cask", "--versions", old_cask])
    if installed == 0 and shell.run([brew, "uninstall", "--cask", old_cask]) != 0:
        raise RuntimeError(f"Could not uninstall the {old_cask} cask that claude-code replaces.")


def _gui(config, shell):
    if config["platform"] != "mac":
        print("GUI applications are installed only on macOS; skipping.")
        return []
    text = brewfile(config, "gui")
    if text and _bundle(shell, _require_brew(config), text) != 0:
        return [f"GUI apps: Homebrew did not install or upgrade every app. Read its output above, "
                f"then run {_rerun(config, 'gui')}."]
    return []


def _app_store(config, shell):
    if config["platform"] != "mac":
        print("Mac App Store apps are installed only on macOS; skipping.")
        return []
    text = brewfile(config, "app-store")
    if not text:
        return []
    # mas finds installed apps through Spotlight, so index /Applications first.
    shell.run(["mdimport", "/Applications"])
    if _bundle(shell, _require_brew(config), text) != 0:
        return [f"App Store apps: mas did not install every app. Make sure that you are signed in "
                f"to the App Store and that each ID is for a Mac app that is still for sale, then run "
                f"{_rerun(config, 'app-store')}."]
    return []


def _node(config, shell):
    """Ubuntu shells need PNPM_HOME for pnpm's global directory; macOS dotfiles set it."""
    if config["platform"] != "linux":
        print("node: nothing to configure on macOS; the cli step installs Node with the other mise tools.")
        return []
    for name in (".bashrc", ".zshrc"):
        ensure_block(Path(config["home"]) / name, SHELL_BLOCK,
                     [f"export PNPM_HOME={shlex.quote(str(config['pnpm_home']))}",
                      'export PATH="$PNPM_HOME/bin:$PNPM_HOME:$PATH"'], check=shell.check)
    return []
