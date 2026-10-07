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
            assert config["platform"] == platform and config["profile"] == profile
            assert config["home"] == str(real_home) and config["repo_dir"] == str(root)
            socket = ("Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
                      if platform == "mac" else ".1password/agent.sock")
            assert config["ssh_agent_socket"] == f"{real_home}/{socket}", config["ssh_agent_socket"]
            assert config["pnpm_home"] == f"{real_home}/" + ("Library/pnpm" if platform == "mac" else ".local/share/pnpm")
            assert config["shell_path"] == ("/bin/zsh" if platform == "mac" else "/usr/bin/zsh")
            assert config["brew_prefix"] == ("/opt/homebrew" if platform == "mac" else "/home/linuxbrew/.linuxbrew")
            assert ("tailscale_cli" in config) == ("remote_login_sshd_file" in config) == (platform == "mac")
            flagged = load(system, machine, profile=profile,
                           flags={"ssh": True, "dotfiles": False})
            assert flagged["steps"]["ssh"] is True and flagged["steps"]["dotfiles"] is False
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
                          ("[steps]\ndotfiles = 'yes'", "true or false"), ('home = "/tmp"', "cannot be set"),
                          ('machine_type = "work"', "cannot be set"), ('[linux]\nprofile = "work"', "cannot be set"),
                          ("remote_login_sudo = []", "cannot be set"),
                          ("[linux]\nremote_login_port = 2222", "cannot be set"),
                          ('[linux]\nshell_path = "zsh"', "absolute")):
        override.write_text(text + "\n")
        expect_error(message, load, "Linux", "aarch64", overrides=[override])
    expect_error("Cannot read settings file", load, overrides=[fixture / "missing.toml"])
    for text in ('git_emali = "typo@example.invalid"', '[mac.steps]\nappstore = false',
                 '[linux]\nmanage_remote_logni = true', 'install_dotfiles = false'):
        override.write_text(text + "\n")
        expect_error("unknown", load, overrides=[override])
    first_layer = fixture / "first.toml"
    first_layer.write_text('[steps]\napp-store = false\ndock = false\n[mac.steps]\ndock = true\n')
    override.write_text('[steps]\napp-store = true\n[mac.steps]\nosx = false\n')
    selected = load(overrides=[first_layer, override], flags={"app-store": False})
    assert selected["steps"]["dock"] and not selected["steps"]["osx"]
    assert not selected["steps"]["app-store"], "explicit skip must win over later configuration"
    assert load(overrides=[first_layer, override])["steps"]["app-store"]
    override.write_text('[mac]\nmacos_preferences = [["domain", "key"]]\n')
    expect_error("domain, key and value", load, overrides=[override])
    override.write_text('[mac]\ndock_items = [["relative.app"]]\n')
    expect_error("absolute path", load, overrides=[override])
    print("PASS: unknown settings fail and typed component choices merge by key with explicit precedence")
    print("PASS: explicit local TOML layers merge per platform and malformed settings stop before changes")


# Contradictory explicit choices must fail rather than silently turn into no-ops.
for argv in (["dotfiles", "--skip-dotfiles"], ["install", "--keep-ssh", "--1password-ssh"],
             ["install", "--profile", "staging"], ["make"], ["install", "--skip", "preflight"],
             ["install", "--skip", "ssh", "--1password-ssh"], ["app-store", "--skip", "app-store"],
             ["update", "--skip", "dotfiles"], ["node", "--revoke-remote-login"],
             ["install", "--skip"]):
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
    (fixture / "scripts/bootstrap-mise.sh").write_text(
        'mise_bin=/fake/mise\npython_bin="$repo_dir/bin/python"\n')
    (fixture / "bin").mkdir()
    command(fixture / "bin", "python", 'shift; echo "python: $*"')
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

    cases = [
        ("Darwin", [], None),
        ("Darwin", [], "y\n"),
        ("Darwin", [], "n\n"),
        ("Darwin", [], "\n"),
        ("Darwin", [], "maybe\nyes\n"),
        ("Darwin", ["--1password-ssh"], None),
        ("Darwin", ["--keep-ssh", "--skip-dotfiles"], None),
        ("Linux", [], None),
        ("Linux", [], "n\n\n"),
        ("Linux", [], "y\nn\n"),
        ("Linux", [], "n\nmaybe\ny\n"),
        ("Linux", ["--keep-ssh", "--skip-dotfiles"], None),
        ("Linux", ["--1password-ssh", "--dotfiles"], None),
    ]
    for system, args, answer in cases:
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
            if system == "Linux" and answer is not None:
                assert "[Y/n]" in stderr, stderr
            if answer is not None:
                assert "[y/N]" in stderr, stderr
        finally:
            os.close(master)
            os.close(slave)

    env["TEST_SYSTEM"] = "Darwin"
    result = subprocess.run(["bash", str(installer), "--bootstrap-only", "--1password-ssh"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0
    assert setup_line(result.stdout) is None
    shutil.copy(root / "new-mac.sh", fixture / "new-mac.sh")
    result = subprocess.run(["bash", str(fixture / "new-mac.sh"), "--keep-ssh"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0
    assert setup_line(result.stdout) is None
    for system, machine in (("Linux", "x86_64"),):
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
    (fixture / "os-release").write_text("ID=ubuntu\n")
    binary = fixture / "bin"
    binary.mkdir()
    calls = fixture / "calls"
    calls.write_text("")
    fzf_root = fixture / "opt/fzf"
    fzf_root.mkdir(parents=True)
    command(fzf_root, "install", f'echo "fzf-install $*" >> "{calls}"')
    mise = command(binary, "mise", f'echo "mise $*" >> "{calls}"')
    brew = command(binary, "brew", f'''case "$1" in
  list|--version) exit 0 ;;
  --prefix) printf '%s\\n' "{fixture}"; exit 0 ;;
esac
echo "brew $*" >> "{calls}"
if [ "$1" = update ] && [ "${{TEST_BREW_UPDATE_FAIL:-}}" = 1 ]; then exit 17; fi''')
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
        config = config_module.load(
            repo_dir=root, system="Darwin" if platform == "mac" else "Linux", machine="arm64",
            os_release=Path("/dev/null") if platform == "mac" else fixture / "os-release",
            environ={"HOME": str(home)}, mise=str(mise), user="tester")
        config.update(brew=str(brew), brew_prefix=str(fixture), shell_path="/bin/zsh",
                      git_email="tester@example.com", git_name="Test User",
                      dotfiles_conflict_paths=[".agents/.skill-lock.json"], **settings)
        env = {"HOME": str(home), "PATH": f"{binary}{os.pathsep}{os.environ['PATH']}",
               "GIT_CONFIG_NOSYSTEM": "1", "XDG_CONFIG_HOME": str(home / ".config"),
               "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.com",
               "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.com"}
        return home, config, env

    def recorded():
        lines = calls.read_text().splitlines()
        calls.write_text("")
        return lines

    home, config, env = isolated("check-home", "mac", dotfiles_repo=str(fixture / "none"),
                                 dotfiles_version="master")
    config["steps"]["ssh"] = True
    with environment(**env, TEST_UPDATE_CHECK="0"):
        for action in ("bootstrap", "git", "zsh", "fzf", "osx", "dock", "dotfiles"):
            host.run(action, config, check=True)
    assert recorded() == [] and list(home.iterdir()) == [], "check mode ran a command or wrote a file"
    print("PASS: host check mode reports Git and shell changes without installations or writes")

    home, config, env = isolated("git-home")
    with environment(**env):
        host.run("git", config)
        host.run("git", config)
        gitconfig = subprocess.run(["git", "config", "--global", "--list"], text=True, capture_output=True,
                                   check=True).stdout.splitlines()
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
    assert dotfiles_zshrc.read_text() == "# external dotfiles zshrc\n", "setup edited an external shell file"
    assert (home / ".ssh").is_dir() and (home / ".gnupg").is_dir()
    lines = recorded()
    assert not any("1password" in line for line in lines)
    assert lines[-1] == "fzf-install --key-bindings --completion --no-update-rc", lines
    print("PASS: bootstrap and fzf activate mise and shell integration without editing symlinked dotfiles")

    home, config, env = isolated("mac-home", "mac")
    config["macos_preferences"] = [["example.preferences", "Path", "-string", "{home}/custom"],
                                 ["example.preferences", "Literal", "-string", "{literal}"]]
    with environment(**env, TEST_UPDATE_CHECK="0"):
        host.run("osx", config)
    lines = recorded()
    assert f"defaults write example.preferences Path -string {home}/custom" in lines
    assert "defaults write example.preferences Literal -string {literal}" in lines
    assert f"chflags nohidden {home}/Library" in lines
    assert ("sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -int 1"
            in lines) and lines[-1] == "killall Finder"
    with environment(**env, TEST_UPDATE_CHECK="1"):
        host.run("osx", config)
    assert not any(line.startswith("sudo") for line in recorded()), "sudo ran with the preference already set"
    with environment(**env, TEST_UPDATE_CHECK="1", TEST_FAIL_KEY="Path"):
        expect_error("Path", host.run, "osx", config)
    assert "killall Finder" not in recorded()
    config["macos_preferences"] = []
    with environment(**env, TEST_UPDATE_CHECK="1"):
        host.run("osx", config)
    assert not any(line.startswith("defaults write") for line in recorded())
    config["dock_items"] = []
    with environment(**env):
        host.run("dock", config)
    assert recorded() == [], "empty Dock policy must leave the existing Dock untouched"
    config["dock_items"] = [["/Applications/Warp.app"], ["/Applications/Fixture.app"]]
    with environment(**env):
        host.run("dock", config)
    lines = recorded()
    dock = [line for line in lines if line.startswith(("dockutil", "killall"))]
    assert dock[0] == "dockutil --remove all --no-restart" and dock[-1] == "killall Dock"
    assert "dockutil --add /Applications/Warp.app --no-restart" in dock
    assert dock[-2] == "dockutil --add /Applications/Fixture.app --no-restart"
    print("PASS: macOS defaults stop on failure and use sudo only for the update check; Dock skips missing apps")

    # A local upstream stands in for the dotfiles repository.
    home, config, env = isolated("dotfiles-home")
    upstream = fixture / "upstream"
    with environment(**env):
        def git(*args, cwd=upstream):
            return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()
        upstream.mkdir()
        git("init", "-q", "-b", "master")
        command(upstream, "install.sh", 'printf "# Managed by the fixture installer\\n" >> "$HOME/.zshrc"')
        git("add", "install.sh")
        git("commit", "-qm", "first")
        first = git("rev-parse", "HEAD")
        conflict = home / ".agents/.skill-lock.json"
        conflict.parent.mkdir()
        conflict.write_text("local lock")
        config.update(dotfiles_repo=str(upstream))
        host.run("dotfiles", config)

        def refused_install(message):
            (home / ".zshrc").write_text("# User's local shell settings\n")
            shell_before = (home / ".zshrc").read_bytes()
            expect_error(message, host.run, "dotfiles", config)
            assert (home / ".zshrc").read_bytes() == shell_before, "a refused checkout changed shell configuration"

        checkout = home / ".dotfiles"
        assert not conflict.exists()
        backups = list((home / ".dev-setup-backups").glob("*/dotfiles/.agents/.skill-lock.json"))
        assert [backup.read_text() for backup in backups] == ["local lock"]
        original_head = git("rev-parse", "HEAD", cwd=checkout)
        original_origin = git("config", "--get", "remote.origin.url", cwd=checkout)
        fetch_file = checkout / ".git/FETCH_HEAD"
        fetch_head = fetch_file.read_bytes() if fetch_file.exists() else None
        config["dotfiles_repo"] = str(fixture / "different-upstream")
        refused_install("does not match")
        assert git("rev-parse", "HEAD", cwd=checkout) == original_head
        assert git("config", "--get", "remote.origin.url", cwd=checkout) == original_origin
        assert (fetch_file.read_bytes() if fetch_file.exists() else None) == fetch_head
        config["dotfiles_repo"] = upstream.as_uri()
        host.run("dotfiles", config)
        config["dotfiles_repo"] = str(upstream)
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
        refused_install("local changes")
        assert (checkout / "second").read_text() == "local edit"
        git("checkout", "--", "second", cwd=checkout)
        (checkout / "mine").write_text("mine")
        git("add", "mine", cwd=checkout)
        git("commit", "-qm", "local work", cwd=checkout)
        local = git("rev-parse", "HEAD", cwd=checkout)
        (upstream / "third").write_text("3")
        git("add", "third")
        git("commit", "-qm", "third")
        refused_install("diverged")
        assert git("rev-parse", "HEAD", cwd=checkout) == local, "setup discarded a local commit"
        config["dotfiles_version"] = first
        host.run("dotfiles", config)
        assert git("rev-parse", "HEAD", cwd=checkout) == first
        assert git("rev-parse", "master", cwd=checkout) == local, "pinning discarded the local branch"
        (checkout / "detached-work").write_text("preserve me")
        git("add", "detached-work", cwd=checkout)
        git("commit", "-qm", "detached local work", cwd=checkout)
        detached = git("rev-parse", "HEAD", cwd=checkout)
        refused_install("detached commits")
        config["dotfiles_version"] = "master"
        refused_install("detached commits")
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
    override = fixture / "failed-refresh.toml"
    override.write_text(f"brew = {json.dumps(str(brew))}\n")
    result = subprocess.run(
        [sys.executable, str(root / "scripts/setup.py"), "install", "--1password-ssh", "--skip-dotfiles",
         "--config", str(override), "--mise", str(mise)],
        env={**os.environ, **env, "DEVSETUP_PROFILE": "personal", "TEST_BREW_UPDATE_FAIL": "1"},
        text=True, capture_output=True,
    )
    assert result.returncode == 1 and "update" in result.stderr, result.stdout + result.stderr
    assert list(home.iterdir()) == [], "a failed Homebrew refresh changed SSH or host configuration"
    print("PASS: a failed Homebrew refresh stops full setup before managed SSH or host writes")

    if sys.platform == "darwin" and os.uname().machine == "arm64":
        home, config, env = isolated("initial-installer-home", "mac")
        repo = fixture / "installer-repo"
        repo.mkdir()
        shutil.copytree(root / "scripts", repo / "scripts")
        for name in ("install.sh", "remote-login.sh", "defaults.toml"):
            shutil.copy(root / name, repo / name)
        for name in ("bootstrap-macos.sh", "bootstrap-homebrew.sh"):
            (repo / "scripts" / name).write_text(":\n")
        (repo / "scripts/bootstrap-mise.sh").write_text(
            f"mise_bin={shlex.quote(str(mise))}\npython_bin={shlex.quote(sys.executable)}\n")
        command(repo / "scripts", "with-sudo-askpass.sh", 'exec "$@"')
        (home / ".ssh").mkdir()
        keys = home / ".ssh/authorized_keys"
        keys.write_text("preserve existing authorised keys\n")
        service = fixture / "remote-service"
        service.write_text("unchanged")
        launchctl = command(binary, "launchctl-fixture", f'echo changed > "{service}"; exit 99')
        policy = fixture / "remote choice.toml"
        policy.write_text(
            f"brew = {json.dumps(str(brew))}\nbrew_prefix = {json.dumps(str(fixture))}\n"
            f"remote_login_launchctl = {json.dumps(str(launchctl))}\n"
            'remote_login_public_keys = ["not-prepared.pub"]\n[steps]\n' +
            "\n".join(f'{name} = {"true" if name == "remote-login" else "false"}'
                      for name in config_module.STEPS) + "\n")
        process_env = {**os.environ, **env, "DEVSETUP_PROFILE": "personal",
                       "MISE_ORIGINAL_CWD": str(fixture)}
        for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
            process_env.pop(name, None)
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(
                [str(repo / "install.sh"), "--keep-ssh", "--config", policy.name],
                stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=fixture, env=process_env)
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stdout + stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            os.close(master)
            os.close(slave)
        assert keys.read_text() == "preserve existing authorised keys\n"
        assert service.read_text() == "unchanged"
        # Execute the real dispatcher through the launcher, without installing mise/Python.
        command(binary, "mise", f'printf "%s\\n" {shlex.quote(sys.executable)}')
        result = subprocess.run([str(repo / "remote-login.sh"), "--config", policy.name],
                                cwd=fixture, env=process_env, text=True, capture_output=True, timeout=15)
        assert result.returncode == 1 and "not-prepared.pub" in result.stderr, result.stdout + result.stderr
        assert keys.read_text() == "preserve existing authorised keys\n"
        assert service.read_text() == "unchanged"
        print("PASS: interactive installation needs no Remote Login answer or prerequisites; "
              "the separate launcher checks prerequisites before changing access")
