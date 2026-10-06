#!/usr/bin/env python3
"""Check config selection, action routing, the installer prompts, and host configuration.

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
from devsetup import cli, config as config_module, host  # noqa: E402
from devsetup.config import ConfigError  # noqa: E402

CONTRACT_KEYS = {
    "home", "repo_dir", "platform", "profile", "user", "shell_path", "ssh_agent_socket", "pnpm_home",
    "mise", "brew_prefix", "git_email", "git_name", "dotfiles_repo", "dotfiles_version",
    "dotfiles_conflict_paths", "personal_public_ssh_key", "work_public_ssh_key",
    "remote_login_public_keys", "remote_login_sources", "pnpm_global_packages", "manage_ssh_config",
    "install_dotfiles", "manage_remote_login", "revoke_remote_login",
}
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


@contextlib.contextmanager
def environment(**values):
    saved = dict(os.environ)
    for variable in ("SUDO_ASKPASS", "GIT_CONFIG_GLOBAL", "GIT_DIR", "GIT_WORK_TREE"):
        os.environ.pop(variable, None)
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


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
            assert CONTRACT_KEYS <= config.keys(), CONTRACT_KEYS - config.keys()
            assert json.loads(json.dumps(config)) == config, "config must stay a plain JSON-compatible dict"
            assert config["platform"] == platform and config["profile"] == profile
            assert config["home"] == str(real_home) and config["repo_dir"] == str(root)
            assert (config["manage_ssh_config"], config["install_dotfiles"],
                    config["manage_remote_login"], config["revoke_remote_login"]) == (False, True, False, False)
            socket = ("Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
                      if platform == "mac" else ".1password/agent.sock")
            assert config["ssh_agent_socket"] == f"{real_home}/{socket}", config["ssh_agent_socket"]
            assert config["pnpm_home"] == f"{real_home}/" + ("Library/pnpm" if platform == "mac" else ".local/share/pnpm")
            assert config["shell_path"] == ("/bin/zsh" if platform == "mac" else "/usr/bin/zsh")
            assert config["brew_prefix"] == ("/opt/homebrew" if platform == "mac" else "/home/linuxbrew/.linuxbrew")
            assert ("tailscale_cli" in config) == ("remote_login_sshd_file" in config) == (platform == "mac")
            flagged = load(system, machine, profile=profile,
                           flags={"manage_ssh_config": True, "install_dotfiles": False})
            assert flagged["manage_ssh_config"] is True and flagged["install_dotfiles"] is False
            print(f"PASS: {platform}/{profile} ({machine}) selects its defaults and per-run overrides")
    assert load()["profile"] == "personal"
    forwarded = {"HOME": str(home), "SSH_AUTH_SOCK": "/tmp/session-specific-agent"}
    assert load("Linux", "aarch64", environ=forwarded)["ssh_agent_socket"] == "SSH_AUTH_SOCK"
    assert load(environ=forwarded)["ssh_agent_socket"].endswith("/t/agent.sock")
    print("PASS: Ubuntu uses the forwarded agent variable rather than a session-specific socket path")

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
    override.write_text('profile = "work"\ngit_name = "Override Name"\nremote_login_sshd = ["/fake/sshd", "-f", "x"]\n'
                        '[linux]\npnpm_home = "~/custom-pnpm"\n[mac]\ntailscale_cli = "/fake/tailscale"\n')
    merged = load("Linux", "aarch64", overrides=[override])
    assert merged["profile"] == "work" and merged["git_name"] == "Override Name"
    assert merged["pnpm_home"] == f"{real_home}/custom-pnpm" and "tailscale_cli" not in merged
    assert merged["remote_login_sshd"] == ["/fake/sshd", "-f", "x"]
    assert load(overrides=[override])["tailscale_cli"] == "/fake/tailscale"
    expect_error("Conflicting profiles", load, profile="personal", overrides=[override])
    for text, message in (("git_name = [", "Invalid TOML"), ('remote_login_sources = "100.64.0.0/10"', "list"),
                          ("install_dotfiles = 'yes'", "true or false"), ('home = "/tmp"', "cannot be set"),
                          ('machine_type = "work"', "cannot be set"), ('[linux]\nprofile = "work"', "cannot be set"),
                          ("remote_login_sudo = []", "cannot be set"),
                          ("[linux]\nremote_login_port = 2222", "cannot be set"),
                          ('[linux]\nshell_path = "zsh"', "absolute")):
        override.write_text(text + "\n")
        expect_error(message, load, "Linux", "aarch64", overrides=[override])
    expect_error("Cannot read settings file", load, overrides=[fixture / "missing.toml"])
    print("PASS: explicit local TOML layers merge per platform and malformed settings stop before changes")


# Action routing -------------------------------------------------------------
class Recorder:
    def __init__(self):
        self.calls = []
        self.host, self.software, self.security = (self._module(name) for name in ("host", "software", "security"))

    def _module(self, name):
        recorder = self

        class Module:
            @staticmethod
            def run(action, config, *, check=False):
                recorder.calls.append(f"{name}:{action}" + (" (check)" if check else ""))
        return Module


def route(action, platform="mac", check=False, **flags):
    config = {"platform": platform, "manage_ssh_config": False, "install_dotfiles": True,
              "manage_remote_login": False, "revoke_remote_login": False, **flags}
    recorder = Recorder()
    cli.dispatch(action, config, recorder, check=check)
    return recorder.calls


common = ["host:preflight", "host:git", "software:cli", "host:fzf"]
assert route("install") == common + ["software:gui", "host:zsh", "software:app-store", "host:osx",
                                     "software:node", "host:dotfiles", "host:dock"]
assert route("install", "linux") == common + ["host:zsh", "software:node", "host:dotfiles"]
assert route("install", "linux", manage_ssh_config=True, install_dotfiles=False) == [
    "host:preflight", "security:ssh", "host:git", "software:cli", "host:fzf", "host:zsh", "software:node"]
remote = route("install", manage_remote_login=True)
assert remote[4:6] == ["security:remote-login", "software:gui"], remote
assert "security:remote-login-revoke" in route("install", manage_remote_login=True, revoke_remote_login=True)
assert "security:remote-login" not in route("install", manage_remote_login=True, revoke_remote_login=True)
assert not any(call.startswith("security") for call in route("install", "linux", manage_remote_login=True,
                                                             revoke_remote_login=True))
print("PASS: full setup keeps the old task order, OS guards, and SSH/dotfiles/Remote Login opt-ins")

assert route("packages") == ["software:packages"]
assert route("update", "linux") == ["software:update"]
assert route("cli", "linux") == ["host:preflight", "software:cli", "host:fzf"]
assert route("node", "linux") == ["host:preflight", "software:node"]
assert route("bootstrap", "linux") == ["host:bootstrap"]
for action in ("git", "zsh", "dotfiles"):
    assert route(action, "linux") == ["host:preflight", f"host:{action}"]
for action in ("gui", "app-store", "osx", "dock"):
    assert route(action, "linux") == []
    assert route(action)[-1].endswith(":" + action)
for action in ("remote-login-check", "remote-login", "remote-login-revoke"):
    assert route(action) == [f"security:{action}"]
assert route("ssh", "linux") == ["host:preflight", "security:ssh"]
assert cli.parse_args(["ssh"]).flags == {"manage_ssh_config": True}
assert cli.parse_args(["dotfiles"]).flags == {"install_dotfiles": True}
assert cli.parse_args(["remote-login"]).flags == {"manage_remote_login": True}
assert cli.parse_args(["remote-login-revoke"]).flags == {"revoke_remote_login": True}
assert cli.parse_args(["install", "--keep-ssh", "--skip-dotfiles", "--profile", "work"]).flags == {
    "manage_ssh_config": False, "install_dotfiles": False}
assert cli.parse_args(["packages"]).flags == {}
for argv in (["dotfiles", "--skip-dotfiles"], ["install", "--keep-ssh", "--1password-ssh"],
             ["install", "--profile", "staging"], ["make"]):
    with open(os.devnull, "w") as quiet, contextlib.redirect_stderr(quiet):
        try:
            cli.parse_args(argv)
        except SystemExit as exit_status:
            assert exit_status.code == 2
        else:
            raise AssertionError(f"{argv} was accepted")
assert cli.parse_args(["remote-login", "--check"]).check and not cli.parse_args(["remote-login"]).check
print("PASS: direct commands route to one component, opt in to their own action, and reject conflicting options")


# install.sh prompts and hand-off --------------------------------------------
result = subprocess.run(["bash", str(root / "install.sh"), "invalid"], text=True, capture_output=True)
assert result.returncode == 64 and "Usage:" in result.stderr, result.stdout + result.stderr
print("PASS: bootstrap rejects an invalid profile before installing anything")
for requested, inherited in (("personal", "work"), ("work", "personal"), ("--bootstrap-only", "invalid")):
    result = subprocess.run(["bash", str(root / "install.sh"), requested], text=True, capture_output=True,
                            env=dict(os.environ, DEVSETUP_PROFILE=inherited))
    assert result.returncode == 64 and "DEVSETUP_PROFILE" in result.stderr, result.stdout + result.stderr
print("PASS: conflicting and invalid environment profiles stop before bootstrap")

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
    (fixture / "scripts/bootstrap-mise.sh").write_text(
        'mise_bin=/fake/mise\npython_bin="$repo_dir/bin/python"\n')
    (fixture / "bin").mkdir()
    command(fixture / "bin", "python", '''shift
echo "python: $*"
if [ "$1" = remote-login-check ]; then echo remote-preflight; exit "${TEST_PREFLIGHT_STATUS:-0}"; fi''')
    command(fixture / "scripts", "with-sudo-askpass.sh", 'echo "wrapper: $*"')
    command(fixture / "bin", "uname", '''case "$1" in
  -m) printf '%s\\n' "${TEST_MACHINE:-arm64}" ;;
  *) printf '%s\\n' "${TEST_SYSTEM:-Darwin}" ;;
esac''')
    env = dict(os.environ, PATH=str(fixture / "bin") + os.pathsep + os.environ["PATH"])
    for variable in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
        env.pop(variable, None)

    def setup_line(stdout):
        lines = [line for line in stdout.splitlines() if line.startswith("wrapper: ")]
        assert len(lines) <= 1, stdout
        return lines[0].split() if lines else None

    def bootstrap_line(stdout):
        lines = [line.split() for line in stdout.splitlines() if line.startswith("python: ") and " bootstrap " in line]
        assert len(lines) == 1, stdout
        return lines[0]

    cases = [
        ("Darwin", [], None, "--keep-ssh", "--dotfiles"),
        ("Darwin", [], "y\n", "--1password-ssh", "--dotfiles"),
        ("Darwin", [], "n\n", "--keep-ssh", "--dotfiles"),
        ("Darwin", [], "\n", "--keep-ssh", "--dotfiles"),
        ("Darwin", [], "maybe\nyes\n", "--1password-ssh", "--dotfiles"),
        ("Darwin", ["--1password-ssh"], None, "--1password-ssh", "--dotfiles"),
        ("Darwin", ["--keep-ssh", "--skip-dotfiles"], None, "--keep-ssh", "--skip-dotfiles"),
        ("Linux", [], None, "--keep-ssh", "--dotfiles"),
        ("Linux", [], "n\n\n", "--keep-ssh", "--dotfiles"),
        ("Linux", [], "y\nn\n", "--1password-ssh", "--skip-dotfiles"),
        ("Linux", [], "n\nmaybe\ny\n", "--keep-ssh", "--dotfiles"),
        ("Linux", ["--keep-ssh", "--skip-dotfiles"], None, "--keep-ssh", "--skip-dotfiles"),
        ("Linux", ["--1password-ssh", "--dotfiles"], None, "--1password-ssh", "--dotfiles"),
    ]
    for system, args, answer, ssh, dotfiles in cases:
        env["TEST_SYSTEM"] = system
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(["bash", str(installer), "work", *args],
                                       stdin=slave if answer is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            if answer is not None:
                os.write(master, (answer + ("n\n" if system == "Darwin" else "")).encode())
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stdout + stderr
            assert ("os-bootstrap:macos" if system == "Darwin" else "os-bootstrap:ubuntu") in stdout, stdout
            assert bootstrap_line(stdout)[-1] == ssh, stdout
            line = setup_line(stdout)
            assert line[2:] == [str(fixture / "scripts/setup.py"), "install", "--profile", "work",
                                "--mise", "/fake/mise", ssh, dotfiles, "--keep-remote-login"], line
            assert "remote-preflight" not in stdout, stdout
            if system == "Linux" and answer is not None:
                assert "[Y/n]" in stderr, stderr
            if answer is not None:
                assert "[y/N]" in stderr, stderr
        finally:
            os.close(master)
            os.close(slave)
    for profile, answer, remote_session, preflight_status, expected in (
        ("personal", "y\n", False, "0", True),
        ("personal", "\n", False, "0", False),
        ("personal", "maybe\nno\n", False, "0", False),
        ("personal", "\x04", False, "0", False),
        ("personal", "yes\n", False, "42", True),
        ("personal", "", True, "0", False),
        ("--bootstrap-only", "", False, "0", False),
    ):
        prompt_env = dict(env, TEST_SYSTEM="Darwin", TEST_PREFLIGHT_STATUS=preflight_status)
        if remote_session:
            prompt_env["SSH_CONNECTION"] = "remote-session"
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(["bash", str(installer), profile, "--keep-ssh"],
                                       stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, env=prompt_env)
            if answer:
                os.write(master, answer.encode())
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == int(preflight_status), stdout + stderr
            assert ("remote-preflight" in stdout) == expected, stdout
            bootstrap_line(stdout)
            line = setup_line(stdout)
            if preflight_status != "0" or profile == "--bootstrap-only":
                assert line is None, "Setup ran despite a failed preflight or bootstrap-only mode"
            else:
                assert line[-1] == ("--remote-login" if expected else "--keep-remote-login"), line
            if expected:
                check = next(item for item in stdout.splitlines() if "remote-login-check" in item)
                assert check.split()[1:] == ["remote-login-check", "--profile", profile, "--mise", "/fake/mise"]
                assert stdout.index("remote-preflight") > stdout.index(" bootstrap ")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            os.close(master)
            os.close(slave)
    print("PASS: Remote Login prompt is opt-in, preserves access on EOF or remote sessions, and stops on preflight failure")

    env["TEST_SYSTEM"] = "Darwin"
    result = subprocess.run(["bash", str(installer), "--bootstrap-only", "--1password-ssh"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0 and bootstrap_line(result.stdout)[-1] == "--1password-ssh"
    assert setup_line(result.stdout) is None
    shutil.copy(root / "new-mac.sh", fixture / "new-mac.sh")
    result = subprocess.run(["bash", str(fixture / "new-mac.sh"), "--keep-ssh"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0 and bootstrap_line(result.stdout)[-1] == "--keep-ssh"
    assert setup_line(result.stdout) is None
    for args in (["--keep-ssh", "--1password-ssh"], ["--dotfiles", "--skip-dotfiles"], ["work", "personal"]):
        result = subprocess.run(["bash", str(installer), *args], env=env, text=True, capture_output=True)
        assert result.returncode == 64 and "os-bootstrap" not in result.stdout, result.stdout
    for system, machine in (("Darwin", "x86_64"), ("Linux", "x86_64")):
        result = subprocess.run(["bash", str(installer), "--keep-ssh"], text=True, capture_output=True,
                                env=dict(env, TEST_SYSTEM=system, TEST_MACHINE=machine))
        assert result.returncode == 1 and "ARM64" in result.stderr and "os-bootstrap" not in result.stdout
    (fixture / "os-release").write_text("ID=fedora\n")
    result = subprocess.run(["bash", str(installer), "--keep-ssh"], text=True, capture_output=True,
                            env=dict(env, TEST_SYSTEM="Linux", TEST_MACHINE="aarch64"))
    assert result.returncode == 1 and "Only Ubuntu" in result.stderr and "os-bootstrap" not in result.stdout
    print("PASS: startup SSH/dotfiles prompts, defaults, opt-outs, ARM64/Ubuntu guards, and bootstrap-only mode")


# Host configuration in an isolated home -------------------------------------
if shutil.which("git") is None:
    print("SKIP: host configuration checks need git")
    sys.exit(0)

with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory).resolve()
    binary = fixture / "bin"
    binary.mkdir()
    calls = fixture / "calls"
    calls.write_text("")
    fzf_root = fixture / "fzf"
    fzf_root.mkdir()
    command(fzf_root, "install", f'echo "fzf-install $*" >> "{calls}"')
    mise = command(binary, "mise", f'''echo "mise $*" >> "{calls}"
if [ "$3" = where ]; then echo "{fzf_root}"; fi''')
    for name in ("sudo", "chflags", "killall"):
        command(binary, name, f'echo "{name} $*" >> "{calls}"')
    command(binary, "defaults", f'''if [ "$1" = read ]; then echo "$TEST_UPDATE_CHECK"; exit 0; fi
echo "defaults $*" >> "{calls}"
[ "$3" != "${{TEST_FAIL_KEY:-}}" ]''')
    command(binary, "dockutil", f'''echo "dockutil $*" >> "{calls}"
case "$2" in */Warp.app) exit 1 ;; esac''')

    def isolated(name, platform="linux", **settings):
        home = fixture / name
        home.mkdir()
        config = {"home": str(home), "repo_dir": str(root), "platform": platform, "profile": "personal",
                  "user": "tester", "mise": str(mise), "brew_prefix": "/opt/homebrew",
                  "shell_path": "/bin/zsh", "git_email": "tester@example.com", "git_name": "Test User",
                  "dotfiles_conflict_paths": [".agents/.skill-lock.json"], "manage_ssh_config": False,
                  **settings}
        env = {"HOME": str(home), "PATH": f"{binary}{os.pathsep}{os.environ['PATH']}",
               "GIT_CONFIG_NOSYSTEM": "1", "XDG_CONFIG_HOME": str(home / ".config"),
               "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.com",
               "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.com"}
        return home, config, env

    def recorded():
        lines = calls.read_text().splitlines()
        calls.write_text("")
        return lines

    home, config, env = isolated("check-home", "mac", manage_ssh_config=True, dotfiles_repo=str(fixture / "none"),
                                 dotfiles_version="master")
    with environment(**env, TEST_UPDATE_CHECK="0"):
        for action in ("bootstrap", "git", "zsh", "fzf", "osx", "dock", "dotfiles"):
            host.run(action, config, check=True)
    assert recorded() == [] and list(home.iterdir()) == [], "check mode ran a command or wrote a file"
    print("PASS: host check mode reports Git and shell changes without running commands or writing files")

    home, config, env = isolated("git-home")
    with environment(**env):
        host.run("git", config)
        host.run("git", config)
        gitconfig = subprocess.run(["git", "config", "--global", "--list"], text=True, capture_output=True,
                                   check=True).stdout.splitlines()
    assert (home / ".global_gitignore").read_text() == (root / "scripts/devsetup/global_gitignore").read_text()
    assert (home / ".global_gitignore").stat().st_mode & 0o777 == 0o644
    for setting in ("user.email=tester@example.com", "user.name=Test User", "pull.rebase=true",
                    "core.excludesfile=~/.global_gitignore", "fetch.prune=true", "init.defaultbranch=main",
                    "push.autosetupremote=true"):
        assert setting in gitconfig, gitconfig
    print("PASS: Git gets the latest formula, global ignore file, identity, and defaults idempotently")

    home, config, env = isolated("shell-home")
    (home / ".bashrc").write_text("# existing bash settings\n")
    dotfiles_zshrc = fixture / "external-dotfiles-zshrc"
    dotfiles_zshrc.write_text("# external dotfiles zshrc\n")
    (home / ".zshrc").symlink_to(dotfiles_zshrc)
    with environment(**env):
        host.run("bootstrap", config)
        host.run("bootstrap", config)
        host.run("fzf", config)
    bashrc = (home / ".bashrc").read_text()
    assert bashrc.startswith("# existing bash settings\n") and bashrc.count("# BEGIN dev-machine mise") == 1
    assert f"eval \"$({mise} activate bash)\"" in bashrc and 'export PATH="/opt/homebrew/bin:' in bashrc
    assert dotfiles_zshrc.read_text() == "# external dotfiles zshrc\n", "setup edited an external shell file"
    assert (home / ".ssh").is_dir() and (home / ".gnupg").is_dir()
    lines = recorded()
    assert not any("1password" in line for line in lines)
    assert lines[-1] == "fzf-install --key-bindings --completion --no-update-rc", lines
    (home / ".zshrc").unlink()
    with environment(**env):
        host.run("bootstrap", config)
        host.run("fzf", config)
    assert "activate zsh" in (home / ".zshrc").read_text()
    assert recorded()[-1] == "fzf-install --all"
    print("PASS: bootstrap and fzf activate mise and shell integration without editing symlinked dotfiles")

    home, config, env = isolated("mac-home", "mac")
    with environment(**env, TEST_UPDATE_CHECK="0"):
        host.run("osx", config)
    lines = recorded()
    assert f"defaults write com.apple.finder NewWindowTargetPath -string file://{home}" in lines
    assert f"defaults write com.apple.screencapture location -string {home}/Desktop" in lines
    assert f"chflags nohidden {home}/Library" in lines
    assert ("sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -int 1"
            in lines) and lines[-1] == "killall Finder"
    with environment(**env, TEST_UPDATE_CHECK="1"):
        host.run("osx", config)
    assert not any(line.startswith("sudo") for line in recorded()), "sudo ran with the preference already set"
    with environment(**env, TEST_UPDATE_CHECK="1", TEST_FAIL_KEY="KeyRepeat"):
        expect_error("KeyRepeat", host.run, "osx", config)
    assert "killall Finder" not in recorded()
    with environment(**env):
        host.run("dock", config)
    lines = recorded()
    dock = [line for line in lines if line.startswith(("dockutil", "killall"))]
    assert dock[0] == "dockutil --remove all --no-restart" and dock[-1] == "killall Dock"
    assert "dockutil --add /Applications/Warp.app --no-restart" in dock
    assert "dockutil --add  --type spacer --section apps --after Open Design --no-restart" in dock
    assert dock[-2] == "dockutil --add /System/Applications/Podcasts.app --no-restart"
    print("PASS: macOS defaults stop on failure and use sudo only for the update check; Dock skips missing apps")

    # A local upstream stands in for the dotfiles repository.
    home, config, env = isolated("dotfiles-home")
    upstream = fixture / "upstream"
    with environment(**env):
        def git(*args, cwd=upstream):
            return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()
        upstream.mkdir()
        git("init", "-q", "-b", "master")
        command(upstream, "install.sh", 'echo ran >> "$HOME/dotfiles-installed"')
        git("add", "install.sh")
        git("commit", "-qm", "first")
        first = git("rev-parse", "HEAD")
        conflict = home / ".agents/.skill-lock.json"
        conflict.parent.mkdir()
        conflict.write_text("local lock")
        config.update(dotfiles_repo=str(upstream), dotfiles_version="master")
        host.run("dotfiles", config)
        checkout = home / ".dotfiles"
        assert not conflict.exists()
        backups = list((home / ".dev-setup-backups").glob("*/dotfiles/.agents/.skill-lock.json"))
        assert [backup.read_text() for backup in backups] == ["local lock"]
        (upstream / "second").write_text("2")
        git("add", "second")
        git("commit", "-qm", "second")
        conflict.write_text("new local lock")
        (checkout / "nested").mkdir()
        (checkout / "nested/.DS_Store").write_text("Finder metadata")
        host.run("dotfiles", config)
        assert git("rev-parse", "HEAD", cwd=checkout) == git("rev-parse", "HEAD")
        assert not (checkout / "nested/.DS_Store").exists(), "macOS metadata was left for stow"
        assert len(list((home / ".dev-setup-backups").iterdir())) == 2, "a later backup overwrote an earlier one"
        (checkout / "second").write_text("local edit")
        expect_error("local changes", host.run, "dotfiles", config)
        assert (checkout / "second").read_text() == "local edit"
        git("checkout", "--", "second", cwd=checkout)
        (checkout / "mine").write_text("mine")
        git("add", "mine", cwd=checkout)
        git("commit", "-qm", "local work", cwd=checkout)
        local = git("rev-parse", "HEAD", cwd=checkout)
        (upstream / "third").write_text("3")
        git("add", "third")
        git("commit", "-qm", "third")
        expect_error("diverged", host.run, "dotfiles", config)
        assert git("rev-parse", "HEAD", cwd=checkout) == local, "setup discarded a local commit"
        config["dotfiles_version"] = first
        host.run("dotfiles", config)
        assert git("rev-parse", "HEAD", cwd=checkout) == first
        assert git("rev-parse", "master", cwd=checkout) == local, "pinning discarded the local branch"
        (checkout / "detached-work").write_text("preserve me")
        git("add", "detached-work", cwd=checkout)
        git("commit", "-qm", "detached local work", cwd=checkout)
        detached = git("rev-parse", "HEAD", cwd=checkout)
        expect_error("detached commits", host.run, "dotfiles", config)
        config["dotfiles_version"] = "master"
        expect_error("detached commits", host.run, "dotfiles", config)
        config["dotfiles_version"] = first
        assert git("rev-parse", "HEAD", cwd=checkout) == detached
        assert (checkout / "detached-work").read_text() == "preserve me"
        git("branch", "keep-detached", cwd=checkout)
        host.run("dotfiles", config)
        assert git("rev-parse", "HEAD", cwd=checkout) == first
        assert git("rev-parse", "keep-detached", cwd=checkout) == detached
        shutil.rmtree(checkout)
        host.run("dotfiles", config)
        assert git("rev-parse", "HEAD", cwd=checkout) == first
    print("PASS: dotfiles clone, fast-forward, pin, back up conflicts uniquely, and never discard local work")

    home, config, env = isolated("preflight-home")
    with environment(**{**env, "PATH": str(binary)}):
        expect_error("Required command 'git'", host.run, "preflight", config)
    print("PASS: setup preflight requires git and curl before changes")

with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory)
    binary = fixture / "bin"
    binary.mkdir()
    marker = fixture / "sudo-called"
    command(binary, "sudo", 'touch "$TEST_SUDO_MARKER"; exit 99')
    env = {**os.environ, "HOME": str(fixture), "TEST_SUDO_MARKER": str(marker),
           "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
    env.pop("DEVSETUP_PROFILE", None)
    result = subprocess.run(
        ["bash", str(root / "scripts/with-sudo-askpass.sh"), sys.executable,
         str(root / "scripts/setup.py"), "cli", "--check", "--mise", FAKE_MISE],
        env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists(), "a read-only task requested sudo before parsing --check"
    assert not (fixture / ".dev-setup-backups").exists()
    print("PASS: the public --check command bypasses sudo and leaves the home unchanged")
    refused = subprocess.run(
        ["bash", str(root / "scripts/with-sudo-askpass.sh"), "/bin/sh", "-c", "exit 23"],
        env=env, text=True, capture_output=True, start_new_session=True,
    )
    assert refused.returncode == 1 and "terminal" in refused.stderr
    command(binary, "sudo", 'if [[ "$*" == "-n true" ]]; then exit 0; fi\nexit 1')
    allowed = subprocess.run(
        ["bash", str(root / "scripts/with-sudo-askpass.sh"), "/bin/sh", "-c", "exit 23"],
        env=env, text=True, capture_output=True, start_new_session=True,
    )
    assert allowed.returncode == 23, allowed.stdout + allowed.stderr
    print("PASS: headless sudo refuses unavailable authorisation, accepts NOPASSWD, and preserves command failure")
