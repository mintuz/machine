"""Package inventory, software installation, runtimes, and maintenance.

Inventories live in packages/<layer>/<kind>.toml. Layers are applied in order:
shared, shared/<profile>, <platform>, <platform>/<profile>. Kinds are cli
(required), cli-optional, gui, gui-optional, and app-store; GUI and App Store
kinds apply only on macOS.

Native packages are installed by `mise bootstrap packages`, which needs no
Homebrew executable. mise tools are recorded in a machine-owned global mise
fragment, conf.d/dev-machine-setup.toml, so they work outside this checkout
without replacing the user's own mise configuration.
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
    "brew": "Homebrew formula via mise",
    "brew-cask": "Homebrew cask via mise; Homebrew-owned casks via brew",
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
        extra = [p for p in (f"{prefix}/bin", f"{prefix}/sbin") if p not in paths]
        self.env["PATH"] = os.pathsep.join([*extra, *paths])

    def run(self, argv, *, env=None, cwd="/"):
        print("$ " + shlex.join(str(part) for part in argv), flush=True)
        if self.check:
            print("  (check: not run)", flush=True)
            return 0
        try:
            return subprocess.run([str(part) for part in argv], env=env or self.env, cwd=cwd).returncode
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


def _all_inventory_files(config):
    """Every inventory file for this platform, whatever its profile."""
    inventory_files(config)
    root = Path(config["repo_dir"]) / "packages"
    layers = ["shared", config["platform"]]
    layers += [f"{layer}/{profile}" for layer in layers for profile in ("personal", "work")]
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
            allowed = {"version", "os"} | ({"name"} if key.startswith("mas:") else set())
            if set(options) - allowed:
                fail(f"{key} has unsupported options {sorted(set(options) - allowed)}")
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
                    fail(f"{key} is not supported on Linux; add os = \"macos\" and a Linux tool")
            label = f"{key} ({options['name']})" if "name" in options else key
            entries.append(Entry(kind, key, manager, name, version, frozenset(platforms), label))
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
    return _entries(config, inventory_files(config))


# Paths and helpers

def brew_prefix(config):
    return Path(config.get("brew_prefix") or BREW_PREFIX[config["platform"]])


def _brew(config):
    path = brew_prefix(config) / "bin/brew"
    return path if os.access(path, os.X_OK) else None


def fragment_path(config):
    base = os.environ.get("MISE_CONFIG_DIR")
    if not base:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(config["home"], ".config")
        base = os.path.join(xdg, "mise")
    return Path(base) / "conf.d" / FRAGMENT_NAME


def _fragment_tools(config):
    path = fragment_path(config)
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
    """Add tools to the machine-owned global mise fragment, keeping earlier entries.

    The fragment also enables cask adoption so an existing app bundle is kept
    instead of replaced, matching `brew install --cask --adopt`.
    """
    path = fragment_path(config)
    for part in (path.parent.parent, path.parent, path):
        if part.is_symlink():
            raise RuntimeError(f"Refusing to write the mise runtime fragment through symlink {part}; "
                               "it may belong to another repository.")
    existing = _fragment_tools(config)
    merged = {**existing, **tools}
    lines = [FRAGMENT_HEADER, "[bootstrap.brew]", "adopt = true", "", "[tools]"]
    lines += [f"{json.dumps(key)} = {_toml_value(value, path)}" for key, value in merged.items()]
    content = "\n".join(lines) + "\n"
    if path.exists() and path.read_text() == content:
        return
    print(f"Recording mise tools in {path}: {', '.join(tools) or 'cask adoption default'}", flush=True)
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


def _apply_packages(config, shell, keys):
    return shell.run([_mise(config), "bootstrap", "packages", "apply", "--yes", *keys])


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


def _mise_node_path(config, shell, spec):
    """Return the installed mise Node executable selected by spec, otherwise None."""
    status, output = shell.query([_mise(config), "exec", spec, "--", "node", "-p", "process.execPath"],
                                 env=dict(shell.env, **NO_AUTO_INSTALL))
    path = output.strip()
    if status != 0 or not path or path.startswith(str(brew_prefix(config)) + "/"):
        return None
    return path


def _previous_mise_node(config, shell, spec):
    """The bin directory of the mise Node in use before an install or upgrade.

    That is the installed version spec selects now, or else the newest installed
    mise Node. Check mode does not probe.
    """
    if shell.check:
        return None
    path = _mise_node_path(config, shell, spec)
    if path:
        return Path(path).parent
    status, output = shell.query([_mise(config), "ls", "--installed", "--json", "node"],
                                 env=dict(shell.env, **NO_AUTO_INSTALL))
    try:
        installs = json.loads(output) if status == 0 and output.strip() else []
    except json.JSONDecodeError:
        installs = []
    installs = [item for item in installs if isinstance(item, dict) and item.get("install_path")]
    if not installs:
        return None
    newest = max(installs, key=lambda item: _version_key(str(item.get("version", ""))))
    return Path(newest["install_path"]) / "bin"


def _npm_root(shell, bin_dir):
    """The global node_modules of the Node in bin_dir, honouring the user's npm prefix."""
    env = dict(shell.env, PATH=os.pathsep.join([str(bin_dir), shell.env["PATH"]]))
    status, output = shell.query([Path(bin_dir) / "npm", "root", "-g"], env=env)
    root = output.strip()
    return Path(root) if status == 0 and root else None


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


def _transfer_npm_globals(config, shell, previous_bin, active_bin):
    """Install npm globals from earlier Node runtimes into the active mise Node.

    Sources in precedence order: the previous mise Node, nvm's default Node,
    then Homebrew node. The first source with a package decides its version,
    and that exact version is installed. Packages already in the active runtime
    are left alone, and nothing is removed from the earlier runtimes.
    Returns the package specs that failed to install.
    """
    active_root = _npm_root(shell, active_bin)
    if not active_root:
        raise RuntimeError("Could not find the global npm directory of the mise Node runtime.")
    sources = []
    if previous_bin and Path(previous_bin).resolve() != Path(active_bin).resolve():
        root = _npm_root(shell, previous_bin)
        if root:
            sources.append((f"previous mise Node {Path(previous_bin).parent.name}", root))
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


def _switch_node(config, shell, spec, previous_bin):
    """Prove the mise Node and move npm globals to it before retiring Homebrew node.

    Raises RuntimeError when the runtime does not run or a package fails to
    move; earlier runtimes and Homebrew node are then left in place.
    """
    if shell.check:
        print("Moving npm globals to the mise Node runtime: not previewed.", flush=True)
        return
    path = _mise_node_path(config, shell, spec)
    if not path:
        raise RuntimeError("The mise Node runtime did not run after installation.")
    print(f"mise Node runtime: {path}", flush=True)
    failures = _transfer_npm_globals(config, shell, previous_bin, Path(path).parent)
    if failures:
        raise RuntimeError(f"npm global packages failed to move to the mise Node runtime: {', '.join(failures)}. "
                           "Earlier Node runtimes and Homebrew node were left in place.")
    _retire_brew_node(config, shell)


def _retire_brew_node(config, shell):
    """Unlink Homebrew's node once the mise runtime works and has the npm globals."""
    brew = _brew(config)
    if not brew or not (brew_prefix(config) / "var/homebrew/linked/node").exists():
        return
    if shell.run([brew, "unlink", "node"]) != 0:
        print("Could not unlink Homebrew node; mise Node still comes first when activated.", flush=True)


# Actions

def _packages(config, shell):
    files = inventory_files(config)
    entries = _entries(config, files)
    repo = Path(config["repo_dir"])
    print(f"Selected package inventories for {config['platform']}/{config['profile']}:")
    for path in files:
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
    entries = selected_entries(config)
    required = [entry for entry in entries if entry.kind == "cli"]
    optional = [entry for entry in entries if entry.kind == "cli-optional"]
    record_tools(config, shell, {})
    _remove_disabled_tldr(config, shell)
    packages = [entry for entry in required if not entry.is_tool]
    if _converge_packages(config, shell, packages):
        raise RuntimeError("Required CLI packages failed to install or upgrade. See the output above.")
    tools = [entry for entry in required if entry.is_tool]
    if tools:
        node = next((entry for entry in tools if entry.key == "node"), None)
        previous = _previous_mise_node(config, shell, node.spec) if node else None
        if _install_tools(config, shell, tools) != 0:
            raise RuntimeError("Required mise tools failed to install. See the mise output above.")
        if node:
            _switch_node(config, shell, node.spec, previous)
        record_tools(config, shell, {entry.key: entry.version for entry in tools})
    failures = []
    for entry in optional:
        failed = (_install_tools(config, shell, [entry]) != 0 if entry.is_tool
                  else bool(_converge_packages(config, shell, [entry])))
        if failed:
            failures.append(entry.key)
        elif entry.is_tool:
            record_tools(config, shell, {entry.key: entry.version})
    _report("Optional CLI failures", failures)


def _remove_disabled_tldr(config, shell):
    """tlrc replaces the disabled tldr formula, which also provides `tldr`."""
    if not (brew_prefix(config) / "Cellar/tldr").exists():
        return
    brew = _brew(config)
    if not brew:
        raise RuntimeError("The disabled tldr formula blocks tlrc; Homebrew is needed to uninstall it.")
    if shell.run([brew, "uninstall", "tldr"]) != 0:
        raise RuntimeError("Could not uninstall the disabled tldr formula.")


def _brew_owned_cask(config, token):
    return (brew_prefix(config) / "Caskroom" / token / ".metadata").is_dir()


def _converge_packages(config, shell, entries):
    """Install missing packages and upgrade installed ones, as `brew bundle` did.

    Casks that Homebrew already owns stay with Homebrew: they are upgraded with
    `brew upgrade --cask --greedy` when Homebrew is installed and otherwise left
    unchanged. Returns the entries that failed.
    """
    owned = [entry for entry in entries
             if entry.manager == "brew-cask" and _brew_owned_cask(config, entry.name)]
    native = [entry.key for entry in entries if entry not in owned]
    failed = []
    if native and (_apply_packages(config, shell, native) != 0 or shell.run(
            [_mise(config), "bootstrap", "packages", "upgrade", "--yes", *native]) != 0):
        failed += [entry for entry in entries if entry not in owned]
    brew = _brew(config)
    brew_env = dict(shell.env, HOMEBREW_NO_AUTO_UPDATE="1")
    for entry in owned:
        if not brew:
            print(f"Leaving Homebrew-owned cask {entry.name} unchanged: Homebrew is not installed.", flush=True)
        elif shell.run([brew, "upgrade", "--cask", "--greedy", entry.name], env=brew_env) != 0:
            failed.append(entry)
    return failed


def _gui(config, shell):
    if config["platform"] != "mac":
        print("GUI applications are installed only on macOS; skipping.")
        return
    entries = [entry for entry in selected_entries(config) if entry.kind in ("gui", "gui-optional")]
    record_tools(config, shell, {})
    failures = [failed.name for entry in entries for failed in _converge_packages(config, shell, [entry])]
    _report("GUI cask failures", failures)


def _app_store(config, shell):
    if config["platform"] != "mac":
        print("Mac App Store apps are installed only on macOS; skipping.")
        return
    entries = [entry for entry in selected_entries(config) if entry.kind == "app-store"]
    mas = shell.which("mas")
    if not mas:
        if _apply_packages(config, shell, ["brew:mas"]) != 0:
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
    previous = _previous_mise_node(config, shell, node.spec)
    if _install_tools(config, shell, [node, pnpm]) != 0:
        raise RuntimeError("Installing Node and pnpm with mise failed.")
    _switch_node(config, shell, node.spec, previous)
    record_tools(config, shell, {node.key: node.version, pnpm.key: pnpm.version})
    _write_shell_block(config, shell)
    pnpm_home = Path(config["pnpm_home"])
    if not shell.check:
        (pnpm_home / "bin").mkdir(parents=True, exist_ok=True)
    env = dict(shell.env, PNPM_HOME=str(pnpm_home),
               PATH=os.pathsep.join([str(pnpm_home / "bin"), str(pnpm_home), shell.env["PATH"]]))
    for package in config.get("pnpm_global_packages", []):
        command = [_mise(config), "exec", node.spec, pnpm.spec, "--", "pnpm", "add", "-g", f"{package}@latest"]
        if shell.run(command, env=env) != 0:
            raise RuntimeError(f"Installing the pnpm global package {package} failed.")


def _write_shell_block(config, shell):
    """Replace the Ubuntu nvm block with pnpm settings; mise activation is set up separately."""
    if config["platform"] != "linux":
        return
    pnpm_home = shlex.quote(str(config["pnpm_home"]))
    block = (f"# BEGIN {SHELL_BLOCK}\nexport PNPM_HOME={pnpm_home}\n"
             f'export PATH="$PNPM_HOME/bin:$PNPM_HOME:$PATH"\n# END {SHELL_BLOCK}\n')
    pattern = re.compile(rf"^# BEGIN {re.escape(SHELL_BLOCK)}\n.*?^# END {re.escape(SHELL_BLOCK)}\n?",
                         re.MULTILINE | re.DOTALL)
    for name in (".bashrc", ".zshrc"):
        path = Path(config["home"]) / name
        if path.is_symlink():
            print(f"Leaving {path} unchanged: it is a symlink, such as one from your dotfiles.")
            continue
        text = path.read_text() if path.exists() else ""
        if pattern.search(text):
            updated = pattern.sub(lambda _: block, text, count=1)
        else:
            updated = text + ("\n" if text and not text.endswith("\n") else "") + block
        if updated == text:
            continue
        print(f"Updating Node and pnpm shell settings in {path}", flush=True)
        if shell.check:
            continue
        created = not path.exists()
        path.write_text(updated)
        if created:
            path.chmod(0o644)


def _update(config, shell):
    results = []

    def component(name, outcome):
        results.append((name, outcome))

    def status(code):
        if shell.check:
            return "checked"
        return "completed" if code == 0 else "failed"

    brew = _brew(config)
    if brew:
        component("Homebrew metadata", status(shell.run([brew, "update"])))
        component("Homebrew formulae", status(shell.run([brew, "upgrade", "--formula"])))
        component("Homebrew casks", status(shell.run([brew, "upgrade", "--cask"])))
        component("Homebrew cleanup", status(shell.run([brew, "cleanup", "-s"])))
    else:
        for name in ("Homebrew metadata", "Homebrew formulae", "Homebrew casks", "Homebrew cleanup"):
            component(name, "skipped")

    # Homebrew already upgraded every formula in the prefix, including ones mise
    # poured, and owns its casks; mise upgrades only what Homebrew cannot.
    native = sorted({entry.key for entry in _entries(config, _all_inventory_files(config))
                     if entry.manager in ("brew", "brew-cask") and not (brew and entry.manager == "brew")
                     and not (entry.manager == "brew-cask" and _brew_owned_cask(config, entry.name))})
    if native:
        component("mise bootstrap packages", status(shell.run(
            [_mise(config), "bootstrap", "packages", "upgrade", "--yes", *native])))
    else:
        component("mise bootstrap packages", "skipped")

    tools = _fragment_tools(config)
    node_request = tools.get("node")
    if isinstance(node_request, dict):
        node_request = node_request.get("version")
    node_spec = f"node@{node_request}" if isinstance(node_request, str) else None
    if tools:
        previous = _previous_mise_node(config, shell, node_spec) if node_spec else None
        # Keep the Node being replaced until its npm globals have moved.
        component("mise tools", status(shell.run([_mise(config), "upgrade", "--no-prune", *tools])))
        if node_spec:
            try:
                _switch_node(config, shell, node_spec, previous)
                component("npm global transfer", status(0))
            except RuntimeError as error:
                print(error, flush=True)
                component("npm global transfer", "failed")
    else:
        component("mise tools", "skipped")

    pnpm_home = Path(config["pnpm_home"])
    pnpm_env = dict(shell.env, PNPM_HOME=str(pnpm_home),
                    PATH=os.pathsep.join([str(pnpm_home / "bin"), str(pnpm_home), shell.env["PATH"]]))
    for name, tool, command, env in (("npm globals", "node", ["npm", "update", "-g"], None),
                                     ("pnpm globals", "pnpm", ["pnpm", "update", "-g"], pnpm_env)):
        if tool in tools:
            component(name, status(shell.run([_mise(config), "exec", "--", *command], env=env)))
        elif shell.which(command[0]):
            component(name, status(shell.run(command, env=env)))
        else:
            component(name, "skipped")

    mas = shell.which("mas") if config["platform"] == "mac" else None
    component("Mac App Store", status(shell.run([mas, "upgrade"])) if mas else "skipped")

    component("Ollama models", _update_ollama(shell, status))

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
