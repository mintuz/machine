"""Package inventory, software installation, runtimes, and maintenance.

Inventories live in packages/<layer>/<kind>.toml. Layers are applied in order:
shared, shared/<profile>, <platform>, <platform>/<profile>. Kinds are cli
(required), cli-optional, gui, gui-optional, and app-store; GUI and App Store
kinds apply only on macOS.

Formulae and casks are installed and upgraded by Homebrew; App Store apps by
mas. mise tools (runtimes and the Linux providers of CLI casks) are recorded in
a machine-owned global mise fragment, conf.d/dev-machine-setup.toml, so they
work outside this checkout without replacing the user's own mise configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import tomllib

from .host import ensure_block

KINDS = ("cli", "cli-optional", "gui", "gui-optional", "app-store")
MAC_ONLY_KINDS = ("gui", "gui-optional", "app-store")
INVENTORY_PATH = re.compile(
    r"(shared|mac|linux)(/(personal|work))?/(cli(-optional)?|gui(-optional)?|app-store)\.toml")
PACKAGE_MANAGERS = {
    "cli": {"brew", "brew-cask"},
    "cli-optional": {"brew", "brew-cask"},
    "gui": {"brew-cask"},
    "gui-optional": {"brew-cask"},
    "app-store": {"mas"},
}
PROVIDERS = {
    "tool": "mise tool",
    "brew": "Homebrew formula",
    "brew-cask": "Homebrew cask",
    "mas": "mas",
}
MISE_OS = {"mac": "macos", "linux": "linux"}
LAYER_OS = {"shared": {"macos", "linux"}, "mac": {"macos"}, "linux": {"linux"}}
BREW_PREFIX = {"mac": "/opt/homebrew", "linux": "/home/linuxbrew/.linuxbrew"}
FRAGMENT_NAME = "dev-machine-setup.toml"
FRAGMENT_HEADER = """\
# Managed by mac-dev-machine-setup. Setup adds tools here and never removes
# them. Keep your own mise settings in config.toml or another conf.d file.
"""
SHELL_BLOCK = "dev-machine Node and pnpm"


@dataclass(frozen=True)
class Entry:
    kind: str
    key: str
    manager: str
    name: str
    version: str
    os: frozenset
    label: str
    greedy: bool = False

    @property
    def is_tool(self):
        return self.manager == "tool"

    @property
    def spec(self):
        return f"{self.key}@{self.version}"


def run(action: str, config: dict, *, check: bool = False) -> None:
    """Run one software action. check=True prints commands without running them."""
    handlers = {
        "packages": _packages,
        "cli": _cli,
        "gui": _gui,
        "app-store": _app_store,
        "node": _node,
        "update": _update,
    }
    if action not in handlers:
        raise RuntimeError(f"Unknown software action: {action}")
    if config.get("platform") not in MISE_OS or config.get("profile") not in ("personal", "work"):
        raise RuntimeError("Software setup needs platform mac|linux and profile personal|work.")
    handlers[action](config, _Shell(config, check))


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

def inventory_files(config):
    """Validate every inventory path and return the selected files in apply order."""
    root = Path(config["repo_dir"]) / "packages"
    for path in sorted(root.rglob("*")):
        if path.name.startswith(".") or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not INVENTORY_PATH.fullmatch(relative):
            raise RuntimeError(f"Invalid package inventory: packages/{relative}. "
                               "Check the layer, profile, and file name.")
    if not (root / "shared/cli.toml").is_file():
        raise RuntimeError("Missing shared CLI inventory: packages/shared/cli.toml")
    platform, profile = config["platform"], config["profile"]
    layers = ("shared", f"shared/{profile}", platform, f"{platform}/{profile}")
    return [root / layer / f"{kind}.toml" for layer in layers for kind in KINDS
            if (root / layer / f"{kind}.toml").is_file()]


def _parse(path, repo_dir):
    relative = path.relative_to(Path(repo_dir)).as_posix()
    kind = path.stem
    layer_os = LAYER_OS[path.relative_to(Path(repo_dir) / "packages").parts[0]]

    def fail(message):
        raise RuntimeError(f"Malformed package inventory {relative}: {message}")

    try:
        data = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        fail(str(error))
    allowed_sections = {"packages"} if kind in MAC_ONLY_KINDS else {"packages", "tools"}
    if set(data) - allowed_sections:
        fail(f"unexpected sections {sorted(set(data) - allowed_sections)}")
    entries = []
    for section in ("packages", "tools"):
        table = data.get(section, {})
        if not isinstance(table, dict):
            fail(f"[{section}] must be a table")
        for key, value in table.items():
            options = {"version": value} if isinstance(value, str) else value
            if not isinstance(options, dict):
                fail(f"{key} must be a version string or table")
            allowed = {"version", "os"}
            allowed |= {"name"} if key.startswith("mas:") else set()
            allowed |= {"greedy"} if key.startswith("brew-cask:") else set()
            if set(options) - allowed:
                fail(f"{key} has unsupported options {sorted(set(options) - allowed)}")
            if not isinstance(options.get("greedy", False), bool):
                fail(f"{key} greedy must be true or false")
            version = options.get("version", "latest")
            selector = options.get("os")
            if not isinstance(version, str) or not version:
                fail(f"{key} needs a version string")
            if selector is not None and selector not in ("macos", "linux"):
                fail(f"{key} has os {selector!r}; use macos or linux")
            platforms = layer_os & ({selector} if selector else layer_os)
            if not platforms:
                fail(f"{key} never applies in this layer")
            if section == "tools":
                manager, name = "tool", key
            else:
                manager, separator, name = key.partition(":")
                if not separator or not name:
                    fail(f"{key} must be named manager:package")
                if manager not in PACKAGE_MANAGERS[kind]:
                    fail(f"{key} uses {manager}, which is not allowed in {kind} inventories")
                if version != "latest":
                    fail(f"{key} cannot be pinned; {manager} installs only the current version")
                if manager == "mas" and not name.isdigit():
                    fail(f"{key} needs a numeric App Store ID")
                if (manager == "brew-cask" and kind not in MAC_ONLY_KINDS and "linux" in platforms
                        and not name.startswith("font-")):
                    fail(f"{key}: casks other than fonts are macOS-only; add os = \"macos\" and a Linux tool")
            label = f"{key} ({options['name']})" if "name" in options else key
            entries.append(Entry(kind, key, manager, name, version, frozenset(platforms), label,
                                 options.get("greedy", False)))
    return entries


def _entries(config, files):
    target = MISE_OS[config["platform"]]
    entries = []
    for path in files:
        for entry in _parse(path, config["repo_dir"]):
            if target in entry.os and (config["platform"] == "mac" or entry.kind not in MAC_ONLY_KINDS):
                entries.append(entry)
    return entries


def selected_entries(config):
    return [entry for entry in _entries(config, inventory_files(config))
            if config["steps"][_owner(entry)]]


def _owner(entry):
    if entry.is_tool and (entry.key in ("node", "pnpm") or entry.key.startswith("npm:")):
        return "node"
    return {"cli-optional": "cli", "gui-optional": "gui"}.get(entry.kind, entry.kind)


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


def _mise(config):
    return config["mise"]


def _brewfile(entries):
    """Declare native packages with item-level trust for qualified names."""
    lines = []
    for entry in entries:
        parts = entry.name.split("/")
        if len(parts) == 3:
            tap = f"tap {json.dumps('/'.join(parts[:2]))}"
            if tap not in lines:
                lines.append(tap)
        kind = "brew" if entry.manager == "brew" else "cask"
        line = f"{kind} {json.dumps(entry.name)}"
        if len(parts) == 3:
            line += ", trusted: true"
        if entry.manager == "brew-cask" and entry.greedy:
            line += ", greedy: true"
        lines.append(line)
    return "".join(line + "\n" for line in lines)


def _bundle(shell, brew, entries):
    """Install missing and upgrade outdated packages with `brew bundle`, as before."""
    return shell.run([brew, "bundle", "install", "--file=-"], input=_brewfile(entries),
                     env=dict(shell.env, HOMEBREW_NO_AUTO_UPDATE="1"))


def _install_tools(config, shell, entries):
    return shell.run([_mise(config), "install", *(entry.spec for entry in entries)])


def _report(title, failures):
    if failures:
        print(f"{title}: {', '.join(failures)}. See the errors above.", flush=True)


def _runtime_entries(config):
    tools = {entry.key: entry for entry in selected_entries(config)
             if entry.kind == "cli" and entry.is_tool}
    missing = [name for name in ("node", "pnpm") if name not in tools]
    if missing:
        raise RuntimeError(f"The required CLI inventories must declare mise tools: {', '.join(missing)}")
    return tools["node"], tools["pnpm"]


# Probes must never install a missing Node as a side effect.
NO_AUTO_INSTALL = {"MISE_AUTO_INSTALL": "0", "MISE_EXEC_AUTO_INSTALL": "0",
                   "MISE_NOT_FOUND_AUTO_INSTALL": "0"}


def _version_key(text):
    return tuple(int(part) for part in re.findall(r"\d+", text))


def _installed_mise_nodes(config, shell):
    """Inspect registered installs, never treating PATH fallbacks as mise runtimes."""
    status, output = shell.query([_mise(config), "ls", "--installed", "--json", "node"],
                                 env=dict(shell.env, **NO_AUTO_INSTALL))
    try:
        if status != 0:
            raise ValueError("mise ls failed")
        installs = json.loads(output)
        if not isinstance(installs, list):
            raise ValueError("expected a list of installed Node runtimes")
        nodes = {}
        for item in installs:
            if (not isinstance(item, dict) or not isinstance(item.get("version"), str)
                    or not item["version"] or not isinstance(item.get("install_path"), str)
                    or not Path(item["install_path"]).is_absolute()):
                raise ValueError("invalid installed Node metadata")
            executable = Path(item["install_path"]) / "bin/node"
            if executable.is_file() and os.access(executable, os.X_OK):
                nodes[executable] = item["version"]
        return nodes
    except (ValueError, OSError) as error:
        raise RuntimeError(f"Could not inspect installed mise Node runtimes: {error}") from error


def _mise_node_path(config, shell, spec, installs=None):
    """Return the registered mise Node executable selected by spec, otherwise None."""
    if installs is None:
        installs = _installed_mise_nodes(config, shell)
    status, output = shell.query([_mise(config), "exec", spec, "--", "node", "-p", "process.execPath"],
                                 env=dict(shell.env, **NO_AUTO_INSTALL))
    path = output.strip()
    if status != 0 or not path:
        return None
    executable = Path(path).resolve()
    return next((str(installed) for installed in installs if installed.resolve() == executable), None)


def _previous_mise_node(config, shell, spec):
    """The installed Node selected before an install, falling back to installed versions."""
    if shell.check:
        return None
    installs = _installed_mise_nodes(config, shell)
    if not installs:
        return None
    path = _mise_node_path(config, shell, spec, installs)
    if path:
        return Path(path).parent
    return max(installs, key=lambda path: _version_key(installs[path])).parent


def _npm_root(shell, bin_dir):
    """The global node_modules of the Node in bin_dir, honouring the user's npm prefix."""
    env = dict(shell.env, PATH=os.pathsep.join([str(bin_dir), shell.env["PATH"]]))
    status, output = shell.query([Path(bin_dir) / "npm", "root", "-g"], env=env)
    root = output.strip()
    return Path(root) if status == 0 and root else None


def _node_state_path(config):
    path = fragment_path(config).with_suffix(".node.json")
    _guard_fragment_path(path)
    return path


def _node_state(config):
    path = _node_state_path(config)
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text())
        if (not isinstance(state, dict) or not isinstance(state.get("selector"), str)
                or set(state) - {"selector", "source", "legacy", "target"}
                or ("source" in state) != ("legacy" in state)
                or ("source" in state and state["source"] is not None
                    and not isinstance(state["source"], str))
                or ("legacy" in state and not isinstance(state["legacy"], bool))
                or ("target" in state and not isinstance(state["target"], str))):
            raise ValueError("invalid Node migration state")
        return state
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Cannot read Node migration state {path}: {error}") from error


def _save_node_state(config, shell, state):
    path = _node_state_path(config)
    if shell.check:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".node-migration.")
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(state, stream)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _begin_node_transfer(config, shell, selector):
    """Keep one original source across retries, even if the requested target changes."""
    state = _node_state(config)
    tools = _fragment_tools(config)
    value = tools.get("node")
    version = value.get("version") if isinstance(value, dict) else value
    if state.get("target") == version and version is not None:
        # The fragment committed but clearing the pending journal was interrupted.
        state = {"selector": state["selector"]}
    if "source" not in state:
        previous = _previous_mise_node(config, shell, f"node@{version}" if version else "node")
        state = {"selector": selector, "source": str(previous) if previous else None,
                 "legacy": "node" not in tools}
    else:
        if state["source"]:
            source = (Path(state["source"]) / "node").resolve()
            if not any(installed.resolve() == source for installed in _installed_mise_nodes(config, shell)):
                raise RuntimeError(f"Previous mise Node runtime {state['source']} is no longer installed. "
                                   "Restore it before retrying; the migration journal was preserved.")
        state["selector"] = selector
        state.pop("target", None)
    _save_node_state(config, shell, state)
    previous = Path(state["source"]) if state["source"] else None
    if previous and "node" in tools:
        # A floating selector would switch as soon as installation finishes.
        record_tools(config, shell, {"node": previous.parent.name})
    return previous, state["legacy"]


def _commit_node_transfer(config, shell, selector, version, tools):
    # Journal the proven target before the atomic fragment write. On restart a
    # matching pin means transfer completed, even if clearing this journal failed.
    state = _node_state(config)
    _save_node_state(config, shell, {**state, "selector": selector, "target": version})
    record_tools(config, shell, {**tools, "node": version})
    _save_node_state(config, shell, {"selector": selector})
    if not shell.check:
        selected = _mise_node_path(config, shell, "node")
        expected = _mise_node_path(config, shell, f"node@{version}")
        if not selected or not expected or Path(selected).resolve() != Path(expected).resolve():
            raise RuntimeError("Another mise configuration overrides the managed Node selection. "
                               "Resolve that configuration before retiring the previous Node provider.")


def _npm_globals(root):
    """Map each package in a global node_modules to its version.

    Linked or unreadable packages map to None because they cannot be reinstalled
    at a known version.
    """
    found = {}
    if not root or not root.is_dir():
        return found
    for item in sorted(root.iterdir()):
        if item.name.startswith("."):
            continue
        scoped = item.name.startswith("@") and item.is_dir() and not item.is_symlink()
        for package in (sorted(item.iterdir()) if scoped else [item]):
            name = package.relative_to(root).as_posix()
            if name in ("npm", "corepack"):
                continue
            version = None
            if not package.is_symlink():
                try:
                    version = json.loads((package / "package.json").read_text()).get("version")
                except (OSError, ValueError, AttributeError):
                    version = None
            found[name] = version if isinstance(version, str) and version else None
    return found


def _nvm_default(config):
    """Return (bin dir, description, other versions) for nvm's default Node.

    The default alias is followed through nvm's alias files, for example
    default -> lts/* -> lts/jod -> v22.1.0. If it does not resolve, the newest
    installed version is used and the description says so.
    """
    nvm = Path(config["home"]) / ".nvm"
    versions = sorted((path for path in (nvm / "versions/node").glob("v*") if path.is_dir()),
                      key=lambda path: _version_key(path.name))
    if not versions:
        return None, "", []
    chain, value = [], "default"
    for _ in range(8):
        alias = nvm / "alias" / value
        if not alias.is_file():
            break
        value = alias.read_text().strip()
        chain.append(value)
    wanted = value.removeprefix("v")
    if wanted in ("node", "stable"):
        matches = versions
    else:
        matches = [path for path in versions
                   if path.name[1:] == wanted or path.name[1:].startswith(wanted + ".")]
    if chain and matches:
        chosen, how = matches[-1], "default alias " + " -> ".join(["default", *chain])
    else:
        chosen, how = versions[-1], "newest installed; the default alias did not resolve"
    others = [path.name for path in versions if path != chosen]
    return chosen / "bin", f"nvm {chosen.name} ({how})", others


def _transfer_npm_globals(config, shell, previous_bin, active_bin, legacy):
    """Install npm globals from earlier Node runtimes into the active mise Node.

    Sources in precedence order: the previous mise Node, nvm's default Node,
    then Homebrew node. The first source with a package decides its version,
    and that exact version is installed. Packages already in the active runtime
    are left alone, and nothing is removed from the earlier runtimes.
    Legacy providers are read only before the machine fragment takes ownership
    of Node. Later runs must not restore packages that the user uninstalled.
    Returns the package specs that failed to install.
    """
    active_root = _npm_root(shell, active_bin)
    if not active_root:
        raise RuntimeError("Could not find the global npm directory of the mise Node runtime.")
    sources = []
    nvm_others = []
    if previous_bin and Path(previous_bin).resolve() != Path(active_bin).resolve():
        root = _npm_root(shell, previous_bin)
        if not root:
            raise RuntimeError(f"Could not inspect npm globals of previous Node runtime {previous_bin}.")
        sources.append((f"previous mise Node {Path(previous_bin).parent.name}", root))
    if legacy:
        nvm_bin, nvm_label, nvm_others = _nvm_default(config)
        if nvm_bin:
            sources.append((nvm_label, nvm_bin.parent / "lib/node_modules"))
        if (brew_prefix(config) / "Cellar/node").is_dir():
            sources.append(("Homebrew node", brew_prefix(config) / "lib/node_modules"))
    current = _npm_globals(active_root)
    chosen = {}
    for label, root in sources:
        if root.resolve() == active_root.resolve():
            continue
        for name, version in _npm_globals(root).items():
            if name not in chosen:
                chosen[name] = (version, label)
            elif chosen[name][0] != version:
                print(f"npm global {name}: using {chosen[name][0]} from {chosen[name][1]}, "
                      f"not {version} from {label}.", flush=True)
    if nvm_others:
        print(f"npm globals of other nvm versions are not moved: {', '.join(nvm_others)}", flush=True)
    env = dict(shell.env, PATH=os.pathsep.join([str(active_bin), shell.env["PATH"]]))
    failures = []
    for name, (version, label) in chosen.items():
        if name in current:
            continue
        if version is None:
            print(f"Not moving npm global {name} from {label}: it is linked or has no readable version.",
                  flush=True)
            continue
        print(f"Moving npm global {name}@{version} from {label} to the mise Node runtime.", flush=True)
        if shell.run([Path(active_bin) / "npm", "install", "-g", f"{name}@{version}"], env=env) != 0:
            failures.append(f"{name}@{version}")
    return failures


def _prepare_node(config, shell, spec, previous_bin, legacy):
    """Prove the mise Node and move npm globals before committing its configuration.

    Raises RuntimeError when the runtime does not run or a package fails to
    move. The caller must record the working default before retiring Homebrew.
    """
    if shell.check:
        print("Moving npm globals to the mise Node runtime: not previewed.", flush=True)
        return spec.partition("@")[2]
    path = _mise_node_path(config, shell, spec)
    if not path:
        raise RuntimeError("The mise Node runtime did not run after installation.")
    print(f"mise Node runtime: {path}", flush=True)
    failures = _transfer_npm_globals(config, shell, previous_bin, Path(path).parent, legacy)
    if failures:
        raise RuntimeError(f"npm global packages failed to move to the mise Node runtime: {', '.join(failures)}. "
                           "Earlier Node runtimes and Homebrew node were left in place.")
    return Path(path).parent.parent.name


def _retire_brew_node(config, shell):
    """Unlink Homebrew's node after its working replacement and globals are configured."""
    brew = _brew(config)
    if not brew or not (brew_prefix(config) / "var/homebrew/linked/node").exists():
        return
    if shell.run([brew, "unlink", "node"]) != 0:
        print("Could not unlink Homebrew node; mise Node still comes first when activated.", flush=True)


# Actions

def _packages(config, shell):
    files = inventory_files(config)
    entries = selected_entries(config)
    repo = Path(config["repo_dir"])
    print(f"Selected package inventories for {config['platform']}/{config['profile']}:")
    for path in files:
        if any(config["steps"][_owner(entry)] for entry in _entries(config, [path])):
            print(f"  {path.relative_to(repo).as_posix()}")
    titles = {"cli": "Required CLI", "cli-optional": "Optional CLI", "gui": "GUI applications",
              "gui-optional": "Optional GUI applications", "app-store": "Mac App Store"}
    for kind in KINDS:
        chosen = [entry for entry in entries if entry.kind == kind]
        if chosen:
            print(f"{titles[kind]} ({len(chosen)}):")
            for entry in chosen:
                provider = PROVIDERS[entry.manager] + (f" {entry.version}" if entry.is_tool else "")
                print(f"  {entry.label} [{provider}]")
    if config["platform"] != "mac":
        print("GUI and App Store inventories apply only on macOS.")
    print(f"mise runtime fragment: {fragment_path(config)}")


def _cli(config, shell):
    entries = [entry for entry in selected_entries(config) if _owner(entry) == "cli"]
    required = [entry for entry in entries if entry.kind == "cli"]
    optional = [entry for entry in entries if entry.kind == "cli-optional"]
    brew = _require_brew(config)
    _remove_disabled_tldr(config, shell, brew)
    packages = [entry for entry in required if not entry.is_tool]
    if packages and _bundle(shell, brew, packages) != 0:
        raise RuntimeError("Required CLI packages failed to install or upgrade. See the output above.")
    tools = [entry for entry in required if entry.is_tool]
    if tools:
        if _install_tools(config, shell, tools) != 0:
            raise RuntimeError("Required mise tools failed to install. See the mise output above.")
        record_tools(config, shell, {entry.key: entry.version for entry in tools})
    failures = []
    for entry in optional:
        failed = (_install_tools(config, shell, [entry]) != 0 if entry.is_tool
                  else _bundle(shell, brew, [entry]) != 0)
        if failed:
            failures.append(entry.key)
        elif entry.is_tool:
            record_tools(config, shell, {entry.key: entry.version})
    _report("Optional CLI failures", failures)


def _remove_disabled_tldr(config, shell, brew):
    """tlrc replaces the disabled tldr formula, which also provides `tldr`."""
    if (brew_prefix(config) / "Cellar/tldr").exists() and shell.run([brew, "uninstall", "tldr"]) != 0:
        raise RuntimeError("Could not uninstall the disabled tldr formula.")


def _gui(config, shell):
    if config["platform"] != "mac":
        print("GUI applications are installed only on macOS; skipping.")
        return
    entries = [entry for entry in selected_entries(config) if entry.kind in ("gui", "gui-optional")]
    brew = _require_brew(config)
    env = dict(shell.env, HOMEBREW_NO_AUTO_UPDATE="1")
    failures = []
    for entry in entries:
        installed, _ = shell.query([brew, "list", "--cask", entry.name], env=env)
        command = (["upgrade", "--cask", "--greedy"] if installed == 0 else ["install", "--cask", "--adopt"])
        if shell.run([brew, *command, entry.name], env=env) != 0:
            failures.append(entry.name)
    _report("GUI cask failures", failures)


def _app_store(config, shell):
    if config["platform"] != "mac":
        print("Mac App Store apps are installed only on macOS; skipping.")
        return
    entries = [entry for entry in selected_entries(config) if entry.kind == "app-store"]
    mas = shell.which("mas")
    if not mas:
        brew = _require_brew(config)
        if shell.run([brew, "install", "mas"], env=dict(shell.env, HOMEBREW_NO_AUTO_UPDATE="1")) != 0:
            raise RuntimeError("Could not install the mas CLI needed for App Store apps.")
        mas = shell.which("mas") or str(brew_prefix(config) / "bin/mas")
    shell.run(["mdimport", "/Applications"])
    sudo = ["sudo", "-A"] if shell.env.get("SUDO_ASKPASS") else ["sudo"]
    failures = []
    for entry in entries:
        if shell.run([*sudo, mas, "get", entry.name]) != 0:
            if shell.run([*sudo, mas, "install", entry.name]) != 0:
                failures.append(entry.label)
    _report("App Store installation failures", failures)


def _node(config, shell):
    node, pnpm = _runtime_entries(config)
    previous, legacy = _begin_node_transfer(config, shell, node.version)
    if _install_tools(config, shell, [node, pnpm]) != 0:
        raise RuntimeError("Installing Node and pnpm with mise failed.")
    version = _prepare_node(config, shell, node.spec, previous, legacy)
    _commit_node_transfer(config, shell, node.version, version, {pnpm.key: pnpm.version})
    providers = [entry for entry in selected_entries(config) if entry.key.startswith("npm:")]
    required = [entry for entry in providers if entry.kind == "cli"]
    if required:
        if _install_tools(config, shell, required) != 0:
            raise RuntimeError("Required npm-backed mise tools failed to install.")
        record_tools(config, shell, {entry.key: entry.version for entry in required})
    failures = []
    for entry in providers:
        if entry.kind != "cli-optional":
            continue
        if _install_tools(config, shell, [entry]) != 0:
            failures.append(entry.key)
        else:
            record_tools(config, shell, {entry.key: entry.version})
    _report("Optional npm-backed CLI failures", failures)
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
        command = [_mise(config), "exec", f"node@{version}", pnpm.spec, "--", "pnpm", "add", "-g", f"{package}@latest"]
        if shell.run(command, env=env) != 0:
            raise RuntimeError(f"Installing the pnpm global package {package} failed.")
    _retire_brew_node(config, shell)


def _outdated_casks(shell, brew, env):
    code, output = shell.query([brew, "outdated", "--cask", "--json=v2"], env=env)
    if code != 0:
        raise RuntimeError("Could not query outdated Homebrew casks.")
    try:
        casks = json.loads(output)["casks"]
        if not isinstance(casks, list) or any(
                not isinstance(cask, dict) or not isinstance(cask.get("name"), str)
                or not cask["name"] or not isinstance(cask.get("pinned", False), bool)
                for cask in casks):
            raise ValueError("invalid cask metadata")
        return [cask["name"] for cask in casks if not cask.get("pinned", False)]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("Invalid outdated Homebrew cask metadata.") from error


def _update(config, shell):
    results = []

    def component(name, outcome):
        results.append((name, outcome))

    def status(code):
        if shell.check:
            return "checked"
        return "completed" if code == 0 else "failed"

    steps = config["steps"]
    inventory_files(config)
    brew = _brew(config)
    brew_env = dict(shell.env, HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_INSTALL_CLEANUP="1",
                    HOMEBREW_NO_AUTOREMOVE="1")
    if brew and (steps["cli"] or steps["gui"]):
        component("Homebrew metadata", status(shell.run([brew, "update"])))
        cleanup = []
        excluded_cleanup = set()
        cleanup_safe = True
        unrestricted = steps["cli"] and steps["gui"]
        cli_casks = {entry.name.rsplit("/", 1)[-1]
                     for path in (Path(config["repo_dir"]) / "packages").rglob("*.toml")
                     for entry in _parse(path, config["repo_dir"])
                     if entry.kind in ("cli", "cli-optional") and entry.manager == "brew-cask"}
        for flag, name, enabled in (("--formula", "Homebrew formulae", steps["cli"]),
                                    ("--cask", "Homebrew casks",
                                     config["platform"] == "mac" and (steps["cli"] or steps["gui"]))):
            if not enabled:
                component(name, "skipped")
                if flag == "--formula" and config["platform"] == "mac":
                    code, output = shell.query([brew, "list", flag], env=brew_env)
                    cleanup_safe = code == 0
                    excluded_cleanup.update(output.split())
                continue
            code, output = shell.query([brew, "list", flag], env=brew_env)
            if code != 0:
                component(name, "failed")
                cleanup_safe = False
                continue
            installed = output.split()
            if flag == "--cask":
                excluded_cleanup.update(item for item in installed
                                        if not steps["cli" if item in cli_casks else "gui"])
                installed = [item for item in installed
                             if steps["cli" if item in cli_casks else "gui"]]
            cleanup.extend(installed)
            if flag == "--cask" and not unrestricted:
                try:
                    eligible = _outdated_casks(shell, brew, brew_env)
                except RuntimeError as error:
                    print(error, flush=True)
                    component(name, "failed")
                    continue
                # Named upgrades are implicitly greedy; let Homebrew's ordinary
                # outdated query apply auto-update/latest and user greedy settings.
                selected = set(installed)
                eligible = [item for item in eligible if item in selected]
                component(name, status(shell.run([brew, "upgrade", flag, *eligible], env=brew_env))
                          if eligible else "skipped")
            else:
                # Bare upgrades skip pinned and unavailable packages normally.
                component(name, status(shell.run([brew, "upgrade", flag], env=brew_env)))
        # Named cleanup resolves both a formula and a cask with the same token.
        # Leave ambiguous tokens alone rather than clean an excluded installation.
        cleanup = [item for item in dict.fromkeys(cleanup) if item not in excluded_cleanup]
        component("Homebrew cleanup",
                  (status(shell.run([brew, "cleanup", "-s",
                                     *([] if unrestricted else cleanup)], env=brew_env))
                   if unrestricted or cleanup else "skipped") if cleanup_safe else "failed")
    else:
        for name in ("Homebrew metadata", "Homebrew formulae", "Homebrew casks", "Homebrew cleanup"):
            component(name, "skipped")

    tools = {}
    node_ready = steps["node"]
    try:
        if steps["cli"] or steps["node"]:
            tools = {key: value for key, value in _fragment_tools(config).items()
                     if steps["node" if key in ("node", "pnpm") or key.startswith("npm:") else "cli"]}
    except (RuntimeError, OSError) as error:
        print(error, flush=True)
        component("mise configuration", "failed")
        node_ready = False
    cli_tools = [key for key in tools if key not in ("node", "pnpm") and not key.startswith("npm:")]
    component("mise tools",
              status(shell.run([_mise(config), "upgrade", "--no-prune", *cli_tools]))
              if cli_tools else "skipped")
    if "node" in tools:
        try:
            value = tools["node"]
            request = value.get("version") if isinstance(value, dict) else value
            selector = _node_state(config).get("selector", request)
            previous, legacy = _begin_node_transfer(config, shell, selector)
            # install never rewrites the pinned fragment or prunes the source runtime.
            if shell.run([_mise(config), "install", f"node@{selector}"]) != 0:
                raise RuntimeError("Installing the updated Node runtime failed.")
            version = _prepare_node(config, shell, f"node@{selector}", previous, legacy)
            _commit_node_transfer(config, shell, selector, version, {})
            _retire_brew_node(config, shell)
            component("npm global transfer", status(0))
        except (RuntimeError, OSError) as error:
            print(error, flush=True)
            component("npm global transfer", "failed")
            node_ready = False
    node_tools = [key for key in tools if key == "pnpm" or key.startswith("npm:")]
    component("Node ecosystem tools",
              status(shell.run([_mise(config), "upgrade", "--no-prune", *node_tools],
                               env=dict(shell.env, **NO_AUTO_INSTALL)))
              if node_ready and node_tools else "skipped")

    pnpm_home = Path(config["pnpm_home"])
    pnpm_env = dict(shell.env, PNPM_HOME=str(pnpm_home), **NO_AUTO_INSTALL,
                    PATH=os.pathsep.join([str(pnpm_home / "bin"), str(pnpm_home), shell.env["PATH"]]))
    for name, tool, command, env in (("npm globals", "node", ["npm", "update", "-g"],
                                     dict(shell.env, **NO_AUTO_INSTALL)),
                                    ("pnpm globals", "pnpm", ["pnpm", "update", "-g"], pnpm_env)):
        if not node_ready:
            component(name, "skipped")
        elif tool in tools:
            component(name, status(shell.run([_mise(config), "exec", "--", *command], env=env)))
        elif shell.which(command[0]):
            component(name, status(shell.run(command, env=env)))
        else:
            component(name, "skipped")

    mas = shell.which("mas") if steps["app-store"] and config["platform"] == "mac" else None
    component("Mac App Store", status(shell.run([mas, "upgrade"])) if mas else "skipped")
    component("Ollama models", _update_ollama(shell, status) if steps["cli"] else "skipped")

    print("Update summary:")
    for name, outcome in results:
        print(f"  {name}: {outcome}")
    failed = [name for name, outcome in results if outcome == "failed"]
    if failed:
        message = f"Update failures: {', '.join(failed)}. See the errors above."
        print(message, flush=True)
        raise RuntimeError(message)


def _update_ollama(shell, status):
    ollama = shell.which("ollama")
    if not ollama:
        return "skipped"
    code, output = shell.query([ollama, "list"])
    if code != 0:
        print("ollama list failed.", flush=True)
        return "failed"
    models = [line.split()[0] for line in output.splitlines()[1:] if line.strip()]
    if not models:
        return "skipped"
    for model in models:
        code = shell.run([ollama, "pull", model])
        if code != 0:
            return "failed"
    return status(0)
