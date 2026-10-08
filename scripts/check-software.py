#!/usr/bin/env python3
"""Check package previews, Homebrew Bundle installs and the mise tool step with fake tools.

Nothing is installed: mise, Homebrew and mdimport are replaced by logging
stand-ins in temporary directories, and shell files live in a temporary home.
"""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
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
# mise ls prints a stand-in listing so the preview shows what the real command returns.
MISE_PRE = """if [ "$3" = ls ]; then echo "deno  latest"; fi"""

FIXTURE = {
    "shared/Brewfile.cli": 'brew "git"\n',
    "mac/Brewfile.cli": 'brew "mas"\n',
    "mac/Brewfile.gui": 'cask "firefox"\n',
    "mac/Brewfile.app-store": 'mas "Xcode", id: 497799835\n',
    "mac/personal/Brewfile.cli": 'brew "ollama"\n',
    "mac/personal/Brewfile.gui": 'cask "steam"\n',
    "mac/work/Brewfile.cli": 'brew "awscli"\n',
    "linux/personal/Brewfile.cli": 'brew "htop"\n',
}
LINK = "mise -E personal dot apply --yes ~/.config/mise/conf.d/dev-machine-setup.toml"


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
        fake(self.bin / "mise", "mise", pre=MISE_PRE)
        fake(self.bin / "mdimport", "mdimport")
        fake(self.prefix / "bin/brew", "brew", pre=BREW_PRE)
        self.config = {
            "platform": platform, "profile": profile, "repo_dir": str(repo), "home": str(self.home),
            "mise": str(self.bin / "mise"), "brew": str(self.prefix / "bin/brew"),
            "brew_prefix": str(self.prefix), "pnpm_home": str(self.home / "pnpm"),
            "steps": {name: True for name in STEPS},
        }
        self.env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "FAKE_LOG": str(self.log),
                    "FAKE_FAIL": ""}

    def run(self, action, check=False, **env):
        saved = dict(os.environ)
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
                              "mac/Brewfile.gui", "mac/personal/Brewfile.gui", "mac/Brewfile.app-store"],
        ("mac", "work"): ["shared/Brewfile.cli", "mac/Brewfile.cli", "mac/work/Brewfile.cli",
                          "mac/Brewfile.gui", "mac/Brewfile.app-store"],
        ("linux", "personal"): ["shared/Brewfile.cli", "linux/personal/Brewfile.cli"],
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
            assert "mise tools from mise/conf.d/tools.toml" in output and "deno  latest" in output, output
            assert all(path.is_relative_to(repo / "packages") for path in seen), seen
            assert machine.calls() == [f"mise -E {profile} ls --current"], machine.calls()
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        fails(lambda: machine.run("packages", FAKE_FAIL="ls --current"), "could not list the declared tools")
    print("PASS: packages preview lists the selected layer files in order, marks disabled steps, "
          "reads only packages/ and lists the mise tools")

    # cli --------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        output = machine.run("cli")
        bundle = bundle_call(machine)
        assert "[no auto-update]" in bundle, bundle
        ordered(bundle, 'brew "git"', 'brew "mas"', 'brew "ollama"')
        calls = machine.calls()
        assert calls[-2:] == [LINK, "mise -E personal install"], calls
        assert "brew uninstall" not in "".join(calls), calls
        assert machine.issues == []

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo, "linux", "work")
        machine.run("cli")
        assert machine.calls()[-2:] == [LINK.replace("personal", "work"), "mise -E work install"], machine.calls()

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
        assert not any(call.startswith("mise") for call in machine.calls()), machine.calls()

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        fails(lambda: machine.run("cli", FAKE_FAIL="dot apply"), "Could not link")
        assert not any(call.endswith(" install") for call in machine.calls()), machine.calls()

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        fails(lambda: machine.run("cli", FAKE_FAIL="personal install"), "mise tools failed to install")
    print("PASS: cli pipes the layered Brewfile.cli to brew bundle, removes replaced packages first, "
          "links the tools file for the profile, then installs the tools, and stops on any failure")

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
    print("PASS: gui and app-store skip on Linux, index /Applications before mas, "
          "and report bundle failures as one issue")

    # node ---------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        before = snapshot(machine.home)
        assert "nothing to configure on macOS" in machine.run("node")
        assert machine.calls() == [] and snapshot(machine.home) == before

    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo, "linux")
        external = write(machine.base / "dotfiles/zshrc", "# external\n")
        (machine.home / ".zshrc").symlink_to(external)
        machine.run("node")
        bashrc = (machine.home / ".bashrc").read_text()
        assert f"export PNPM_HOME={machine.home / 'pnpm'}" in bashrc and "# BEGIN dev-machine Node and pnpm" in bashrc
        assert external.read_text() == "# external\n"
        assert machine.calls() == []
    print("PASS: node adds the PNPM_HOME block on Linux only, never edits a symlinked shell file, "
          "and runs no commands")

    # check mode ----------------------------------------------------------------
    with tempfile.TemporaryDirectory() as directory:
        machine = Machine(directory, repo)
        before = snapshot(machine.home)
        output = machine.run("cli", check=True)
        assert "$ " in output and "brew bundle install --file=-" in output and "(check: not run)" in output
        assert ("dot apply --yes '~/.config/mise/conf.d/dev-machine-setup.toml'" in output
                and "mise -E personal install" in output), output
        assert machine.calls() == ["brew list --cask --versions claude-code@latest"], machine.calls()
        assert snapshot(machine.home) == before
    print("PASS: --check prints the bundle, link and install commands without running them")
