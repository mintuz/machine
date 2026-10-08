#!/usr/bin/env python3
"""Check config selection, Remote Login action routing and the installer prompts and hand-off.

Everything runs in temporary directories with substitute commands: no sudo,
network, package installs, or changes to this machine.
"""
import contextlib
import json
import os
from pathlib import Path
import pty
import shlex
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from devsetup import cli, config as config_module  # noqa: E402
from devsetup.config import ConfigError  # noqa: E402

FAKE_MISE = "/opt/fake/bin/mise"


def expect_error(message, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except (ConfigError, RuntimeError) as error:
        assert message in str(error), f"expected {message!r} in {error!r}"
        return error
    raise AssertionError(f"expected an error containing {message!r}")


def command(directory, name, body):
    path = Path(directory) / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return path


# Config selection -----------------------------------------------------------
with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory)
    ubuntu = fixture / "os-release-ubuntu"
    ubuntu.write_text('NAME="Ubuntu"\nID=ubuntu\n')
    fedora = fixture / "os-release-fedora"
    fedora.write_text("ID=fedora\n")
    home = fixture / "home"
    home.mkdir()
    real_home = home.resolve()

    def load(system="Darwin", machine="arm64", environ=None, **kwargs):
        kwargs.setdefault("mise", FAKE_MISE)
        kwargs.setdefault("euid", 501)
        return config_module.load(repo_dir=root, system=system, machine=machine, os_release=ubuntu,
                                  environ=environ if environ is not None else {"HOME": str(home)},
                                  **kwargs)

    for system, machine, platform in (("Darwin", "arm64", "mac"), ("Linux", "aarch64", "linux"),
                                      ("Linux", "arm64", "linux")):
        for profile in ("personal", "work"):
            config = load(system, machine, profile=profile)
            assert config["platform"] == platform and config["profile"] == profile
            assert config["home"] == str(real_home) and config["repo_dir"] == str(root)
            assert config["brew_prefix"] == ("/opt/homebrew" if platform == "mac" else "/home/linuxbrew/.linuxbrew")
            assert ("tailscale_cli" in config) == ("remote_login_sshd_file" in config) == (platform == "mac")
            assert config["steps"] == {"remote-login": False} and config["revoke_remote_login"] is False
            flagged = load(system, machine, profile=profile, flags={"remote-login": True})
            assert flagged["steps"]["remote-login"] is True
            print(f"PASS: {platform}/{profile} ({machine}) selects its defaults and per-run overrides")
    assert load()["profile"] == "personal"

    expect_error("Unsupported profile", load, profile="../personal")
    expect_error("Unsupported profile", load, environ={"HOME": str(home), "DEVSETUP_PROFILE": "staging"})
    expect_error("Conflicting profiles", load, profile="work",
                 environ={"HOME": str(home), "DEVSETUP_PROFILE": "personal"})
    assert load(profile="work", environ={"HOME": str(home), "DEVSETUP_PROFILE": "work"})["profile"] == "work"
    print("PASS: invalid and conflicting profiles are rejected")
    expect_error("Only Ubuntu", config_module.load, repo_dir=root, system="Linux", machine="aarch64",
                 os_release=fedora, environ={"HOME": str(home)}, mise=FAKE_MISE, euid=501)
    expect_error("Apple silicon", load, machine="x86_64")
    expect_error("ARM64", load, "Linux", "x86_64")
    expect_error("Only macOS and Ubuntu", load, "FreeBSD", "arm64")
    expect_error("not root", load, euid=0)
    expect_error("absolute", load, mise="mise")
    print("PASS: unsupported OS, distribution, architecture, root, and relative mise are rejected")

    override = fixture / "local.toml"
    override.write_text('remote_login_sshd = ["/fake/sshd", "-f", "x"]\ncustom_note = "kept"\n'
                        '[linux]\nbrew_prefix = "~/custom-brew"\n[mac]\ntailscale_cli = "/fake/tailscale"\n')
    merged = load("Linux", "aarch64", override=override)
    assert merged["custom_note"] == "kept"
    assert merged["brew_prefix"] == f"{real_home}/custom-brew" and "tailscale_cli" not in merged
    assert merged["remote_login_sshd"] == ["/fake/sshd", "-f", "x"]
    assert load(override=override)["tailscale_cli"] == "/fake/tailscale"
    for text, message in (("brew_prefix = [", "Invalid TOML"), ('remote_login_sources = "100.64.0.0/10"', "list"),
                          ("[steps]\nremote-login = 'yes'", "true or false"),
                          ("[steps]\ndotfiles = true", "unknown step"), ('home = "/tmp"', "cannot be set"),
                          ('machine_type = "work"', "cannot be set"), ('profile = "work"', "cannot be set"),
                          ('[linux]\nprofile = "work"', "cannot be set"),
                          ("remote_login_sudo = []", "cannot be set"),
                          ("[linux]\nremote_login_port = 2222", "cannot be set"),
                          ('[linux]\nbrew_prefix = "brew"', "absolute")):
        override.write_text(text + "\n")
        expect_error(message, load, "Linux", "aarch64", override=override)
    expect_error("Cannot read settings file", load, override=fixture / "missing.toml")
    override.write_text('[steps]\nremote-login = true\n[linux.steps]\nremote-login = false\n')
    assert load(override=override)["steps"]["remote-login"]
    assert not load("Linux", "aarch64", override=override)["steps"]["remote-login"]
    assert not load(override=override, flags={"remote-login": False})["steps"]["remote-login"], \
        "an explicit flag must win over the override file"
    print("PASS: the override file merges per platform, steps merge by key with explicit precedence, "
          "and malformed settings stop before changes")


# Contradictory explicit choices must fail rather than silently turn into no-ops.
for argv in (["remote-login", "--keep-remote-login"], ["remote-login", "--profile", "staging"], ["install"],
             ["ssh"], ["remote-login-check", "--revoke-remote-login"], ["remote-login", "--skip", "ssh"],
             ["remote-login", "--config"]):
    with open(os.devnull, "w") as quiet, contextlib.redirect_stderr(quiet):
        try:
            cli.parse_args(argv)
        except SystemExit as exit_status:
            assert exit_status.code == 2
        else:
            raise AssertionError(f"{argv} was accepted")


# install.sh prompts and hand-off --------------------------------------------
with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory)
    installer = fixture / "install.sh"
    source = (root / "install.sh").read_text()
    assert "os_release=/etc/os-release\n" in source
    installer.write_text(source.replace("os_release=/etc/os-release\n",
                                        "os_release=" + shlex.quote(str(fixture / "os-release")) + "\n"))
    installer.chmod(0o755)
    (fixture / "os-release").write_text("ID=ubuntu\n")
    (fixture / "scripts").mkdir()
    (fixture / "scripts/bootstrap-macos.sh").write_text('echo "os-bootstrap:macos"\n')
    (fixture / "scripts/bootstrap-ubuntu.sh").write_text('echo "os-bootstrap:ubuntu"\n')
    (fixture / "scripts/bootstrap-homebrew.sh").write_text(":\n")
    (fixture / "scripts/bootstrap-mise.sh").write_text('mise_bin="$repo_dir/bin/mise"\n')
    (fixture / "bin").mkdir()
    command(fixture / "bin", "mise", 'echo "mise: $*"')
    command(fixture / "scripts", "with-sudo-askpass.sh", 'echo "wrapper: $*"; exec "$@"')
    command(fixture / "bin", "uname", '''case "$1" in
  -m) printf '%s\\n' "${TEST_MACHINE:-arm64}" ;;
  *) printf '%s\\n' "${TEST_SYSTEM:-Darwin}" ;;
esac''')
    home = fixture / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh/config").write_text("# existing SSH configuration\n")
    env = dict(os.environ, PATH=str(fixture / "bin") + os.pathsep + os.environ["PATH"], HOME=str(home))
    for variable in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "DEVSETUP_PROFILE"):
        env.pop(variable, None)

    def mise_lines(stdout):
        return [line for line in stdout.splitlines() if line.startswith("mise: ")]

    cases = [
        ("Darwin", [], None, "work bootstrap --yes", False),
        ("Darwin", [], "y\n", "work,ssh bootstrap --yes", True),
        ("Darwin", [], "n\n", "work bootstrap --yes", False),
        ("Darwin", [], "\n", "work bootstrap --yes", False),
        ("Darwin", [], "maybe\nyes\n", "work,ssh bootstrap --yes", True),
        ("Darwin", ["--1password-ssh"], None, "work,ssh bootstrap --yes", True),
        ("Darwin", ["--keep-ssh", "--skip-dotfiles"], None, "work bootstrap --yes --skip repos,task", False),
        ("Darwin", ["--skip", "cli", "--skip", "osx", "--skip", "zsh"], None,
         "work bootstrap --yes --skip packages,tools,macos-defaults,user", False),
        ("Linux", [], None, "work bootstrap --yes", False),
        ("Linux", [], "n\n\n", "work bootstrap --yes", False),
        ("Linux", [], "y\nn\n", "work,ssh bootstrap --yes --skip repos,task", True),
        ("Linux", [], "n\nmaybe\ny\n", "work bootstrap --yes", False),
        ("Linux", ["--keep-ssh", "--skip-dotfiles"], None, "work bootstrap --yes --skip repos,task", False),
        ("Linux", ["--1password-ssh", "--dotfiles"], None, "work,ssh bootstrap --yes", True),
        ("Linux", ["--skip", "ssh", "--skip", "dotfiles", "--skip", "gui"], None,
         "work bootstrap --yes --skip packages,repos,task", False),
    ]
    for system, args, answer, expected, tracks in cases:
        env["TEST_SYSTEM"] = system
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(["bash", str(installer), "work", *args],
                                       stdin=slave if answer is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            if answer is not None:
                os.write(master, answer.encode())
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stdout + stderr
            assert ("os-bootstrap:macos" if system == "Darwin" else "os-bootstrap:ubuntu") in stdout, stdout
            lines = mise_lines(stdout)
            assert lines[-1] == f"mise: -E {expected}", (args, answer, lines)
            assert f"wrapper: {fixture}/bin/mise -E {expected}" in stdout, stdout
            # SSH opt-in keeps the existing client configuration in mise history first.
            assert (f"mise: dot track --yes {home}/.ssh/config" in lines) == tracks, (args, answer, lines)
            if system == "Linux" and answer is not None:
                assert "[Y/n]" in stderr, stderr
            if answer is not None:
                assert "[y/N]" in stderr, stderr
        finally:
            os.close(master)
            os.close(slave)

    env["TEST_SYSTEM"] = "Darwin"
    for args in (["--bootstrap-only"], ["--bootstrap-only", "--1password-ssh"]):
        result = subprocess.run(["bash", str(installer), *args], env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert mise_lines(result.stdout) == ["mise: -E personal bootstrap --only files,user --yes"], result.stdout
        assert "[y/N]" not in result.stderr
    shutil.copy(root / "new-mac.sh", fixture / "new-mac.sh")
    result = subprocess.run(["bash", str(fixture / "new-mac.sh"), "--keep-ssh"],
                            env=dict(env, DEVSETUP_PROFILE="work"), text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert mise_lines(result.stdout) == ["mise: -E work bootstrap --only files,user --yes"], result.stdout
    result = subprocess.run(["bash", str(installer), "--keep-ssh"], text=True, capture_output=True,
                            env=dict(env, TEST_SYSTEM="Linux", TEST_MACHINE="x86_64"))
    assert result.returncode == 1 and "ARM64" in result.stderr and "os-bootstrap" not in result.stdout
    (fixture / "os-release").write_text("ID=fedora\n")
    result = subprocess.run(["bash", str(installer), "--keep-ssh"], text=True, capture_output=True,
                            env=dict(env, TEST_SYSTEM="Linux", TEST_MACHINE="aarch64"))
    assert result.returncode == 1 and "Only Ubuntu" in result.stderr and "os-bootstrap" not in result.stdout
    print("PASS: startup SSH/dotfiles prompts, defaults, opt-outs, --skip mapping, ARM64/Ubuntu guards, "
          "and bootstrap-only mode")


# The installer never enables Remote Login; the launcher checks prerequisites ---
if sys.platform == "darwin" and os.uname().machine == "arm64":
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory).resolve()
        binary = fixture / "bin"
        binary.mkdir()
        calls = fixture / "calls"
        calls.write_text("")
        mise = command(binary, "mise", f'echo "mise $*" >> "{calls}"')
        home = fixture / "home"
        home.mkdir()
        repo = fixture / "installer-repo"
        repo.mkdir()
        shutil.copytree(root / "scripts", repo / "scripts")
        for name in ("install.sh", "remote-login.sh", "defaults.toml"):
            shutil.copy(root / name, repo / name)
        for name in ("bootstrap-macos.sh", "bootstrap-homebrew.sh"):
            (repo / "scripts" / name).write_text(":\n")
        (repo / "scripts/bootstrap-mise.sh").write_text(f"mise_bin={shlex.quote(str(mise))}\n")
        command(repo / "scripts", "with-sudo-askpass.sh", 'exec "$@"')
        (home / ".ssh").mkdir()
        keys = home / ".ssh/authorized_keys"
        keys.write_text("preserve existing authorised keys\n")
        service = fixture / "remote-service"
        service.write_text("unchanged")
        launchctl = command(binary, "launchctl-fixture", f'echo changed > "{service}"; exit 99')
        policy = fixture / "remote choice.toml"
        policy.write_text(f"remote_login_launchctl = {json.dumps(str(launchctl))}\n"
                          'remote_login_public_keys = ["not-prepared.pub"]\n[steps]\nremote-login = true\n')
        process_env = {**os.environ, "HOME": str(home), "PATH": f"{binary}{os.pathsep}{os.environ['PATH']}",
                       "DEVSETUP_PROFILE": "personal", "MISE_ORIGINAL_CWD": str(fixture)}
        for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
            process_env.pop(name, None)
        result = subprocess.run([str(repo / "install.sh"), "--keep-ssh"], stdin=subprocess.DEVNULL,
                                cwd=fixture, env=process_env, text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert calls.read_text().splitlines() == ["mise -E personal bootstrap --yes"], calls.read_text()
        assert keys.read_text() == "preserve existing authorised keys\n"
        assert service.read_text() == "unchanged"
        # Execute the real dispatcher through the launcher, without installing mise/Python.
        command(binary, "mise", f'printf "%s\\n" {shlex.quote(sys.executable)}')
        result = subprocess.run([str(repo / "remote-login.sh"), "--config", policy.name],
                                cwd=fixture, env=process_env, text=True, capture_output=True, timeout=15)
        assert result.returncode == 1 and "not-prepared.pub" in result.stderr, result.stdout + result.stderr
        assert keys.read_text() == "preserve existing authorised keys\n"
        assert service.read_text() == "unchanged"
        print("PASS: installation hands everything to mise bootstrap without Remote Login; "
              "the separate launcher checks prerequisites before changing access")
