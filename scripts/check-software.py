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
{extra}
IFS='|'
for pattern in $FAKE_FAIL; do
  case "$line" in *"$pattern"*) exit 1 ;; esac
done
exit 0
"""
# brew bundle logs its Brewfile from stdin on the same line, joined by "; ".
BREW_PRE = """[ "$1" = bundle ] && line="$line: $(sed 's/$/;/' | tr '\\n' ' ')"
if [ "$1" = list ]; then printf '%s\\n' "$line" >> "$FAKE_LOG"; [ -d "$FAKE_PREFIX/Caskroom/$3" ]; exit $?; fi
if [ "$1" = unlink ] && [ "$2" = node ]; then rm -rf "$FAKE_PREFIX/var/homebrew/linked/node"; fi"""
# The selected mise Node is the path in $FAKE_NODE_FILE. Installing or upgrading
# Node switches it to $FAKE_NODE_AFTER when that is set.
MISE_EXTRA = """case "$*" in
  *"node -p process.execPath"*) [ -s "$FAKE_NODE_FILE" ] || exit 1; cat "$FAKE_NODE_FILE"; exit 0 ;;
  "ls --installed --json node") printf '%s\\n' "${FAKE_NODE_INSTALLS:-[]}"; exit 0 ;;
  install*node*|upgrade*node*) [ -z "$FAKE_NODE_AFTER" ] || printf '%s\\n' "$FAKE_NODE_AFTER" > "$FAKE_NODE_FILE" ;;
esac"""
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
        }
        self.env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "FAKE_LOG": str(self.log),
                    "FAKE_FAIL": "", "MISE_CONFIG_DIR": str(self.home / ".config/mise"),
                    "FAKE_NODE_FILE": str(self.base / "node-path"), "FAKE_PREFIX": str(self.prefix)}
        self.fragment = self.home / ".config/mise/conf.d/dev-machine-setup.toml"
        self.active_bin = self.runtime("24.0.0")
        self.select_node(self.active_bin)

    def add_brew(self):
        fake(self.prefix / "bin/brew", "brew", pre=BREW_PRE)

    def runtime(self, version, packages=None):
        """A fake mise Node install with npm globals {name: version}; returns its bin dir."""
        path = self.home / ".local/share/mise/installs/node" / version
        fake_npm = write(path / "bin/npm", FAKE_NPM)
        fake_npm.chmod(0o755)
        globals_root = path / "lib/node_modules"
        globals_root.mkdir(parents=True, exist_ok=True)
        for name, package_version in (packages or {}).items():
            write(globals_root / name / "package.json", f'{{"version": "{package_version}"}}')
        return path / "bin"

    def select_node(self, bin_dir):
        (self.base / "node-path").write_text(f"{bin_dir}/node\n" if bin_dir else "")

    def node_globals(self, bin_dir):
        return software._npm_globals(bin_dir.parent / "lib/node_modules")

    def run(self, action, check=False, **env):
        saved = dict(os.environ)
        os.environ.update(self.env, **env)
        for name in ("SUDO_ASKPASS", "XDG_CONFIG_HOME"):
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
                       '[tools]\nnode = "lts"\npnpm = "latest"\n"aqua:openai/codex" = { version = "latest", os = "linux" }\n',
    "mac/cli-optional.toml": '[packages]\n"brew:first" = "latest"\n"brew:acme/tools/second" = "latest"\n'
                             '[tools]\n"aqua:x/broken" = "latest"\n"aqua:x/works" = "latest"\n',
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
        assert all(call.startswith(("ollama list", "brew list --cask ")) for call in machine.calls()), machine.calls()
        assert snapshot(machine.base) == before
print("PASS: check mode runs no installers and writes no files")

# Required CLI failures stop; optional failures are reported and the rest continue.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    output = machine.run("cli", FAKE_FAIL='brew "first"|install aqua:x/broken@latest')
    assert "Optional CLI failures: brew:first, aqua:x/broken" in output, output
    assert machine.tools() == {"node": "lts", "pnpm": "latest", "aqua:x/works": "latest"}
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    fails(lambda: machine.run("cli", FAKE_FAIL='brew "git"'), "Required CLI packages failed")
    assert not any(call.startswith("mise install") for call in machine.calls())
    machine.log.write_text("")
    fails(lambda: machine.run("cli", FAKE_FAIL="brew update"), "Updating Homebrew failed")
    assert machine.calls() == ["brew update"]
    machine.log.write_text("")
    fails(lambda: machine.run("cli", FAKE_FAIL="mise install node"), "Required mise tools failed")
    assert not machine.fragment.exists() and not any('"first"' in call for call in machine.calls())
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
    assert calls == ["brew update", "brew upgrade --cask --greedy owned", "brew install --cask --adopt fresh",
                     "brew install --cask --adopt bad"], calls
    assert "GUI cask failures: bad" in output
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
        machine.select_node(machine.prefix / "bin")
        fails(lambda: machine.run("node"), "did not run")
        machine.select_node(machine.active_bin)
        assert "node" not in machine.tools() and "brew unlink node" not in machine.calls()

        machine.log.write_text("")
        fails(lambda: machine.run("node", FAKE_FAIL="pnpm add -g @scope/tool"), "@scope/tool")
        calls = machine.calls()
        assert calls.index("mise install node@lts pnpm@latest") < calls.index("brew unlink node")
        assert machine.tools() == {"aqua:earlier/profile": "latest", "node": "lts", "pnpm": "latest"}
        assert user_config.read_text() == '[tools]\npython = "3.13"\n'
        assert "mise exec node@lts pnpm@latest -- pnpm add -g typescript@latest" in calls
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
        else:
            output = machine.run("node")
            calls = machine.calls()
            assert calls.index("npm[24.0.0] install -g eslint@8.0.0") < calls.index("brew unlink node")
            assert machine.node_globals(machine.active_bin) == {
                "@scope/tool": "1.2.0", "eslint": "8.0.0", "existing": "1.0.0", "typescript": "5.0.0"}
            assert machine.tools()["node"] == "lts"
            shutil.rmtree(machine.active_bin.parent / "lib/node_modules/eslint")
            machine.run("node")
            assert "eslint" not in machine.node_globals(machine.active_bin), "legacy migration restored a removed package"
        assert (snapshot(nvm), snapshot(machine.prefix / "lib")) == legacy, "Legacy runtimes were changed"
        assert "nvm v20.1.0 (default alias default -> lts/* -> lts/jod -> v20.1.0)" in output, output
        assert "using 8.0.0 from nvm v20.1.0" in output and "not 7.0.0 from Homebrew node" in output
        assert "other nvm versions are not moved: v22.3.0" in output
        assert "Not moving npm global mylink" in output
print("PASS: npm globals move from nvm's default and Homebrew node at their versions; "
      "a failed move keeps Homebrew node linked")

with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    linked_node = machine.prefix / "var/homebrew/linked/node"
    linked_node.mkdir(parents=True)
    (machine.home / ".config").mkdir()
    write(machine.base / "elsewhere/conf.d/keep.toml", "")
    (machine.home / ".config/mise").symlink_to(machine.base / "elsewhere")
    fails(lambda: machine.run("node"), "symlink")
    assert not (machine.base / "elsewhere/conf.d/dev-machine-setup.toml").exists()
    assert linked_node.exists(), "Homebrew Node was retired before its replacement configuration was safe"
print("PASS: a refused runtime fragment leaves Homebrew Node linked and external configuration unchanged")

# B10/B12: updates continue past failures, skip missing tools, and fail at the end.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, "linux", repo=fixture_repo(directory, CLI_REPO), brew=False, commands=("mas",))
    output = machine.run("update")
    for name in ("Homebrew metadata", "Homebrew formulae", "Homebrew casks", "mise tools", "npm globals",
                 "pnpm globals", "Mac App Store", "Ollama models"):
        assert f"{name}: skipped" in output, output
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
        for command in ("brew update", "brew upgrade --formula", "brew upgrade --cask", "brew cleanup -s",
                        "mise upgrade --no-prune node pnpm", "mise exec -- pnpm update -g", "mas upgrade"):
            assert command in calls, (command, calls)
        pulls = [call for call in calls if call.startswith("ollama pull")]
        assert pulls == (["ollama pull first:latest"] if status == "fail"
                         else ["ollama pull first:latest", "ollama pull second:latest"])
        assert "pnpm globals: completed" in output and "Mac App Store: completed" in output
print("PASS: updates skip missing components, keep going after failures, and report them at the end")

# D3: a Node upgrade keeps the old runtime and moves its npm globals to the new one.
for case in ("moved", "unprobed", "failed", "shared prefix"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=True)
        write(machine.fragment, '[tools]\nnode = "lts"\npnpm = "latest"\n')
        (machine.prefix / "var/homebrew/linked/node").mkdir(parents=True)
        old_bin = machine.runtime("24.0.0", {"cli-a": "1.0.0"})
        new_bin = machine.runtime("24.1.0")
        env = {"FAKE_NODE_AFTER": f"{new_bin}/node"}
        if case == "unprobed":
            machine.select_node(None)
            env["FAKE_NODE_INSTALLS"] = json.dumps(
                [{"version": version, "install_path": str(bin_dir.parent)}
                 for version, bin_dir in (("24.0.0", old_bin), ("22.0.0", machine.runtime("22.0.0")))])
        if case == "shared prefix":
            env["FAKE_NPM_PREFIX"] = str(machine.base / "npm-global")
        if case == "failed":
            error = fails(lambda: machine.run("update", FAKE_FAIL="install -g cli-a", **env),
                          "Update failures: npm global transfer")
            output = error.output
            assert "brew unlink node" not in machine.calls()
            assert [call for call in machine.calls() if call.startswith("ollama pull")] == [
                "ollama pull first:latest", "ollama pull second:latest"]
        else:
            output = machine.run("update", **env)
        calls = machine.calls()
        assert "mise upgrade --no-prune node pnpm" in calls
        assert machine.node_globals(old_bin) == {"cli-a": "1.0.0"}, "The old runtime lost its globals"
        installs = [call for call in calls if " install -g " in call]
        if case == "shared prefix":
            assert installs == [] and "npm global transfer: completed" in output
        else:
            assert installs == ["npm[24.1.0] install -g cli-a@1.0.0"], calls
            assert "previous mise Node 24.0.0" in output, output
        if case in ("moved", "unprobed"):
            assert machine.node_globals(new_bin) == {"cli-a": "1.0.0"}
            assert (calls.index(installs[0]) < calls.index("brew unlink node")
                    < calls.index("mise exec -- npm update -g")), calls
            assert "npm global transfer: completed" in output
print("PASS: Node upgrades keep the old runtime, move its npm globals before updating them, "
      "and report a failed move at the end")
