#!/usr/bin/env python3
"""Check package previews, Homebrew Bundle installs, mise tools and pnpm globals with fake tools.

Nothing is installed: mise, Homebrew and mdimport are replaced by logging
stand-ins in temporary directories, and the mise fragment lives in a temporary home.
"""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import tomllib
from unittest import mock

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from devsetup import software  # noqa: E402
from devsetup.config import STEPS  # noqa: E402

FAKE = """#!/bin/sh
line="{name} $*"
{pre}
printf '%s\\n' "$line" >> "$FAKE_LOG"
IFS='|'
for pattern in $FAKE_FAIL; do
  case "$line" in *"$pattern"*) exit 1 ;; esac
done
exit 0
"""
# brew bundle logs its Brewfile from stdin on the same line, joined by "; ".
# brew list reports the claude-code@latest cask as installed only when asked to.
BREW_PRE = """if [ "$1" = bundle ]; then
  line="$line${HOMEBREW_NO_AUTO_UPDATE:+ [no auto-update]}: $(sed 's/$/;/' | tr '\\n' ' ')"
fi
if [ "$1" = list ]; then printf '%s\\n' "$line" >> "$FAKE_LOG"; [ -n "$FAKE_CASK_INSTALLED" ]; exit $?; fi"""

FIXTURE = {
    "shared/Brewfile.cli": 'brew "git"\n',
    "shared/tools.cli.toml": '[tools]\nuv = "latest"\nripgrep = "14"\n',
    "shared/tools.node.toml": '[tools]\nnode = "24"\npnpm = "latest"\n',
    "mac/Brewfile.cli": 'brew "mas"\n',
    "mac/Brewfile.gui": 'cask "firefox"\n',
    "mac/Brewfile.app-store": 'mas "Xcode", id: 497799835\n',
    "mac/tools.cli.toml": '[tools]\nripgrep = "15"\n',
    "mac/personal/Brewfile.cli": 'brew "ollama"\n',
    "mac/personal/Brewfile.gui": 'cask "steam"\n',
    "mac/work/Brewfile.cli": 'brew "awscli"\n',
    "linux/tools.cli.toml": '[tools]\nfzf = "latest"\n',
    "linux/tools.node.toml": '[tools]\nnode = "22"\n',
    "linux/personal/Brewfile.cli": 'brew "htop"\n',
}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def fake(path, name, pre=""):
    write(path, FAKE.format(name=name, pre=pre)).chmod(0o755)


def fixture_repo(directory, files=FIXTURE):
    repo = Path(directory).resolve() / "repo"
    for relative, text in files.items():
        write(repo / "packages" / relative, text)
    return repo


def snapshot(path):
    return sorted((str(item.relative_to(path)), item.read_bytes() if item.is_file() else b"")
                  for item in path.rglob("*"))


class Machine:
    """A temporary home, Homebrew prefix and fake commands for one scenario."""

    def __init__(self, directory, repo, platform="mac", profile="personal"):
        self.base = Path(directory).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        self.prefix = self.base / "prefix"
        self.bin = self.base / "bin"
        self.log = write(self.base / "log", "")
        fake(self.bin / "mise", "mise")
        fake(self.bin / "mdimport", "mdimport")
        fake(self.prefix / "bin/brew", "brew", pre=BREW_PRE)
        self.fragment = self.home / ".config/mise/conf.d/dev-machine-setup.toml"
        self.config = {
            "platform": platform, "profile": profile, "repo_dir": str(repo), "home": str(self.home),
            "mise": str(self.bin / "mise"), "brew": str(self.prefix / "bin/brew"),
            "brew_prefix": str(self.prefix), "pnpm_home": str(self.home / "pnpm"),
            "pnpm_global_packages": [], "steps": {name: True for name in STEPS},
        }
        self.env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "FAKE_LOG": str(self.log),
                    "FAKE_FAIL": "", "MISE_CONFIG_DIR": str(self.home / ".config/mise")}

    def run(self, action, check=False, **env):
        saved = dict(os.environ)
        os.environ.pop("XDG_CONFIG_HOME", None)
        os.environ.update(self.env, **env)
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                self.issues = software.run(action, self.config, check=check)
            return output.getvalue()
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


def bundle_call(machine):
    lines = [line for line in machine.calls() if line.startswith("brew bundle install --file=- ")]
    assert len(lines) == 1, machine.calls()
    return lines[0]


def ordered(text, *parts):
    positions = [text.find(part) for part in parts]
    assert -1 not in positions and positions == sorted(positions), (parts, text)


with tempfile.TemporaryDirectory() as fixture_dir:
    repo = fixture_repo(fixture_dir)

    # packages preview ------------------------------------------------------
    expected = {
        ("mac", "personal"): ["shared/Brewfile.cli", "mac/Brewfile.cli", "mac/personal/Brewfile.cli",
                              "mac/Brewfile.gui", "mac/personal/Brewfile.gui", "mac/Brewfile.app-store",
                              "shared/tools.cli.toml", "mac/tools.cli.toml", "shared/tools.node.toml"],
        ("mac", "work"): ["shared/Brewfile.cli", "mac/Brewfile.cli", "mac/work/Brewfile.cli",
                          "mac/Brewfile.gui", "mac/Brewfile.app-store",
                          "shared/tools.cli.toml", "mac/tools.cli.toml", "shared/tools.node.toml"],
        ("linux", "personal"): ["shared/Brewfile.cli", "linux/personal/Brewfile.cli",
                                "shared/tools.cli.toml", "linux/tools.cli.toml",
                                "shared/tools.node.toml", "linux/tools.node.toml"],
    }
    for (platform, profile), files in expected.items():
        with tempfile.TemporaryDirectory() as directory:
            machine = Machine(directory, repo, platform, profile)
            machine.config["steps"]["gui"] = False
            seen = []
            original = Path.read_text

            def spy(self, *args, **kwargs):
                seen.append(Path(self).resolve())
                return original(self, *args, **kwargs)

            with mock.patch.object(Path, "read_text", spy):
                output = machine.run("packages")
            listed = [line.strip() for line in output.splitlines() if line.startswith("  packages/")]
            assert [item.split(" ")[0] for item in listed] == [f"packages/{name}" for name in files], listed
            for item in listed:
                assert item.endswith("(skipped by configuration)") == ("Brewfile.gui" in item), item
            assert "uv@latest ripgrep@15" in output or platform == "linux", output
            assert all(path.is_relative_to(repo / "packages") for path in seen), seen
            assert machine.calls() == [] and not machine.fragment.exists()
    print("PASS: packages preview lists the selected layer files in order, marks disabled steps, "
          "and reads only packages/")

    # cli --------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        write(machine.fragment, '[tools]\npython = "3.12"\n')
        output = machine.run("cli")
        bundle = bundle_call(machine)
        assert "[no auto-update]" in bundle, bundle
        ordered(bundle, 'brew "git"', 'brew "mas"', 'brew "ollama"')
        assert "mise install uv@latest ripgrep@15" in machine.calls(), machine.calls()
        assert machine.tools() == {"python": "3.12", "uv": "latest", "ripgrep": "15"}, machine.tools()
        assert "brew uninstall" not in "".join(machine.calls()), machine.calls()
        assert machine.issues == []

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        (machine.prefix / "Cellar/tldr").mkdir(parents=True)
        machine.run("cli", FAKE_CASK_INSTALLED="1")
        calls = machine.calls()
        assert calls[:3] == ["brew uninstall tldr", "brew list --cask --versions claude-code@latest",
                             "brew uninstall --cask claude-code@latest"], calls
        assert calls[3].startswith("brew bundle install"), calls

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        fails(lambda: machine.run("cli", FAKE_FAIL="brew bundle"), "CLI packages failed")
        assert not any(call.startswith("mise install") for call in machine.calls()), machine.calls()
        assert not machine.fragment.exists()

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        fails(lambda: machine.run("cli", FAKE_FAIL="mise install"), "mise tools failed to install")
        assert not machine.fragment.exists()
    print("PASS: cli pipes the layered Brewfile.cli to brew bundle, installs and records merged tools, "
          "removes replaced packages first, and records nothing after a failure")

    # gui and app-store --------------------------------------------------------
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo, "linux")
        for action in ("gui", "app-store"):
            assert "only on macOS" in machine.run(action) and machine.issues == []
        assert machine.calls() == []

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        machine.run("gui")
        ordered(bundle_call(machine), 'cask "firefox"', 'cask "steam"')
        machine.run("gui", FAKE_FAIL="brew bundle")
        assert len(machine.issues) == 1 and "GUI apps" in machine.issues[0], machine.issues

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        machine.run("app-store", FAKE_FAIL="brew bundle")
        assert len(machine.issues) == 1 and "App Store apps" in machine.issues[0], machine.issues
        calls = machine.calls()
        assert calls[0] == "mdimport /Applications" and calls[1].startswith("brew bundle install"), calls
        assert 'mas "Xcode", id: 497799835' in calls[1], calls
        assert not machine.fragment.exists()
    print("PASS: gui and app-store skip on Linux, index /Applications before mas, "
          "and report bundle failures as one issue")

    # node ---------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        machine.config["pnpm_global_packages"] = ["foo", "bar"]
        machine.run("node")
        calls = machine.calls()
        assert calls == ["mise install node@24 pnpm@latest",
                         "mise exec node@24 pnpm@latest -- pnpm add -g foo@latest",
                         "mise exec node@24 pnpm@latest -- pnpm add -g bar@latest"], calls
        assert machine.tools() == {"node": "24", "pnpm": "latest"}, machine.tools()
        assert (machine.home / "pnpm/bin").is_dir()
        assert not (machine.home / ".zshrc").exists() and not (machine.home / ".bashrc").exists()

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo, "linux")
        machine.config["pnpm_global_packages"] = ["foo"]
        external = write(machine.base / "dotfiles/zshrc", "# external\n")
        (machine.home / ".zshrc").symlink_to(external)
        machine.run("node")
        assert "mise install node@22 pnpm@latest" in machine.calls(), machine.calls()
        bashrc = (machine.home / ".bashrc").read_text()
        assert f"export PNPM_HOME={machine.home / 'pnpm'}" in bashrc and "# BEGIN dev-machine Node and pnpm" in bashrc
        assert external.read_text() == "# external\n"
        assert machine.tools() == {"node": "22", "pnpm": "latest"}, machine.tools()
        fails(lambda: machine.run("node", FAKE_FAIL="pnpm add"), "pnpm global package foo failed")
    print("PASS: node installs and records tools.node.toml, adds the PNPM_HOME block on Linux only, "
          "never edits a symlinked shell file, and fails on a pnpm error")

    # fragment safety ------------------------------------------------------------
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        before = snapshot(machine.home)
        output = machine.run("cli", check=True)
        assert "$ " in output and "brew bundle install --file=-" in output and "(check: not run)" in output
        assert "Recording mise tools" in output and "(check: not written)" in output, output
        assert machine.calls() == ["brew list --cask --versions claude-code@latest"], machine.calls()
        assert snapshot(machine.home) == before

    for name in ("config", "mise"):
        with tempfile.TemporaryDirectory() as directory:
            machine = Machine(directory, repo)
            target = machine.base / "elsewhere"
            if name == "config":
                target.mkdir()
                (machine.home / ".config").symlink_to(target)
            else:
                (target / "mise").mkdir(parents=True)
                (machine.home / ".config").mkdir()
                (machine.home / ".config/mise").symlink_to(target / "mise")
            fails(lambda: machine.run("node"), "Refusing to access the mise runtime fragment through symlink")
            assert list(target.rglob("*.toml")) == []

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        real = machine.base / "real"
        real.mkdir()
        link = machine.base / "link"
        link.symlink_to(real)
        fails(lambda: machine.run("node", MISE_CONFIG_DIR="", XDG_CONFIG_HOME=str(link / "xdg")),
              "Refusing to access the mise runtime fragment through symlink")
        fails(lambda: machine.run("node", MISE_CONFIG_DIR=str(link / "mise")),
              "Refusing to access the mise runtime fragment through symlink")
        assert list(real.rglob("*.toml")) == []

    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        machine = Machine(directory, repo)
        alias = Path("/tmp") / Path(directory).name / "mise"
        machine.run("node", MISE_CONFIG_DIR=str(alias))
        assert tomllib.loads((alias / "conf.d/dev-machine-setup.toml").read_text())["tools"] == {
            "node": "24", "pnpm": "latest"}
    print("PASS: the fragment refuses symlinked ancestors, accepts the /tmp alias, "
          "and --check prints commands without writing")

# malformed inventories ---------------------------------------------------------
with tempfile.TemporaryDirectory() as directory:
    repo = fixture_repo(directory, {**FIXTURE, "shared/tools.cli.toml": "[tools\nbroken\n"})
    base = Path(directory) / "machine"
    base.mkdir()
    machine = Machine(base, repo)
    fails(lambda: machine.run("cli"), "Malformed tool inventory packages/shared/tools.cli.toml")
    assert not any(call.startswith("mise install") for call in machine.calls())
print("PASS: a malformed tools.*.toml names the file and installs nothing")
