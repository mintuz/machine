#!/usr/bin/env python3
"""Check package selection, installs, runtimes, and updates with fake tools.

Nothing is installed: mise, Homebrew, mas, sudo, npm, pnpm, and Ollama are
replaced by logging stand-ins in temporary directories.
"""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import tomllib

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from devsetup import software  # noqa: E402

FAKE = """#!/bin/sh
line="{name} $*"
printf '%s\\n' "$line" >> "$FAKE_LOG"
{extra}
IFS='|'
for pattern in $FAKE_FAIL; do
  case "$line" in *"$pattern"*) exit 1 ;; esac
done
exit 0
"""
MISE_EXTRA = """case "$*" in
  *"node -p process.execPath"*) printf '%s\\n' "$FAKE_NODE_PATH"; exit "${FAKE_NODE_STATUS:-0}" ;;
esac"""
OLLAMA_EXTRA = """if [ "$1" = list ]; then printf 'NAME ID SIZE\\nfirst:latest a 1\\nsecond:latest b 2\\n'; exit 0; fi"""
SUDO_EXTRA = """[ "$1" = -A ] && shift
"$@"; exit $?"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def fake(path, name, extra=""):
    write(path, FAKE.format(name=name, extra=extra)).chmod(0o755)


class Machine:
    """A temporary home, Homebrew prefix, and fake commands for one scenario."""

    def __init__(self, directory, platform="mac", profile="personal", repo=root,
                 brew=False, commands=("mas", "npm", "pnpm", "ollama", "sudo", "mdimport")):
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
            fake(self.prefix / "bin/brew", "brew")
        self.config = {
            "home": str(self.home), "repo_dir": str(repo), "platform": platform, "profile": profile,
            "user": "tester", "shell_path": "/bin/zsh", "ssh_agent_socket": "SSH_AUTH_SOCK",
            "pnpm_home": str(self.home / "pnpm"), "mise": str(self.bin / "mise"),
            "brew_prefix": str(self.prefix), "pnpm_global_packages": [],
        }
        self.env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "FAKE_LOG": str(self.log),
                    "FAKE_FAIL": "", "MISE_CONFIG_DIR": str(self.home / ".config/mise"),
                    "FAKE_NODE_PATH": str(self.home / ".local/share/mise/installs/node/24/bin/node")}
        self.fragment = self.home / ".config/mise/conf.d/dev-machine-setup.toml"

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
        ("shared/cli-optional.toml", '[packages]\n"brew-cask:codex" = "latest"\n', "not supported on Linux"),
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
    "shared/cli.toml": '[packages]\n"brew:git" = "latest"\n"brew-cask:codex" = { os = "macos" }\n'
                       '[tools]\nnode = "lts"\npnpm = "latest"\n"aqua:openai/codex" = { version = "latest", os = "linux" }\n',
    "mac/cli-optional.toml": '[packages]\n"brew:first" = "latest"\n"brew:second" = "latest"\n'
                             '[tools]\n"aqua:x/broken" = "latest"\n"aqua:x/works" = "latest"\n',
    "mac/gui.toml": '[packages]\n"brew-cask:owned" = "latest"\n"brew-cask:fresh" = "latest"\n"brew-cask:bad" = "latest"\n',
    "mac/app-store.toml": '[packages]\n"mas:111" = { name = "One" }\n"mas:222" = { name = "Two" }\n',
}

# B11: check mode prints the plan but runs and writes nothing.
for platform in ("mac", "linux"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, platform, repo=fixture_repo(directory, CLI_REPO), brew=True)
        machine.config["pnpm_global_packages"] = ["typescript"]
        before = snapshot(machine.base)
        for action in ("cli", "gui", "app-store", "node", "update"):
            machine.run(action, check=True)
        assert machine.calls() == ["ollama list"] and snapshot(machine.base) == before
print("PASS: check mode runs no installers and writes no files")

# Required CLI failures stop; optional failures are reported and the rest continue.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    output = machine.run("cli", FAKE_FAIL="apply --yes brew:first|install aqua:x/broken@latest")
    calls = machine.calls()
    assert calls[:2] == ["mise bootstrap packages apply --yes brew:git brew-cask:codex",
                         "mise bootstrap packages upgrade --yes brew:git brew-cask:codex"], calls
    assert "mise install node@lts pnpm@latest" in calls
    assert "mise bootstrap packages apply --yes brew:second" in calls
    assert "Optional CLI failures: brew:first, aqua:x/broken" in output, output
    assert machine.tools() == {"node": "lts", "pnpm": "latest", "aqua:x/works": "latest"}
    assert "adopt = true" in machine.fragment.read_text()
    assert not any(call.startswith("brew ") for call in calls), "Setup needed the Homebrew executable"
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    fails(lambda: machine.run("cli", FAKE_FAIL="brew:git"), "Required CLI packages failed")
    assert not any("install" in call and "apply" not in call for call in machine.calls())
    machine.log.write_text("")
    fails(lambda: machine.run("cli", FAKE_FAIL="mise install node"), "Required mise tools failed")
    assert "node" not in machine.tools() and not any("brew:first" in call for call in machine.calls())
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, "linux", repo=fixture_repo(directory, CLI_REPO))
    machine.run("cli")
    assert machine.calls()[:3] == ["mise bootstrap packages apply --yes brew:git",
                                   "mise bootstrap packages upgrade --yes brew:git",
                                   "mise install node@lts pnpm@latest aqua:openai/codex@latest"]
for brew in (True, False):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=brew)
        (machine.prefix / "Caskroom/codex/.metadata").mkdir(parents=True)
        output = machine.run("cli")
        calls = machine.calls()
        assert calls[0] == "mise bootstrap packages apply --yes brew:git"
        assert ("brew upgrade --cask --greedy codex" in calls) == brew
        assert brew or "Homebrew-owned cask codex unchanged" in output
        assert not any("brew-cask:codex" in call for call in calls)
print("PASS: required CLI failures stop setup; optional failures are reported; Linux uses tool providers; "
      "Homebrew-owned casks stay Brew-updated")

# The disabled tldr formula is removed before tlrc only when Homebrew can do it.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    (machine.prefix / "Cellar/tldr").mkdir(parents=True)
    fails(lambda: machine.run("cli"), "tldr")
    assert machine.calls() == []
    fake(machine.prefix / "bin/brew", "brew")
    machine.run("cli")
    assert machine.calls()[0] == "brew uninstall tldr"
print("PASS: the disabled tldr formula is uninstalled before CLI packages")

# GUI and App Store: Mac only, Homebrew-owned casks stay with Homebrew, failures reported.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, "linux", repo=fixture_repo(directory, CLI_REPO), brew=True)
    assert "only on macOS" in machine.run("gui") and "only on macOS" in machine.run("app-store")
    assert machine.calls() == []
for brew in (True, False):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=brew)
        (machine.prefix / "Caskroom/owned/.metadata").mkdir(parents=True)
        output = machine.run("gui", FAKE_FAIL="apply --yes brew-cask:bad")
        calls = machine.calls()
        assert ("brew upgrade --cask --greedy owned" in calls) == brew
        assert not any("brew-cask:owned" in call for call in calls)
        assert calls[-1] == "mise bootstrap packages apply --yes brew-cask:bad"
        assert "mise bootstrap packages apply --yes brew-cask:fresh" in calls
        assert "mise bootstrap packages upgrade --yes brew-cask:fresh" in calls
        assert "GUI cask failures: bad" in output
        assert brew or "Homebrew-owned cask owned unchanged" in output
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    output = machine.run("app-store", FAKE_FAIL="mas get 111|mas install 111|mas get 222")
    calls = machine.calls()
    assert calls[0] == "mdimport /Applications"
    assert f"sudo {machine.bin}/mas install 222" in calls and "mas install 222" in calls
    assert "App Store installation failures: mas:111 (One)" in output, output
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), commands=("sudo", "mdimport"))
    fails(lambda: machine.run("app-store", FAKE_FAIL="brew:mas"), "mas CLI")
print("PASS: GUI and App Store failures are reported, Homebrew-owned casks stay Brew-updated, both Mac only")

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
        write(machine.home / ".nvm/versions/node/v22/lib/node_modules/eslint/package.json", "{}")
        write(machine.home / ".nvm/versions/node/v22/lib/node_modules/npm/package.json", "{}")

        fails(lambda: machine.run("node", FAKE_FAIL="mise install node"), "Installing Node and pnpm")
        assert "node" not in machine.tools() and "brew unlink node" not in machine.calls()
        assert "nvm.sh" in (machine.home / ".bashrc").read_text()
        fails(lambda: machine.run("node", FAKE_NODE_PATH=str(machine.prefix / "bin/node")), "did not run")
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
        output = machine.run("node")
        assert "Node runtime: eslint\n" in output, output
print("PASS: Node is proven before Homebrew node is unlinked; failures stop setup; config and dotfiles untouched")

with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO))
    (machine.home / ".config").mkdir()
    write(machine.base / "elsewhere/conf.d/keep.toml", "")
    (machine.home / ".config/mise").symlink_to(machine.base / "elsewhere")
    fails(lambda: machine.run("node"), "symlink")
    assert not (machine.base / "elsewhere/conf.d/dev-machine-setup.toml").exists()
print("PASS: the runtime fragment is never written through a symlinked mise configuration")

# B10/B12: updates continue past failures, skip missing tools, and fail at the end.
with tempfile.TemporaryDirectory() as directory:
    machine = Machine(directory, "linux", repo=fixture_repo(directory, CLI_REPO), commands=("mas",))
    output = machine.run("update")
    for name in ("Homebrew metadata", "mise tools", "npm globals", "pnpm globals", "Mac App Store", "Ollama models"):
        assert f"{name}: skipped" in output, output
    assert "mise bootstrap packages upgrade --yes brew:git" in machine.calls()
    assert not any(call.startswith(("mas", "brew")) for call in machine.calls())
for status in ("ok", "fail"):
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo=fixture_repo(directory, CLI_REPO), brew=True)
        write(machine.fragment, '[tools]\nnode = "lts"\npnpm = "latest"\n')
        (machine.prefix / "Caskroom/owned/.metadata").mkdir(parents=True)
        fail = "-- npm update -g|ollama pull first:latest" if status == "fail" else ""
        if status == "ok":
            output = machine.run("update")
        else:
            error = fails(lambda: machine.run("update", FAKE_FAIL=fail), "Update failures: npm globals, Ollama models")
            output = error.output
        calls = machine.calls()
        for command in ("brew update", "brew upgrade --formula", "brew upgrade --cask", "brew cleanup -s",
                        "mise upgrade node pnpm", "mise exec -- pnpm update -g", "mas upgrade"):
            assert command in calls, (command, calls)
        native = next(call for call in calls if call.startswith("mise bootstrap packages upgrade"))
        assert native == "mise bootstrap packages upgrade --yes brew-cask:bad brew-cask:codex brew-cask:fresh"
        pulls = [call for call in calls if call.startswith("ollama pull")]
        assert pulls == (["ollama pull first:latest"] if status == "fail"
                         else ["ollama pull first:latest", "ollama pull second:latest"])
        assert "pnpm globals: completed" in output and "Mac App Store: completed" in output
print("PASS: updates skip missing components, keep going after failures, and report them at the end")
