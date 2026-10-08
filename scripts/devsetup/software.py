"""Package inventories, Homebrew installation, mise tools and the Node ecosystem.

Inventories live in packages/<layer>/. Layers apply in order: shared,
shared/<profile>, <platform>, <platform>/<profile>. Each layer may contain:

  Brewfile.cli, Brewfile.gui, Brewfile.app-store   Homebrew Bundle syntax
  tools.cli.toml, tools.node.toml                  a mise [tools] table

The Brewfiles of one kind are concatenated in layer order and piped to
`brew bundle install`. Tool tables are merged in layer order into the
machine-owned global mise fragment, conf.d/dev-machine-setup.toml, so they
work outside this checkout without replacing the user's own mise configuration.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import tomllib

from .host import ensure_block

BREWFILES = {"cli": "Brewfile.cli", "gui": "Brewfile.gui", "app-store": "Brewfile.app-store"}
TOOL_FILES = {"cli": "tools.cli.toml", "node": "tools.node.toml"}
MAC_ONLY = ("gui", "app-store")
BREW_PREFIX = {"mac": "/opt/homebrew", "linux": "/home/linuxbrew/.linuxbrew"}
FRAGMENT_NAME = "dev-machine-setup.toml"
FRAGMENT_HEADER = """\
# Managed by mac-dev-machine-setup. Setup adds tools here and never removes
# them. Keep your own mise settings in config.toml or another conf.d file.
"""
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


def tools(config, kind):
    """The selected mise [tools] tables of one kind, merged in layer order."""
    repo = Path(config["repo_dir"])
    merged = {}
    for path in layer_files(config, TOOL_FILES[kind]):
        relative = path.relative_to(repo).as_posix()
        try:
            table = tomllib.loads(path.read_text()).get("tools", {})
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            raise RuntimeError(f"Malformed tool inventory {relative}: {error}") from error
        if not isinstance(table, dict):
            raise RuntimeError(f"Malformed tool inventory {relative}: [tools] must be a table")
        merged.update(table)
    return merged


def _specs(tools):
    specs = []
    for name, value in tools.items():
        version = value.get("version", "latest") if isinstance(value, dict) else value
        specs.append(f"{name}@{version}")
    return specs


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


def fragment_path(config):
    base = os.environ.get("MISE_CONFIG_DIR")
    if not base:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(config["home"], ".config")
        base = os.path.join(xdg, "mise")
    return Path(base) / "conf.d" / FRAGMENT_NAME


def _guard_fragment_path(path):
    # /var and /tmp are system aliases on macOS, not externally managed config.
    aliases = {Path("/var"): Path("/private/var"), Path("/tmp"): Path("/private/tmp")}
    for part in (*reversed(path.absolute().parents), path.absolute()):
        if part.is_symlink() and not (part in aliases and part.resolve() == aliases[part]):
            raise RuntimeError(f"Refusing to access the mise runtime fragment through symlink {part}; "
                               "it may belong to another repository.")


def _fragment_tools(config):
    path = fragment_path(config)
    _guard_fragment_path(path)
    if not path.exists():
        return {}
    try:
        tools = tomllib.loads(path.read_text()).get("tools", {})
    except tomllib.TOMLDecodeError as error:
        raise RuntimeError(f"Cannot read the mise runtime fragment {path}: {error}") from error
    if not isinstance(tools, dict):
        raise RuntimeError(f"Cannot read the mise runtime fragment {path}: [tools] is not a table")
    return tools


def _toml_value(value, path):
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, dict) and all(isinstance(item, (str, bool)) for item in value.values()):
        pairs = ", ".join(f"{json.dumps(key)} = {json.dumps(item)}" for key, item in value.items())
        return "{ " + pairs + " }"
    raise RuntimeError(f"Cannot keep an unsupported tool value in {path}: {value!r}")


def record_tools(config, shell, tools):
    """Add tools to the machine-owned global mise fragment, keeping earlier entries."""
    path = fragment_path(config)
    _guard_fragment_path(path)
    existing = _fragment_tools(config)
    merged = {**existing, **tools}
    lines = [FRAGMENT_HEADER, "[tools]"]
    lines += [f"{json.dumps(key)} = {_toml_value(value, path)}" for key, value in merged.items()]
    content = "\n".join(lines) + "\n"
    if path.exists() and path.read_text() == content:
        return
    print(f"Recording mise tools in {path}: {', '.join(tools) or 'none yet'}", flush=True)
    if shell.check:
        print("  (check: not written)", flush=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".dev-machine-setup.")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(content)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _bundle(shell, brew, text):
    """Install missing and upgrade outdated packages with `brew bundle`."""
    return shell.run([brew, "bundle", "install", "--file=-"], input=text,
                     env=dict(shell.env, HOMEBREW_NO_AUTO_UPDATE="1"))


def _install_tools(config, shell, tools):
    """Install the tools with mise, then record them in the global fragment."""
    if not tools:
        return
    if shell.run([config["mise"], "install", *_specs(tools)]) != 0:
        raise RuntimeError("mise tools failed to install. See the mise output above.")
    record_tools(config, shell, tools)


def _rerun(config, action):
    return f"`mise run {action} --profile {config['profile']}`"


# Actions

def _packages(config, shell):
    repo = Path(config["repo_dir"])
    print(f"Selected package inventories for {config['platform']}/{config['profile']}:")
    for kind, name in (*BREWFILES.items(), *TOOL_FILES.items()):
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
    for kind in TOOL_FILES:
        if config["steps"][kind]:
            specs = _specs(tools(config, kind))
            if specs:
                print(f"\n{TOOL_FILES[kind]} tools for `mise install`: {' '.join(specs)}")
    if config["platform"] != "mac":
        print("\nGUI and App Store inventories apply only on macOS.")
    print(f"\nmise runtime fragment: {fragment_path(config)}")


def _cli(config, shell):
    brew = _require_brew(config)
    _remove_replaced_packages(config, shell, brew)
    text = brewfile(config, "cli")
    if text and _bundle(shell, brew, text) != 0:
        raise RuntimeError("CLI packages failed to install or upgrade. See the Homebrew output above.")
    _install_tools(config, shell, tools(config, "cli"))


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
    node_tools = tools(config, "node")
    _install_tools(config, shell, node_tools)
    if config["platform"] == "linux":
        for name in (".bashrc", ".zshrc"):
            ensure_block(Path(config["home"]) / name, SHELL_BLOCK,
                         [f"export PNPM_HOME={shlex.quote(str(config['pnpm_home']))}",
                          'export PATH="$PNPM_HOME/bin:$PNPM_HOME:$PATH"'], check=shell.check)
    pnpm_home = Path(config["pnpm_home"])
    if not shell.check:
        (pnpm_home / "bin").mkdir(parents=True, exist_ok=True)
    env = dict(shell.env, PNPM_HOME=str(pnpm_home),
               PATH=os.pathsep.join([str(pnpm_home / "bin"), str(pnpm_home), shell.env["PATH"]]))
    for package in config.get("pnpm_global_packages", []):
        command = [config["mise"], "exec", *_specs(node_tools), "--", "pnpm", "add", "-g", f"{package}@latest"]
        if shell.run(command, env=env) != 0:
            raise RuntimeError(f"Installing the pnpm global package {package} failed.")
    return []
