#!/usr/bin/env python3
"""Check package selection, installs, runtimes, and updates with fake tools.

Nothing is installed: mise, Homebrew, mas, sudo, npm, pnpm, and Ollama are
replaced by logging stand-ins in temporary directories.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import shutil
import tempfile
import tomllib

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from devsetup import software  # noqa: E402

FAKE = """#!/bin/sh
line="{name} $*"
{pre}
printf '%s\\n' "$line" >> "$FAKE_LOG"
IFS='|'
for pattern in $FAKE_FAIL; do
  case "$line" in *"$pattern"*) exit 1 ;; esac
done
unset IFS
{extra}
exit 0
"""
# brew bundle logs its Brewfile from stdin on the same line, joined by "; ".
BREW_PRE = """[ "$1" = bundle ] && line="$line: $(sed 's/$/;/' | tr '\\n' ' ')"
if [ -n "$FAKE_BREW_STATE" ]; then
  "$FAKE_PYTHON" - "$@" <<'PY'
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
command = args[0]
if command not in ("update", "list", "outdated", "upgrade", "cleanup"):
    sys.exit(99)
line = "brew " + " ".join(args)
with open(os.environ["FAKE_LOG"], "a") as log:
    print(line, file=log)
if any(pattern in line for pattern in os.environ.get("FAKE_FAIL", "").split("|") if pattern):
    sys.exit(1)
path = Path(os.environ["FAKE_BREW_STATE"])
state = json.loads(path.read_text())
if command == "update":
    state["refreshes"] = state.get("refreshes", 0) + 1
else:
    # Model the implicit effects as state changes so missing suppression is visible.
    if os.environ.get("HOMEBREW_NO_AUTO_UPDATE") != "1":
        state["refreshes"] = state.get("refreshes", 0) + 1
    group = "formulae" if "--formula" in args else "casks"
    packages = state[group]
    names = [arg for arg in args[1:] if not arg.startswith("-")]
    greedy = os.environ.get("HOMEBREW_UPGRADE_GREEDY_CASKS", "").split()

    def eligible(name, package, named=False):
        return (package.get("available", True) and package["version"] != package["current"]
                and (group == "formulae" or named or name in greedy
                     or not (package.get("auto_updates") or package["current"] == "latest")))

    if command == "list":
        print("\\n".join(packages))
    elif command == "outdated":
        if os.environ.get("FAKE_BREW_BAD_JSON"):
            print("{}")
        else:
            print(json.dumps({"formulae": [], "casks": [
                {"name": name, "installed_versions": [package["version"]],
                 "current_version": package["current"], "pinned": package.get("pinned", False)}
                for name, package in packages.items() if eligible(name, package)]}))
    elif command == "upgrade":
        for name in names:
            if name not in packages or not packages[name].get("available", True) or packages[name].get("pinned"):
                sys.exit(1)
        for name in names or packages:
            package = packages[name]
            if not package.get("pinned") and eligible(name, package, bool(names)):
                package["version"] = package["current"]
        if os.environ.get("HOMEBREW_NO_INSTALL_CLEANUP") != "1":
            for installed in (state["formulae"], state["casks"]):
                for package in installed.values():
                    package["cleaned"] = True
    elif command == "cleanup":
        # Homebrew resolves both kinds for each name and ignores unavailable ones.
        for installed in (state["formulae"], state["casks"]):
            for name, package in installed.items():
                if (not names or name in names) and package.get("available", True):
                    package["cleaned"] = True
        if os.environ.get("HOMEBREW_NO_AUTOREMOVE") != "1":
            state["formulae"].pop("unused-dependency", None)
path.write_text(json.dumps(state))
PY
  status=$?
  [ "$status" -eq 99 ] || exit "$status"
fi
if [ "$1" = outdated ]; then
  printf '%s\\n' "$line" >> "$FAKE_LOG"
  printf '{"formulae": [], "casks": []}\\n'
  exit 0
fi
if [ "$1" = list ]; then
  printf '%s\\n' "$line" >> "$FAKE_LOG"
  if [ -z "$3" ]; then
    if [ "$2" = --formula ]; then printf '%s\\n' "$FAKE_BREW_FORMULAE"; else printf '%s\\n' "$FAKE_BREW_CASKS"; fi
    exit 0
  fi
  if [ "$2" = --formula ]; then [ -d "$FAKE_PREFIX/Cellar/$3" ]; else [ -d "$FAKE_PREFIX/Caskroom/$3" ]; fi
  exit $?
fi
if [ "$1" = unlink ] && [ "$2" = node ]; then rm -rf "$FAKE_PREFIX/var/homebrew/linked/node"; fi"""
# Resolve the managed pin and registered installs; unresolved selectors fall back
# to PATH. A prepared FAKE_NODE_AFTER runtime is registered only on installation.
MISE_EXTRA = """exec "$FAKE_PYTHON" - "$@" <<'PY'
import json
import os
from pathlib import Path
import re
import sys
import tomllib

args = sys.argv[1:]
registry = Path(os.environ["FAKE_NODE_REGISTRY"])
installs = json.loads(registry.read_text())
selected = Path(os.environ["FAKE_NODE_FILE"])
if args == ["ls", "--installed", "--json", "node"]:
    print(os.environ.get("FAKE_NODE_INSTALLS", json.dumps(installs)))
elif args and args[0] in ("install", "upgrade") and any(
        spec == "node" or spec.startswith("node@") for spec in args[1:]):
    target = os.environ.get("FAKE_NODE_AFTER")
    if target:
        install = Path(target).parent.parent
        installs = [item for item in installs if item["install_path"] != str(install)]
        installs.append({"version": install.name, "install_path": str(install)})
        registry.write_text(json.dumps(installs))
        selected.write_text(target)
elif args[-3:] == ["node", "-p", "process.execPath"]:
    spec = args[1]
    version = spec.removeprefix("node@") if spec != "node" else None
    override = os.environ.get("FAKE_NODE_OVERRIDE") if spec == "node" else None
    fragment = Path(os.environ["FAKE_NODE_FRAGMENT"])
    if spec == "node" and fragment.exists():
        value = tomllib.loads(fragment.read_text()).get("tools", {}).get("node")
        version = value.get("version") if isinstance(value, dict) else value
    matches = [item for item in installs if version and (
        version in ("lts", "latest") or item["version"] == version
        or item["version"].startswith(version + "."))]
    if override:
        path = override
    elif matches:
        newest = max(matches, key=lambda item: tuple(map(int, re.findall(r"[0-9]+", item["version"]))))
        path = str(Path(newest["install_path"]) / "bin/node")
    else:
        path = selected.read_text().strip() if selected.exists() else ""
    if not path:
        sys.exit(1)
    print(path)
PY"""
# npm inside a fake Node runtime: its global root is the runtime's own
# lib/node_modules unless $FAKE_NPM_PREFIX is set, and install -g creates the package.
FAKE_NPM = """#!/bin/sh
runtime="$(cd "$(dirname "$0")/.." && pwd)"
root="${FAKE_NPM_PREFIX:-$runtime/lib/node_modules}"
line="npm[$(basename "$runtime")] $*"
printf '%s\\n' "$line" >> "$FAKE_LOG"
IFS='|'
for pattern in $FAKE_FAIL; do
  case "$line" in *"$pattern"*) exit 1 ;; esac
done
case "$1" in
  root) printf '%s\\n' "$root" ;;
  install) name="${3%@*}"; mkdir -p "$root/$name"
           printf '{"version": "%s"}\\n' "${3##*@}" > "$root/$name/package.json" ;;
esac
"""
OLLAMA_EXTRA = """if [ "$1" = list ]; then printf 'NAME ID SIZE\\nfirst:latest a 1\\nsecond:latest b 2\\n'; exit 0; fi"""
SUDO_EXTRA = """[ "$1" = -A ] && shift
"$@"; exit $?"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def fake(path, name, extra="", pre=""):
    write(path, FAKE.format(name=name, extra=extra, pre=pre)).chmod(0o755)


class Machine:
    """A temporary home, Homebrew prefix, and fake commands for one scenario."""

    def __init__(self, directory, platform="mac", profile="personal", repo=root,
                 brew=True, commands=("mas", "npm", "pnpm", "ollama", "sudo", "mdimport")):
        self.base = Path(directory)
        self.home = self.base / "home"
        self.home.mkdir()
        self.prefix = self.base / "prefix"
        (self.prefix / "bin").mkdir(parents=True)
        self.bin = self.base / "bin"
        self.log = self.base / "log"
        self.log.write_text("")
        fake(self.bin / "mise", "mise", MISE_EXTRA)
        extras = {"ollama": OLLAMA_EXTRA, "sudo": SUDO_EXTRA}
        for name in commands:
            fake(self.bin / name, name, extras.get(name, ""))
        if brew:
            self.add_brew()
        self.config = {
            "home": str(self.home), "repo_dir": str(repo), "platform": platform, "profile": profile,
            "user": "tester", "shell_path": "/bin/zsh", "ssh_agent_socket": "SSH_AUTH_SOCK",
            "pnpm_home": str(self.home / "pnpm"), "mise": str(self.bin / "mise"),
            "brew_prefix": str(self.prefix), "brew": str(self.prefix / "bin/brew"), "pnpm_global_packages": [],
            "steps": {name: name not in ("ssh", "remote-login") for name in
                      ("ssh", "git", "cli", "remote-login", "gui", "zsh", "app-store",
                       "osx", "node", "dotfiles", "dock")},
        }
        self.env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "FAKE_LOG": str(self.log),
                    "FAKE_FAIL": "", "MISE_CONFIG_DIR": str(self.home / ".config/mise"),
                    "FAKE_NODE_FILE": str(self.base / "node-path"), "FAKE_PREFIX": str(self.prefix),
                    "FAKE_PYTHON": sys.executable,
                    "FAKE_NODE_REGISTRY": str(self.base / "node-installs.json"),
                    "FAKE_NODE_FRAGMENT": str(self.home / ".config/mise/conf.d/dev-machine-setup.toml")}
        write(Path(self.env["FAKE_NODE_REGISTRY"]), "[]")
        self.fragment = self.home / ".config/mise/conf.d/dev-machine-setup.toml"
        self.active_bin = self.runtime("24.0.0")
        self.select_node(self.active_bin)

    def add_brew(self):
        fake(self.prefix / "bin/brew", "brew", pre=BREW_PRE)

    def runtime(self, version, packages=None, installed=True):
        """Prepare a real executable and npm globals; optionally defer registration."""
        path = self.home / ".local/share/mise/installs/node" / version
        write(path / "bin/node", '#!/bin/sh\nprintf "%s\\n" "$0"\n').chmod(0o755)
        if installed:
            registry = Path(self.env["FAKE_NODE_REGISTRY"])
            installs = [item for item in json.loads(registry.read_text())
                        if item["install_path"] != str(path)]
            installs.append({"version": version, "install_path": str(path)})
            registry.write_text(json.dumps(installs))
        fake_npm = write(path / "bin/npm", FAKE_NPM)
        fake_npm.chmod(0o755)
        globals_root = path / "lib/node_modules"
        globals_root.mkdir(parents=True, exist_ok=True)
        for name, package_version in (packages or {}).items():
            write(globals_root / name / "package.json", f'{{"version": "{package_version}"}}')
        return path / "bin"

    def select_node(self, bin_dir):
        (self.base / "node-path").write_text(f"{bin_dir}/node\n" if bin_dir else "")

    def selected_node(self):
        """Observe what the fake mise actually selects from the current fragment."""
        shell = software._Shell(self.config, False)
        shell.env.update(self.env)
        status, path = shell.query([self.config["mise"], "exec", "node", "--",
                                    "node", "-p", "process.execPath"])
        assert status == 0
        return Path(path.strip())

    def node_globals(self, bin_dir):
        return software._npm_globals(bin_dir.parent / "lib/node_modules")

    def run(self, action, check=False, **env):
        saved = dict(os.environ)
        os.environ.update(self.env, **env)
        for name in ("SUDO_ASKPASS", "XDG_CONFIG_HOME"):
            if name not in env:
                os.environ.pop(name, None)
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                software.run(action, self.config, check=check)
            return output.getvalue()
        except RuntimeError as error:
            error.output = output.getvalue()
            raise
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def calls(self):
        return self.log.read_text().splitlines()

    def tools(self):
        return tomllib.loads(self.fragment.read_text())["tools"]


def fails(function, text):
    try:
        function()
    except RuntimeError as error:
        assert text in str(error), error
        return error
    raise AssertionError(f"expected failure containing {text!r}")


def fixture_repo(directory, files):
    repo = Path(directory) / "repo"
    for relative, text in files.items():
        write(repo / "packages" / relative, text)
    return repo


def snapshot(path):
    """Every file except the fake-command log."""
    return sorted((str(item.relative_to(path)), item.read_bytes() if item.is_file() else b"")
                  for item in path.rglob("*") if item.name != "log")


# B1: the real inventories select every applicable declaration for each OS/profile.
for platform, os_name in (("mac", "macos"), ("linux", "linux")):
    for profile in ("personal", "work"):
        with tempfile.TemporaryDirectory() as directory:
            machine = Machine(directory, platform, profile)
            config = machine.config
            layers = ("shared", f"shared/{profile}", platform, f"{platform}/{profile}")
            expected_files = [root / "packages" / layer / f"{kind}.toml" for layer in layers
                              for kind in software.KINDS if (root / "packages" / layer / f"{kind}.toml").is_file()]
            assert software.inventory_files(config) == expected_files
            expected = []
            for path in expected_files:
                kind = path.stem
                if platform == "linux" and kind in software.MAC_ONLY_KINDS:
                    continue
                data = tomllib.loads(path.read_text())
                for section in ("packages", "tools"):
                    for key, value in data.get(section, {}).items():
                        selector = value.get("os") if isinstance(value, dict) else None
                        if selector in (None, os_name):
                            expected.append((kind, key))
            selected = [(entry.kind, entry.key) for entry in software.selected_entries(config)]
            assert selected == expected, set(selected) ^ set(expected)
            keys = {key for _, key in selected}
            assert ("brew:mosh" in keys) == (platform == "mac" and profile == "personal")
            assert ("brew-cask:codex" in keys) == (platform == "mac")
            assert ("aqua:openai/codex" in keys) == (platform == "linux")
            assert {"node", "pnpm", "brew:git", "brew:stow", "brew:fzf"} <= keys
            assert not any(kind in software.MAC_ONLY_KINDS for kind, _ in selected) or platform == "mac"
            before = snapshot(machine.base)
            output = machine.run("packages")
            assert machine.calls() == [] and snapshot(machine.base) == before
            assert "packages/shared/cli.toml" in output and "brew:git" in output
            print(f"PASS: {platform}/{profile} selects its layers and tiers; the preview is read-only")

# B1: missing layers are allowed; misspelt, missing, and malformed inventories fail.
with tempfile.TemporaryDirectory() as directory:
    repo = fixture_repo(directory, {"shared/cli.toml": '[packages]\n"brew:git" = "latest"\n'})
    machine = Machine(directory, repo=repo)
    assert [entry.key for entry in software.selected_entries(machine.config)] == ["brew:git"]
    for relative, text, message in (
        ("shared/cli.tom", "", "Invalid package inventory"),
        ("mac/team/cli.toml", "", "Invalid package inventory"),
        ("mac/Brewfile.cli", "", "Invalid package inventory"),
        ("mac/cli.toml", "[packages\n", "Malformed package inventory"),
        ("mac/cli.toml", '[packages]\n"git" = "latest"\n', "manager:package"),
        ("mac/cli.toml", '[packages]\n"brew:git" = "2.0"\n', "cannot be pinned"),
        ("mac/gui.toml", '[packages]\n"brew:git" = "latest"\n', "not allowed in gui"),
        ("mac/app-store.toml", '[packages]\n"mas:Drafts" = "latest"\n', "numeric App Store ID"),
        ("shared/cli-optional.toml", '[packages]\n"brew-cask:codex" = "latest"\n', "macOS-only"),
        ("mac/cli.toml", '[packages]\n"brew-cask:codex" = { greedy = "yes" }\n', "greedy must be"),
        ("mac/cli.toml", '[packages]\n"brew:git" = { greedy = true }\n', "unsupported options"),
        ("mac/cli.toml", '[tools]\nnode = { version = "lts", os = "linux" }\n', "never applies"),
    ):
        path = write(repo / "packages" / relative, text)
        fails(lambda: machine.run("packages"), message)
        path.unlink()
    write(repo / "packages/shared/cli-optional.toml", '[packages]\n"brew-cask:font-hack" = "latest"\n')
    machine.run("packages")
    (repo / "packages/shared/cli.toml").unlink()
    fails(lambda: machine.run("packages"), "Missing shared CLI inventory")
print("PASS: missing layers are allowed; misspelt, missing, unsupported, and malformed inventories fail")

CLI_REPO = {
    "shared/cli.toml": '[packages]\n"brew:git" = "latest"\n"brew-cask:codex" = { os = "macos", greedy = true }\n'
                       '[tools]\nnode = "lts"\npnpm = "latest"\n"npm:required" = "latest"\n'
                       '"aqua:openai/codex" = { version = "latest", os = "linux" }\n',
    "mac/cli-optional.toml": '[packages]\n"brew:first" = "latest"\n"brew:acme/tools/second" = "latest"\n'
                             '[tools]\n"aqua:x/broken" = "latest"\n"aqua:x/works" = "latest"\n'
                             '"npm:optional-broken" = "latest"\n"npm:optional-works" = "latest"\n',
    "mac/gui.toml": '[packages]\n"brew-cask:owned" = "latest"\n"brew-cask:fresh" = "latest"\n"brew-cask:bad" = "latest"\n',
    "mac/app-store.toml": '[packages]\n"mas:111" = { name = "One" }\n"mas:222" = { name = "Two" }\n',
}
BUNDLE = "brew bundle install --file=-: "

# B11: check mode prints the plan but runs only read-only queries and writes nothing.
for platform in ("mac", "linux"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, platform, repo=fixture_repo(directory, CLI_REPO))
        machine.config["pnpm_global_packages"] = ["typescript"]
        before = snapshot(machine.base)
        for action in ("cli", "gui", "app-store", "node", "update"):
            machine.run(action, check=True)
        assert all(call.startswith(("ollama list", "brew list ")) for call in machine.calls()), machine.calls()
        assert snapshot(machine.base) == before
print("PASS: check mode runs no installers and writes no files")

# Native installs trust only selected formulae and casks, including optional packages.
with tempfile.TemporaryDirectory() as directory:
    repo = fixture_repo(directory, {
        "shared/cli.toml": '[packages]\n"brew:git" = "latest"\n'
                           '"brew:can1357/tap/omp" = "latest"\n',
        "mac/cli.toml": '[packages]\n'
                        '"brew-cask:acme/widgets/cli-widget" = { greedy = true }\n',
        "mac/cli-optional.toml": '[packages]\n"brew:acme/tools/helper" = "latest"\n'
                                 '"brew-cask:acme/widgets/optional-widget" = "latest"\n',
        "mac/work/cli.toml": '[packages]\n"brew:acme/tools/excluded" = "latest"\n',
    })
    machine = Machine(directory, repo=repo)
    state = write(machine.base / "bundle-state.json", json.dumps({
        "trusted": ["formula:other/tools/keep"], "installed": [],
    }))
    driver = write(machine.base / "bundle.py", '''import json
import os
from pathlib import Path
import re
import sys

state_path = Path(os.environ["FAKE_BUNDLE_STATE"])
state = json.loads(state_path.read_text())
for line in sys.stdin:
    match = re.fullmatch(r'(tap|brew|cask) "([^"]+)"(.*)\\n', line)
    assert match, line
    kind, name, options = match.groups()
    item_type = {"tap": "tap", "brew": "formula", "cask": "cask"}[kind]
    identity = f"{item_type}:{name}"
    if "trusted: true" in options and identity not in state["trusted"]:
        state["trusted"].append(identity)
    if kind != "tap":
        tap = "/".join(name.split("/")[:2])
        if name.count("/") == 2 and not (
                identity in state["trusted"] or f"tap:{tap}" in state["trusted"]):
            print(f"Refusing to load untrusted {identity}", file=sys.stderr)
            sys.exit(1)
        if identity not in state["installed"]:
            state["installed"].append(identity)
    state_path.write_text(json.dumps(state))
''')
    fake(machine.prefix / "bin/brew", "brew",
         extra='exec "$FAKE_PYTHON" "$FAKE_BUNDLE_DRIVER"')
    machine.env.update(FAKE_BUNDLE_STATE=str(state), FAKE_BUNDLE_DRIVER=str(driver))
    before = state.read_bytes()
    machine.run("cli", check=True)
    assert state.read_bytes() == before
    machine.run("cli")
    installed = json.loads(state.read_text())
    selected = {"formula:git", "formula:can1357/tap/omp", "formula:acme/tools/helper",
                "cask:acme/widgets/cli-widget", "cask:acme/widgets/optional-widget"}
    assert set(installed["installed"]) == selected
    assert set(installed["trusted"]) == selected - {"formula:git"} | {"formula:other/tools/keep"}
print("PASS: required and optional installs trust only selected formulae/casks; previews preserve trust")

# Required CLI failures stop; optional failures are reported and the rest continue.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    output = machine.run("cli", FAKE_FAIL='brew "first"|install aqua:x/broken@latest')
    assert machine.tools() == {"aqua:x/works": "latest"}
    assert not any("node" in call or "pnpm" in call or "npm:" in call for call in machine.calls())
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    fails(lambda: machine.run("cli", FAKE_FAIL='brew "git"'), "Required CLI packages failed")
    assert not any(call.startswith("mise install") for call in machine.calls())
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=False)
    before = snapshot(machine.base)
    for action in ("cli", "gui"):
        fails(lambda: machine.run(action), "Homebrew is needed")
    assert machine.calls() == [] and snapshot(machine.base) == before
print("PASS: required CLI failures stop setup; optional failures are reported; package installs need Homebrew")

# The disabled tldr formula is removed before tlrc.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    (machine.prefix / "Cellar/tldr").mkdir(parents=True)
    fails(lambda: machine.run("cli", FAKE_FAIL="uninstall tldr"), "tldr")
    assert not any(call.startswith(BUNDLE) for call in machine.calls())
print("PASS: a failed tldr removal stops new CLI package installation")

# GUI and App Store: Mac only; installed casks upgrade greedily, others install with --adopt.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, "linux", repo=fixture_repo(directory, CLI_REPO))
    assert "only on macOS" in machine.run("gui") and "only on macOS" in machine.run("app-store")
    assert machine.calls() == []
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    (machine.prefix / "Caskroom/owned").mkdir(parents=True)
    output = machine.run("gui", FAKE_FAIL="install --cask --adopt bad")
    calls = [call for call in machine.calls() if not call.startswith("brew list")]
    assert "brew install --cask --adopt fresh" in calls
    assert "brew upgrade --cask --greedy owned" in calls
    assert calls[-1] == "brew install --cask --adopt bad"
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    output = machine.run("app-store", FAKE_FAIL="mas get 111|mas install 111|mas get 222")
    calls = machine.calls()
    assert calls[0] == "mdimport /Applications"
    assert f"sudo {machine.bin}/mas install 222" in calls and "mas install 222" in calls
    assert "App Store installation failures: mas:111 (One)" in output, output
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), commands=("sudo", "mdimport"))
    fails(lambda: machine.run("app-store", FAKE_FAIL="brew install mas"), "mas CLI")
    assert machine.calls() == ["brew install mas"]
print("PASS: GUI and App Store failures are reported and setup continues; both are Mac only")

# B10/B12: Node is installed and proven before the old provider is retired.
for platform in ("mac", "linux"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, platform, repo=fixture_repo(directory, CLI_REPO), brew=True)
        machine.config["pnpm_global_packages"] = ["typescript", "@scope/tool"]
        (machine.prefix / "var/homebrew/linked/node").mkdir(parents=True)
        user_config = write(machine.home / ".config/mise/config.toml", '[tools]\npython = "3.13"\n')
        write(machine.fragment, '[tools]\n"aqua:earlier/profile" = "latest"\n')
        nvm_block = ('# BEGIN dev-machine Node and pnpm\nexport NVM_DIR="$HOME/.nvm"\n'
                     '. "$(brew --prefix nvm)/nvm.sh"\n# END dev-machine Node and pnpm\n')
        write(machine.home / ".bashrc", "alias keep=1\n" + nvm_block)
        dotfiles_zshrc = write(machine.base / "dotfiles/.zshrc", "# dotfiles\n")
        (machine.home / ".zshrc").symlink_to(dotfiles_zshrc)

        fails(lambda: machine.run("node", FAKE_FAIL="mise install node"), "Installing Node and pnpm")
        assert "node" not in machine.tools() and "brew unlink node" not in machine.calls()
        assert "nvm.sh" in (machine.home / ".bashrc").read_text()
        fails(lambda: machine.run("node", FAKE_FAIL="mise exec node@lts"), "did not run")
        assert "node" not in machine.tools() and "brew unlink node" not in machine.calls()

        machine.log.write_text("")
        fails(lambda: machine.run("node", FAKE_FAIL="install npm:optional-broken|pnpm add -g @scope/tool"),
              "@scope/tool")
        assert "brew unlink node" not in machine.calls()
        machine.run("node", FAKE_FAIL="install npm:optional-broken")
        assert "brew unlink node" in machine.calls()
        tools = machine.tools()
        assert tools["node"] == "24.0.0" and tools["npm:required"] == "latest"
        if platform == "mac":
            assert tools["npm:optional-works"] == "latest" and "npm:optional-broken" not in tools
        assert tools["aqua:earlier/profile"] == "latest"
        assert user_config.read_text() == '[tools]\npython = "3.13"\n'
        assert (machine.home / "pnpm/bin").is_dir()
        assert dotfiles_zshrc.read_text() == "# dotfiles\n"
        bashrc = (machine.home / ".bashrc").read_text()
        if platform == "linux":
            assert "nvm" not in bashrc and bashrc.startswith("alias keep=1\n")
            assert f"export PNPM_HOME={machine.home}/pnpm" in bashrc and bashrc.count("# BEGIN") == 1
        else:
            assert "nvm.sh" in bashrc
print("PASS: Node is proven before Homebrew node is unlinked; failures stop setup; config and dotfiles untouched")

# D2: npm globals from nvm's default Node and Homebrew node move to the mise Node.
for fail in (False, True):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=True)
        (machine.prefix / "var/homebrew/linked/node").mkdir(parents=True)
        (machine.prefix / "Cellar/node/25.0.0").mkdir(parents=True)
        nvm = machine.home / ".nvm"
        write(nvm / "alias/default", "lts/*\n")
        write(nvm / "alias/lts/*", "lts/jod\n")
        write(nvm / "alias/lts/jod", "v20.1.0\n")
        for version, packages in (("v20.1.0", {"eslint": "8.0.0", "@scope/tool": "1.2.0", "npm": "10.0.0"}),
                                  ("v22.3.0", {"prettier": "3.0.0"})):
            for name, package_version in packages.items():
                write(nvm / "versions/node" / version / "lib/node_modules" / name / "package.json",
                      f'{{"version": "{package_version}"}}')
        linked = write(machine.base / "work/mylink/package.json", '{"version": "0.1.0"}').parent
        (nvm / "versions/node/v20.1.0/lib/node_modules/mylink").symlink_to(linked)
        for name, package_version in (("eslint", "7.0.0"), ("typescript", "5.0.0")):
            write(machine.prefix / "lib/node_modules" / name / "package.json", f'{{"version": "{package_version}"}}')
        machine.runtime("24.0.0", {"existing": "1.0.0"})
        legacy = snapshot(nvm), snapshot(machine.prefix / "lib")
        if fail:
            error = fails(lambda: machine.run("node", FAKE_FAIL="install -g @scope/tool"), "@scope/tool@1.2.0")
            output = error.output
            assert "brew unlink node" not in machine.calls() and not machine.fragment.exists()
            machine.run("node")
            assert machine.node_globals(machine.active_bin)["@scope/tool"] == "1.2.0"
            shutil.rmtree(machine.active_bin.parent / "lib/node_modules/@scope/tool")
            machine.run("node")
            assert "@scope/tool" not in machine.node_globals(machine.active_bin)
        else:
            output = machine.run("node")
            calls = machine.calls()
            assert calls.index("npm[24.0.0] install -g eslint@8.0.0") < calls.index("brew unlink node")
            assert machine.node_globals(machine.active_bin) == {
                "@scope/tool": "1.2.0", "eslint": "8.0.0", "existing": "1.0.0", "typescript": "5.0.0"}
            assert machine.tools()["node"] == "24.0.0"
            shutil.rmtree(machine.active_bin.parent / "lib/node_modules/eslint")
            machine.run("node")
            assert "eslint" not in machine.node_globals(machine.active_bin), "legacy migration restored a removed package"
        assert (snapshot(nvm), snapshot(machine.prefix / "lib")) == legacy, "Legacy runtimes were changed"
print("PASS: npm globals move from nvm's default and Homebrew node at their versions; "
      "a failed move keeps Homebrew node linked")

for ancestor in (".config", ".config/mise", "xdg", "mise-config-parent"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
        linked_node = machine.prefix / "var/homebrew/linked/node"
        linked_node.mkdir(parents=True)
        external = write(machine.base / "elsewhere/keep.toml", "untouched").parent
        path = machine.home / ancestor
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(external)
        env = {}
        if ancestor == "xdg":
            env = {"MISE_CONFIG_DIR": "", "XDG_CONFIG_HOME": str(path)}
        elif ancestor == "mise-config-parent":
            env = {"MISE_CONFIG_DIR": str(path / "nested/mise")}
        before = snapshot(external)
        fails(lambda: machine.run("node", **env), "symlink")
        assert snapshot(external) == before
        assert linked_node.exists(), "Homebrew Node was retired before safe configuration"
        assert not any(call.startswith("mise install") for call in machine.calls())
print("PASS: symlinked fragment ancestors cannot mutate external configuration or retire Node")

# B10/B12: updates continue past failures, skip missing tools, and fail at the end.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, "linux", repo=fixture_repo(directory, CLI_REPO), brew=False, commands=("mas",))
    output = machine.run("update")
    assert "failed" not in output
    assert machine.calls() == []
for status in ("ok", "fail"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=True)
        write(machine.fragment, '[tools]\nnode = "lts"\npnpm = "latest"\n')
        fail = "-- npm update -g|ollama pull first:latest" if status == "fail" else ""
        if status == "ok":
            output = machine.run("update")
        else:
            error = fails(lambda: machine.run("update", FAKE_FAIL=fail), "Update failures: npm globals, Ollama models")
            output = error.output
        calls = machine.calls()
        assert "mise exec -- pnpm update -g" in calls and "mas upgrade" in calls
        pulls = [call for call in calls if call.startswith("ollama pull")]
        assert pulls == (["ollama pull first:latest"] if status == "fail"
                         else ["ollama pull first:latest", "ollama pull second:latest"])
print("PASS: updates skip missing components, keep going after failures, and report them at the end")

# D3: a Node upgrade keeps the old runtime and moves its npm globals to the new one.
for case in ("moved", "unprobed", "failed", "shared prefix"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=True)
        write(machine.fragment, '[tools]\nnode = "lts"\npnpm = "latest"\n')
        (machine.prefix / "var/homebrew/linked/node").mkdir(parents=True)
        old_bin = machine.runtime("24.0.0", {"cli-a": "1.0.0"})
        new_bin = machine.runtime("24.1.0", installed=False)
        env = {"FAKE_NODE_AFTER": f"{new_bin}/node"}
        if case == "unprobed":
            machine.select_node(None)
            machine.runtime("22.0.0")
            write(machine.fragment, '[tools]\nnode = "23.0.0"\npnpm = "latest"\n')
        if case == "shared prefix":
            env["FAKE_NPM_PREFIX"] = str(machine.base / "npm-global")
        if case == "failed":
            error = fails(lambda: machine.run("update", FAKE_FAIL="install -g cli-a", **env),
                          "Update failures: npm global transfer")
            output = error.output
            assert machine.selected_node() == old_bin / "node"
            assert "brew unlink node" not in machine.calls()
            assert [call for call in machine.calls() if call.startswith("ollama pull")] == [
                "ollama pull first:latest", "ollama pull second:latest"]
        else:
            output = machine.run("update", **env)
        calls = machine.calls()
        assert machine.node_globals(old_bin) == {"cli-a": "1.0.0"}, "The old runtime lost its globals"
        installs = [call for call in calls if " install -g " in call]
        if case == "shared prefix":
            assert installs == []
        else:
            assert installs == ["npm[24.1.0] install -g cli-a@1.0.0"], calls
        if case in ("moved", "unprobed"):
            assert machine.node_globals(new_bin) == {"cli-a": "1.0.0"}
            assert (calls.index(installs[0]) < calls.index("brew unlink node")
                    < calls.index("mise exec -- npm update -g")), calls
print("PASS: Node upgrades keep the old runtime, move its npm globals before updating them, "
      "and report a failed move at the end")

# A failed transfer retries from the original runtime, not the newly installed target.
for action, failure, selector_change in (("node", "install -g cli-a", False),
                                          ("update", "install -g cli-a", False),
                                          ("node", "npm[24.0.0] root -g", False),
                                          ("node", "install -g cli-a", True)):
    with tempfile.TemporaryDirectory() as directory:
        repo = fixture_repo(directory, CLI_REPO)
        machine = Machine(directory, repo=repo)
        old_bin = machine.runtime("24.0.0", {"cli-a": "1.0.0"})
        target = machine.runtime("24.1.0")
        write(machine.fragment, '[tools]\nnode = "24.0.0"\npnpm = "latest"\n')
        state_path = machine.fragment.with_suffix(".node.json")
        write(state_path, '{"selector": "lts"}')
        linked = machine.prefix / "var/homebrew/linked/node"
        linked.mkdir(parents=True)
        error = fails(lambda: machine.run(action, FAKE_FAIL=failure, FAKE_NODE_AFTER=f"{target}/node"),
                      "inspect npm globals" if "root" in failure else
                      "Update failures" if action == "update" else "failed to move")
        assert machine.tools()["node"] == "24.0.0"
        assert machine.selected_node() == old_bin / "node"
        assert json.loads(state_path.read_text())["source"] == str(old_bin)
        assert linked.exists()
        assert machine.node_globals(target) == {}
        if action == "update":
            assert "mas upgrade" in machine.calls() and "ollama pull second:latest" in machine.calls()
            assert not any("-- npm update" in call for call in machine.calls())
        selector = "lts"
        if selector_change:
            target = machine.runtime("25.0.0")  # already installed before the changed request
            selector = "25.0.0"
            write(repo / "packages/shared/cli.toml",
                  CLI_REPO["shared/cli.toml"].replace('node = "lts"', 'node = "25.0.0"'))
        machine.run(action, FAKE_NODE_AFTER=f"{target}/node")
        assert machine.node_globals(target) == {"cli-a": "1.0.0"}
        assert machine.node_globals(old_bin) == {"cli-a": "1.0.0"}
        assert machine.tools()["node"] == target.parent.name
        assert machine.selected_node() == target / "node"
        assert json.loads(state_path.read_text()) == {"selector": selector}
        assert not linked.exists()
        shutil.rmtree(target.parent / "lib/node_modules/cli-a")
        machine.run(action, FAKE_NODE_AFTER=f"{target}/node")
        assert machine.node_globals(target) == {}, "A committed migration replayed its old source"
print("PASS: transfer and source-probe failures retain the working pin and original retry source")

# PATH-only Node is neither a migration source nor proof of a mise target.
for target_missing in (False, True):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, "linux", repo=fixture_repo(directory, CLI_REPO),
                          brew=False, commands=("sudo", "mdimport"))
        Path(machine.env["FAKE_NODE_REGISTRY"]).write_text("[]")
        system_bin = machine.base / "system/usr/bin"
        write(system_bin / "node", '#!/bin/sh\nprintf "%s\\n" "$0"\n').chmod(0o755)
        machine.select_node(system_bin)
        assert not (system_bin / "npm").exists()
        state_path = machine.fragment.with_suffix(".node.json")
        if target_missing:
            fails(lambda: machine.run("node"), "did not run")
            assert json.loads(state_path.read_text())["source"] is None
            assert not machine.fragment.exists()
        machine.run("node", FAKE_NODE_AFTER=f"{machine.active_bin}/node")
        assert machine.selected_node() == machine.active_bin / "node"
        assert machine.tools()["node"] == "24.0.0"
        assert json.loads(state_path.read_text()) == {"selector": "lts"}
print("PASS: PATH-only Node without npm cannot become a mise source or target; installation recovers")

# A missing journal source must not replace a user's working selection or lose recovery data.
for missing in ("executable", "registration"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
        old_bin = machine.runtime("24.0.0", {"recover-me": "3.0.0"})
        target = machine.runtime("24.1.0")
        write(machine.fragment, '[tools]\nnode = "24.0.0"\n')
        fails(lambda: machine.run("node", FAKE_FAIL="install -g recover-me",
                                  FAKE_NODE_AFTER=f"{target}/node"), "failed to move")
        state_path = machine.fragment.with_suffix(".node.json")
        write(machine.fragment, '[tools]\nnode = "24.1.0"\n')
        if missing == "executable":
            (old_bin / "node").unlink()
        else:
            registry = Path(machine.env["FAKE_NODE_REGISTRY"])
            registry.write_text(json.dumps([item for item in json.loads(registry.read_text())
                                            if item["install_path"] != str(old_bin.parent)]))
        before = machine.fragment.read_bytes(), state_path.read_bytes()
        fails(lambda: machine.run("node"), "Restore it before retrying")
        assert (machine.fragment.read_bytes(), state_path.read_bytes()) == before
        assert machine.selected_node() == target / "node"
        assert machine.node_globals(target) == {}
        assert machine.node_globals(old_bin) == {"recover-me": "3.0.0"}
        machine.runtime("24.0.0")
        machine.run("node")
        assert machine.node_globals(target) == {"recover-me": "3.0.0"}
        assert json.loads(state_path.read_text()) == {"selector": "lts"}
print("PASS: missing retry sources preserve the working pin and journal until the runtime is restored")

# Inspection failures cannot silently discard an installed runtime's globals.
for env in ({"FAKE_FAIL": "mise ls --installed"}, {"FAKE_NODE_INSTALLS": "broken-json"},
            {"FAKE_NODE_INSTALLS": "{}"}):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
        machine.runtime("24.0.0", {"keep-me": "1.0.0"})
        write(machine.fragment, '[tools]\nnode = "24.0.0"\n')
        before = machine.fragment.read_bytes()
        fails(lambda: machine.run("node", **env), "Could not inspect installed mise Node")
        assert machine.fragment.read_bytes() == before
        assert not machine.fragment.with_suffix(".node.json").exists()
        assert machine.node_globals(machine.active_bin) == {"keep-me": "1.0.0"}
print("PASS: installed-runtime metadata failures stop before changing Node selection or migration state")

# An already-installed target must not win source selection over the managed old version.
with tempfile.TemporaryDirectory() as directory:
    repo = fixture_repo(directory, {**CLI_REPO, "shared/cli.toml":
                                   CLI_REPO["shared/cli.toml"].replace('node = "lts"', 'node = "25.0.0"')})
    machine = Machine(directory, repo=repo)
    old_bin = machine.runtime("24.0.0", {"from-old": "2.0.0"})
    target = machine.runtime("25.0.0")
    machine.select_node(target)
    write(machine.fragment, '[tools]\nnode = "24.0.0"\n')
    machine.run("node")
    assert machine.node_globals(target) == {"from-old": "2.0.0"}

# Recover a crash between fragment commit and clearing the journal without replaying legacy globals.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    old_bin = machine.runtime("22.0.0", {"removed": "1.0.0"})
    write(machine.fragment, '[tools]\nnode = "24.0.0"\n')
    write(machine.fragment.with_suffix(".node.json"),
          json.dumps({"selector": "lts", "source": str(old_bin), "legacy": True, "target": "24.0.0"}))
    machine.run("node")
    assert machine.node_globals(machine.active_bin) == {}
print("PASS: target selectors and interrupted journal cleanup preserve committed migration semantics")

# A global config override cannot silently retire the working legacy provider.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    linked = machine.prefix / "var/homebrew/linked/node"
    linked.mkdir(parents=True)
    override = machine.runtime("22.0.0")
    fails(lambda: machine.run("node", FAKE_NODE_OVERRIDE=f"{override}/node"), "overrides")
    assert linked.exists()

# Maintenance categories cover installed packages across profiles, never only selected inventory.
BREW_CLI_CASKS = {"codex", "work-cli", "pinned-cli", "missing-cli", "auto-cli", "latest-cli"}
BREW_REPO = {**CLI_REPO, "mac/work/cli.toml": '[packages]\n' + "\n".join(
    f'"brew-cask:acme/tools/{name}" = {{ version = "latest", greedy = true }}'
    for name in sorted(BREW_CLI_CASKS - {"codex"}))}


def brew_state(machine):
    state = {"refreshes": 0, "formulae": {}, "casks": {}}
    for group, names in (
            ("formulae", ("git", "user-formula", "pinned-formula", "missing-formula",
                          "unused-dependency", "user-desktop")),
            ("casks", (*sorted(BREW_CLI_CASKS), "user-desktop", "pinned-desktop",
                       "missing-desktop", "auto-desktop", "latest-desktop"))):
        for name in names:
            state[group][name] = {
                "version": "1", "current": "latest" if name.startswith("latest-") else "2",
                "pinned": name.startswith("pinned-"), "available": not name.startswith("missing-"),
                "auto_updates": name.startswith("auto-"), "cleaned": False}
    path = write(machine.base / "brew-state.json", json.dumps(state))
    machine.env["FAKE_BREW_STATE"] = str(path)
    machine.env["HOMEBREW_UPGRADE_GREEDY_CASKS"] = ""
    return path, state


for excluded in (None, "node", "cli", "gui", "app-store", "cli+gui"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, BREW_REPO))
        for step in excluded.split("+") if excluded else ():
            machine.config["steps"][step] = False
        state_path, initial = brew_state(machine)
        write(machine.fragment, '[tools]\nnode = "24.0.0"\npnpm = "latest"\n'
                                '"npm:provider" = "latest"\n"aqua:other/profile" = "latest"\n')
        before = machine.fragment.read_bytes()
        machine.run("update")
        final = json.loads(state_path.read_text())
        assert final["refreshes"] == (0 if excluded == "cli+gui" else 1)
        for group in ("formulae", "casks"):
            assert final[group].keys() == initial[group].keys()
            for name, package in initial[group].items():
                owner = "cli" if group == "formulae" or name in BREW_CLI_CASKS else "gui"
                selected = machine.config["steps"][owner]
                if not selected:
                    assert final[group][name] == package, (excluded, group, name)
                    continue
                eligible = (package["available"] and not package["pinned"]
                            and not package["auto_updates"] and package["current"] != "latest")
                assert final[group][name]["version"] == (package["current"] if eligible else "1"), name
                # The shared formula/cask token cannot be cleaned selectively.
                cleanable = package["available"] and not (
                    name == "user-desktop" and excluded in ("cli", "gui"))
                assert final[group][name]["cleaned"] == cleanable, (excluded, group, name)
        calls = machine.calls()
        if excluded in ("cli", "cli+gui"):
            assert not any("aqua:other/profile" in call or "ollama" in call for call in calls)
        if excluded == "node":
            assert not any("node@" in call or "pnpm" in call or "npm:" in call or "npm update" in call
                           for call in calls)
            assert machine.fragment.read_bytes() == before
        assert ("mas upgrade" in calls) == (excluded != "app-store")
print("PASS: maintenance preserves pins, non-greedy defaults, stale packages and excluded state across profiles")

for failure, bad_json, component in (
        ("brew outdated", False, "Homebrew casks"),
        ("", True, "Homebrew casks"),
        ("brew list --cask", False, "Homebrew casks"),
        ("brew upgrade --cask", False, "Homebrew casks"),
        ("brew upgrade --formula", False, "Homebrew formulae")):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, BREW_REPO))
        machine.config["steps"]["gui"] = False
        state_path, initial = brew_state(machine)
        error = fails(lambda: machine.run("update", FAKE_FAIL=failure,
                                         FAKE_BREW_BAD_JSON="1" if bad_json else ""), component)
        final = json.loads(state_path.read_text())
        assert final["formulae"]["git"]["version"] == ("1" if component == "Homebrew formulae" else "2")
        assert final["casks"]["codex"]["version"] == ("1" if component == "Homebrew casks" else "2")
        assert final["casks"]["user-desktop"] == initial["casks"]["user-desktop"]
        assert final["casks"]["missing-cli"]["version"] == "1"
        assert "Mac App Store: completed" in error.output

with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, BREW_REPO))
    machine.config["steps"]["gui"] = False
    state_path, initial = brew_state(machine)
    for name in ("codex", "work-cli"):
        initial["casks"][name]["version"] = "2"
    state_path.write_text(json.dumps(initial))
    machine.run("update")
    final = json.loads(state_path.read_text())
    assert {name: package["version"] for name, package in final["casks"].items()} == {
        name: package["version"] for name, package in initial["casks"].items()}
print("PASS: empty eligibility never upgrades other casks; query and upgrade failures remain visible and independent")

with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    machine.config["steps"]["node"] = False
    selected = software.selected_entries(machine.config)
    assert not any(entry.key in ("node", "pnpm") or entry.key.startswith("npm:") for entry in selected)
    output = machine.run("packages")
    assert "npm:required" not in output and "brew:git" in output
    machine.config["steps"]["cli"] = False
    machine.config["steps"]["node"] = True
    selected = software.selected_entries(machine.config)
    assert {"node", "pnpm", "npm:required"} <= {entry.key for entry in selected}
    assert not any(entry.key == "brew:git" for entry in selected)
    machine.run("node")
    assert not any(call.startswith("brew bundle") for call in machine.calls())
print("PASS: component selections and previews separate native CLI from the Node ecosystem")
