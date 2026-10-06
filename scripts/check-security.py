#!/usr/bin/env python3
"""Executable-state checks for scripts/devsetup/security.py.

Every system tool the security module may call is a stateful fake in a
temporary directory: launchctl, sudo, sshd, dscl, dseditgroup, Tailscale and
Homebrew. Service fakes refuse calls that did not go through the sudo fake.
No host service, SSH configuration, access list or key is read or changed,
except that on macOS the real /usr/sbin/sshd evaluates temporary
configuration files without privileges.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import socket
import subprocess
import sys
import tempfile
import threading

root = Path(__file__).resolve().parents[1]
if os.geteuid() == 0:
    sys.exit("Run check-security.py as a normal user, not root.")
USER = pwd.getpwuid(os.getuid()).pw_name
IS_MAC = platform.system() == "Darwin"
RUNNER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from devsetup import security
try:
    security.run(sys.argv[2], json.loads(sys.argv[3]), check=sys.argv[4] == "1")
except RuntimeError as error:
    print("ERROR: " + str(error), file=sys.stderr)
    sys.exit(1)
"""

LAUNCHCTL = r'''#!/bin/sh
printf 'launchctl %s\n' "$*" >> "$TEST_CALLS"
[ "${TEST_PRIVILEGED:-}" = 1 ] || { echo "launchctl called without sudo" >&2; exit 98; }
case "$*" in
  "print-disabled system")
    if [ -f "$TEST_STATE/disabled" ]; then state=disabled; else state=enabled; fi
    printf '"com.openssh.sshd" => %s\n' "$state" ;;
  "print system/com.openssh.sshd")
    if [ -f "$TEST_STATE/running" ]; then exit 0; else exit 113; fi ;;
  "disable system/com.openssh.sshd") touch "$TEST_STATE/disabled" ;;
  "bootout system/com.openssh.sshd")
    if [ "${TEST_REMOTE_STOP_FAIL:-0}" = 1 ]; then echo "bootout refused" >&2; exit 5; fi
    rm -f "$TEST_STATE/running" ;;
  "enable system/com.openssh.sshd") rm -f "$TEST_STATE/disabled" ;;
  "bootstrap system /System/Library/LaunchDaemons/ssh.plist")
    touch "$TEST_STATE/running"
    if [ "${TEST_REMOTE_BOOTSTRAP_FAIL:-0}" = 1 ]; then echo "bootstrap: Input/output error" >&2; exit 5; fi ;;
  *) echo "unexpected launchctl call" >&2; exit 99 ;;
esac
'''

SUDO = r'''#!/bin/sh
printf 'sudo %s\n' "$*" >> "$TEST_CALLS"
if [ "$1" = -v ]; then exit "${TEST_SUDO_STATUS:-0}"; fi
TEST_PRIVILEGED=1
export TEST_PRIVILEGED
exec "$@"
'''

TAILSCALE = r'''#!/bin/sh
printf 'tailscale %s\n' "$*" >> "$TEST_CALLS"
[ "$*" = "status --json" ] || exit 99
printf '{"BackendState": "%s", "Self": {"DNSName": "test-mac.example.ts.net.", "TailscaleIPs": [%s]}}\n' \
  "${TEST_TAILSCALE_STATE:-Running}" "${TEST_TAILSCALE_IPS-\"100.100.100.10\"}"
'''

SSH_KEYGEN = r'''#!/bin/sh
printf 'ssh-keygen %s\n' "$*" >> "$TEST_CALLS"
if [ "$1" = -A ]; then echo "host key creation must not run in tests" >&2; exit 99; fi
exec /usr/bin/ssh-keygen "$@"
'''

FORBIDDEN = '''#!/bin/sh
printf 'forbidden %s %s\\n' "$(basename "$0")" "$*" >> "$TEST_CALLS"
exit 99
'''

# Models sshd -t and -T for the managed file without reading host configuration.
FAKE_SSHD = r'''
import os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["TEST_CALLS"], "a") as log:
    log.write("sshd " + " ".join(args) + "\n")
if os.environ.get("TEST_PRIVILEGED") != "1":
    sys.exit("sshd called without sudo")
if os.path.exists(os.path.join(os.environ["TEST_STATE"], "running")):
    print("SSH configuration was checked while the listener was running", file=sys.stderr)
    sys.exit(91)
if "-t" in args:
    candidate = args[len(args) - 1 - args[::-1].index("-f") + 1]
    if os.environ.get("TEST_SSHD_SYNTAX_FAIL") or "Match all" not in Path(candidate).read_text():
        print(candidate + " line 1: Bad configuration option", file=sys.stderr)
        sys.exit(255)
    sys.exit(0)
if "-T" in args:
    managed = Path(os.environ["TEST_MANAGED"])
    out, err = [], []
    if managed.is_file() and not managed.is_symlink():
        text = managed.read_text()
        err.append(f"debug2: parse_server_config_depth: config {managed} len {len(text)}")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("Match "):
                err.append(f"debug3: checking syntax for '{line}'")
                continue
            key, value = line.split(None, 1)
            if key.lower() == "allowusers":
                out += ["allowusers " + entry for entry in value.split()]
            else:
                out.append(key.lower() + " " + value)
    if os.environ.get("TEST_SSHD_EXTRA_MATCH"):
        err.append("debug3: checking syntax for '" + os.environ["TEST_SSHD_EXTRA_MATCH"] + "'")
    out += ["refuseconnection no", "forcecommand none", "chrootdirectory none", "permittty yes", "maxsessions 10"]
    out += [line for line in os.environ.get("TEST_SSHD_EXTRA_LINES", "").split(";") if line]
    print("\n".join(out))
    print("\n".join(err), file=sys.stderr)
    sys.exit(0)
sys.exit(99)
'''

FAKE_DSCL = r'''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["TEST_CALLS"], "a") as log:
    log.write("dscl " + " ".join(args) + "\n")
path = os.path.join(os.environ["TEST_STATE"], "access.json")
state = json.load(open(path))
group = "/Groups/com.apple.access_ssh"
if args[:3] == [".", "-read", group]:
    if not state["exists"]:
        print("<dscl_cmd> DS Error: -14136 (eDSRecordNotFound)", file=sys.stderr)
        sys.exit(56)
    for attribute in args[3:]:
        values = {"GroupMembership": state["members"], "NestedGroups": list(state["nested"])}.get(attribute, [])
        if values:
            print(attribute + ": " + " ".join(values))
        else:
            print("No such key: " + attribute, file=sys.stderr)
    sys.exit(0)
if args[:4] == [".", "-search", "/Groups", "GeneratedUID"]:
    name = state["nested"].get(args[4])
    if name:
        print(f"{name}\t\tGeneratedUID = (\n    {args[4]}\n)")
    sys.exit(0)
if args[:4] == [".", "-delete", group, "NestedGroups"] and os.environ.get("TEST_PRIVILEGED") == "1":
    state["nested"].pop(args[4])
    json.dump(state, open(path, "w"))
    sys.exit(0)
sys.exit(99)
'''

FAKE_DSEDITGROUP = r'''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["TEST_CALLS"], "a") as log:
    log.write("dseditgroup " + " ".join(args) + "\n")
if os.environ.get("TEST_PRIVILEGED") != "1" or args[-1] != "com.apple.access_ssh":
    sys.exit(98)
path = os.path.join(os.environ["TEST_STATE"], "access.json")
state = json.load(open(path))
if args[:2] == ["-o", "create"]:
    state.update(exists=True, members=[], nested={})
elif args[:2] == ["-o", "edit"] and state["exists"]:
    kind = args[args.index("-t") + 1]
    if "-a" in args and kind == "user":
        name = args[args.index("-a") + 1]
        state["members"] += [] if name in state["members"] else [name]
    elif "-d" in args and kind == "user":
        state["members"].remove(args[args.index("-d") + 1])
    elif "-d" in args and kind == "group":
        name = args[args.index("-d") + 1]
        state["nested"] = {guid: group for guid, group in state["nested"].items() if group != name}
    else:
        sys.exit(99)
else:
    sys.exit(99)
json.dump(state, open(path, "w"))
'''

REAL_SSHD = r'''#!/bin/sh
printf 'sshd %s\n' "$*" >> "$TEST_CALLS"
[ "${TEST_PRIVILEGED:-}" = 1 ] || { echo "sshd called without sudo" >&2; exit 98; }
if [ -f "$TEST_STATE/running" ]; then
  echo "SSH configuration was checked while the listener was running" >&2
  exit 91
fi
exec /usr/sbin/sshd "$@"
'''

with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory).resolve()
    binary = fixture / "bin"
    state = fixture / "state"
    calls = fixture / "calls"
    for path in (binary, state):
        path.mkdir()

    def command(name, body, python=False):
        path = binary / name
        path.write_text((f"#!{sys.executable}\n" if python else "") + body)
        path.chmod(0o755)
        return str(path)

    launchctl = command("launchctl", LAUNCHCTL)
    sudo = command("sudo", SUDO)
    tailscale = command("tailscale", TAILSCALE)
    ssh_keygen = command("ssh-keygen", SSH_KEYGEN)
    fake_sshd = command("sshd", FAKE_SSHD, python=True)
    dscl = command("dscl", FAKE_DSCL, python=True)
    dseditgroup = command("dseditgroup", FAKE_DSEDITGROUP, python=True)
    command("brew", FORBIDDEN)
    offline_tailscale = command("tailscale-offline", FORBIDDEN)

    repo = fixture / "repo"
    (repo / ".ssh").mkdir(parents=True)
    keys = fixture / "keys"
    keys.mkdir()
    subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "phone",
                    "-f", str(keys / "phone")], check=True)
    phone_line = (keys / "phone.pub").read_text().strip()
    fixtures = {"personal.pub": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPersonal personal\n",
                "work.pub": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIWork work\n",
                "phone.pub": phone_line + "\n",
                "options.pub": 'command="true" ' + phone_line + "\n",
                "two.pub": phone_line + "\n" + phone_line + "\n",
                "private.pub": (keys / "phone").read_text()}
    for name, text in fixtures.items():
        (repo / ".ssh" / name).write_text(text)
    host_keys = fixture / "hostkeys"
    host_keys.mkdir()
    subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                    "-f", str(host_keys / "ssh_host_ed25519_key")], check=True)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    open_port = listener.getsockname()[1]

    def accept_forever():
        while True:
            connection, _ = listener.accept()
            connection.close()

    threading.Thread(target=accept_forever, daemon=True).start()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]

    home = fixture / "home"
    managed = fixture / "etc/sshd_config.d/010-remote-login.conf"
    managed.parent.mkdir(parents=True)
    base = {"home": str(home), "repo_dir": str(repo), "platform": "mac", "profile": "personal", "user": USER,
            "shell_path": "/bin/zsh", "ssh_agent_socket": "/tmp/test-agent.sock",
            "pnpm_home": str(home / "Library/pnpm"), "mise": str(binary / "mise"),
            "brew_prefix": str(fixture / "brew"),
            "personal_public_ssh_key": "personal.pub", "work_public_ssh_key": "work.pub",
            "remote_login_public_keys": ["phone.pub"],
            "remote_login_sources": ["100.64.0.0/10", "fd7a:115c:a1e0::/48"],
            "manage_ssh_config": False, "install_dotfiles": False,
            "manage_remote_login": False, "revoke_remote_login": False,
            "remote_login_sshd_file": str(managed), "tailscale_cli": tailscale,
            "remote_login_sshd": [fake_sshd], "remote_login_launchctl": launchctl,
            "remote_login_sudo": [sudo], "remote_login_ssh_keygen": ssh_keygen,
            "remote_login_dscl": dscl, "remote_login_dseditgroup": dseditgroup,
            "remote_login_host_key": str(host_keys / "ssh_host_ed25519_key"),
            "remote_login_config_owner": str(os.getuid()), "remote_login_config_group": str(os.getgid()),
            "remote_login_port": open_port, "remote_login_port_timeout": 2}
    for key, value in base.items():
        assert not (isinstance(value, str) and value.startswith(("/etc", "/bin/launchctl", "/usr/sbin"))), key
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "SSH_AUTH_SOCK", "SUDO_ASKPASS")
                   and not key.startswith(("TEST_", "MISE_"))}
    environment.update(PATH=f"{binary}:/usr/bin:/bin:/usr/sbin:/sbin", HOME=str(home),
                       MISE_DATA_DIR=str(fixture / "mise-data"), TEST_CALLS=str(calls),
                       TEST_STATE=str(state), TEST_MANAGED=str(managed))

    def invoke(action, check=False, env=None, **overrides):
        calls.write_text("")
        config = dict(base, **overrides)
        return subprocess.run([sys.executable, "-c", RUNNER, str(root / "scripts"), action, json.dumps(config),
                               "1" if check else "0"],
                              env=dict(environment, **(env or {})), text=True, capture_output=True)

    def succeeds(result):
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    def fails(result, *expected):
        output = result.stdout + result.stderr
        assert result.returncode == 1 and "ERROR: " in result.stderr, output
        for text in expected:
            assert text in result.stderr, f"{text!r} missing from:\n{output}"

    def logged():
        return calls.read_text().splitlines()

    def index(prefix, last=False):
        lines = [number for number, line in enumerate(logged()) if line.startswith(prefix)]
        assert lines, f"{prefix!r} was not called:\n{calls.read_text()}"
        return lines[-1] if last else lines[0]

    # Common guards.
    fails(invoke("shields-up"), "Unknown security action")
    fails(invoke("ssh", user="root", manage_ssh_config=True), "not root")
    fails(invoke("remote-login-check", profile="guest"), "Unsupported profile")
    print("PASS: unknown actions, root and invalid profiles are refused")

    # Managed SSH client configuration.
    ssh_dir = home / ".ssh"
    (ssh_dir / "agent").mkdir(parents=True)
    (ssh_dir / "agent/placeholder").write_text("agent state\n")
    (ssh_dir / "config").write_text("# original SSH config\n")
    backups = home / ".dev-setup-backups"
    for system in ("mac", "linux"):
        succeeds(invoke("ssh", platform=system, env={"SSH_AUTH_SOCK": "/tmp/forwarded-agent"}))
        assert (ssh_dir / "config").read_text() == "# original SSH config\n" and not backups.exists()
    succeeds(invoke("ssh", check=True, manage_ssh_config=True))
    assert (ssh_dir / "config").read_text() == "# original SSH config\n" and not backups.exists()
    fails(invoke("ssh", manage_ssh_config=True, personal_public_ssh_key="private.pub"), "private key")
    fails(invoke("ssh", manage_ssh_config=True, personal_public_ssh_key="missing.pub"), "missing.pub")
    assert (ssh_dir / "config").read_text() == "# original SSH config\n" and not backups.exists()
    print("PASS: declined, previewed or invalid managed SSH leaves files and backups untouched on both platforms")

    succeeds(invoke("ssh", manage_ssh_config=True))
    first = (ssh_dir / "config").read_text()
    assert 'IdentityAgent "/tmp/test-agent.sock"' in first
    assert "Host github.com\n  HostName github.com\n  # Downloaded from 1Password App\n" \
           "  IdentityFile ~/.ssh/personal.pub\n" in first
    assert "Host github-alt.com\n  HostName github.com\n  # Downloaded from 1Password App\n" \
           "  IdentityFile ~/.ssh/work.pub\n" in first
    succeeds(invoke("ssh", manage_ssh_config=True, platform="linux", profile="work",
                    ssh_agent_socket=str(home / ".1password/agent.sock"),
                    env={"SSH_AUTH_SOCK": "/tmp/forwarded-agent"}))
    second = (ssh_dir / "config").read_text()
    assert 'IdentityAgent "SSH_AUTH_SOCK"' in second and "/tmp/forwarded-agent" not in second
    assert "  IdentityFile ~/.ssh/work.pub\n  IdentitiesOnly yes\n\nHost github-alt.com" in second
    runs = sorted(backups.iterdir())
    assert len(runs) == 2 and all(run.stat().st_mode & 0o777 == 0o700 for run in runs)
    assert (runs[0] / "ssh/config").read_text() == "# original SSH config\n"
    assert (runs[1] / "ssh/config").read_text() == first
    assert not (runs[0] / "ssh/agent").exists(), "The agent directory was copied into a backup"
    assert ssh_dir.stat().st_mode & 0o777 == 0o700
    for name in ("config", "personal.pub", "work.pub"):
        assert (ssh_dir / name).stat().st_mode & 0o777 == 0o600, name
    assert (ssh_dir / "work.pub").read_text() == fixtures["work.pub"]
    assert (ssh_dir / "agent/placeholder").read_text() == "agent state\n"
    succeeds(invoke("ssh", manage_ssh_config=True, platform="linux"))
    assert 'IdentityAgent "/tmp/test-agent.sock"' in (ssh_dir / "config").read_text()
    assert len(list(backups.iterdir())) == 3
    print("PASS: managed SSH keeps unique successive backups, profile keys, private modes and Linux agent forwarding")

    # Remote Login.
    authorized_keys = ssh_dir / "authorized_keys"
    running, disabled, access = state / "running", state / "disabled", state / "access.json"
    old_keys = "ssh-ed25519 AAAA lost-phone-fixture\n"
    original_config = "# Administrator policy before setup\nDenyUsers *\n"

    def reset(service_running=True, service_disabled=False, config_text=original_config):
        authorized_keys.write_text(old_keys)
        authorized_keys.chmod(0o600)
        if service_running:
            running.touch()
        else:
            running.unlink(missing_ok=True)
        if service_disabled:
            disabled.touch()
        else:
            disabled.unlink(missing_ok=True)
        if managed.is_symlink() or managed.is_file():
            managed.unlink()
        elif managed.is_dir():
            managed.rmdir()
        if config_text is not None:
            managed.write_text(config_text)
            managed.chmod(0o600)
        access.write_text(json.dumps({"exists": True, "members": [USER, "intruder"],
                                      "nested": {"GUID-ADMIN": "admin", "GUID-ORPHAN": None}}))

    def unchanged(config_text=original_config, service_running=True):
        assert authorized_keys.read_text() == old_keys, "Authorised keys changed"
        assert running.exists() == service_running and disabled.exists() != service_running
        assert (managed.read_text() if managed.exists() else None) == config_text, "Managed configuration changed"
        assert json.loads(access.read_text())["members"] == [USER, "intruder"], "Access list changed"

    reset()
    for action, flags in (("remote-login", {}), ("remote-login-revoke", {}),
                          ("remote-login", {"manage_remote_login": True, "revoke_remote_login": True})):
        succeeds(invoke(action, **flags))
        unchanged()
        assert logged() == [], calls.read_text()
    for action, flag in (("remote-login", "manage_remote_login"), ("remote-login-revoke", "revoke_remote_login")):
        fails(invoke(action, platform="linux", **{flag: True}), "macOS only")
        assert logged() == []
    print("PASS: Remote Login and revocation act only on explicit macOS opt-in; revocation wins over enablement")

    if not IS_MAC:
        fails(invoke("remote-login", manage_remote_login=True), "macOS only")
        fails(invoke("remote-login-check"), "macOS only")
        assert logged() == []
        print("SKIP: Remote Login executable-state checks need macOS; non-macOS refusal confirmed")
        sys.exit(0)

    for action, flag in (("remote-login", "manage_remote_login"), ("remote-login-revoke", "revoke_remote_login")):
        for variable in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
            fails(invoke(action, env={variable: "remote-session"}, **{flag: True}), "local console")
            assert logged() == []
            unchanged()
    print("PASS: detected SSH sessions cannot enable or revoke Remote Login")

    output = succeeds(invoke("remote-login-check", env={"SSH_CONNECTION": "remote-session"}))
    assert "Prerequisites passed" in output and "100.100.100.10" in output
    assert {line.split()[0] for line in logged()} == {"tailscale", "ssh-keygen"}, calls.read_text()
    unchanged()
    assert not any(run.name.startswith("remote-login") for run in backups.rglob("*"))
    print("PASS: the read-only preflight runs remotely without sudo, services or key changes")

    preflight_failures = [
        ({"remote_login_public_keys": []}, {}, "remote_login_public_keys"),
        ({"remote_login_sources": []}, {}, "remote_login_sources"),
        ({"remote_login_public_keys": ["options.pub"]}, {}, "without options"),
        ({"remote_login_public_keys": ["two.pub"]}, {}, "exactly one line"),
        ({"remote_login_public_keys": ["private.pub"]}, {}, "private key"),
        ({"remote_login_public_keys": ["../keys/phone.pub"]}, {}, "plain file names"),
        ({"remote_login_sources": ["100.64.0.0/10 *"]}, {}, "one address or range"),
        ({}, {"TEST_TAILSCALE_STATE": "Stopped"}, "not connected"),
        ({}, {"TEST_TAILSCALE_IPS": ""}, "no tailnet address"),
        ({"tailscale_cli": str(fixture / "missing-tailscale")}, {}, "not connected"),
    ]
    for overrides, env, message in preflight_failures:
        for action, check in (("remote-login-check", False), ("remote-login", False), ("remote-login", True)):
            fails(invoke(action, check=check, env=env, manage_remote_login=True, **overrides), message)
            assert not any(line.startswith(("sudo", "launchctl", "sshd", "dscl", "dseditgroup"))
                           for line in logged()), calls.read_text()
            unchanged()
    output = succeeds(invoke("remote-login", check=True, manage_remote_login=True))
    assert "Check mode does not stop Remote Login" in output
    assert {line.split()[0] for line in logged()} == {"tailscale", "ssh-keygen"}
    unchanged()
    print("PASS: phone-key, source and Tailscale preflight failures and check mode stop before sudo or changes")

    enable = {"manage_remote_login": True}
    fails(invoke("remote-login", env={"TEST_REMOTE_STOP_FAIL": "1"}, **enable),
          "Could not stop Remote Login", "bootout refused", "No SSH configuration or keys have been replaced")
    unchanged()
    assert not any(line.startswith("sshd") for line in logged())
    print("PASS: a listener stop failure prevents configuration validation and writes")

    for kind in ("symlink", "directory"):
        reset(config_text=None)
        if kind == "symlink":
            (fixture / "link-target").write_text(original_config)
            managed.symlink_to(fixture / "link-target")
        else:
            managed.mkdir()
        fails(invoke("remote-login", **enable), "must be absent or a regular file", "remains disabled")
        assert disabled.exists() and not running.exists()
        assert authorized_keys.read_text() == old_keys and not any(line.startswith("sshd") for line in logged())
        assert managed.is_symlink() if kind == "symlink" else managed.is_dir()
        assert (fixture / "link-target").read_text() == original_config
        index("launchctl bootout")
    print("PASS: symbolic-link or non-regular managed configuration is refused after stopping, without writes")

    gate_failures = [({"TEST_SSHD_EXTRA_MATCH": "Match Address 192.0.2.0/24"}, "another file adds a Match block"),
                     ({"TEST_SSHD_EXTRA_LINES": "denyusers someone"}, "DenyUsers"),
                     ({"TEST_SSHD_EXTRA_LINES": "passwordauthentication yes;allowusers *"},
                      "would not apply the Remote Login limits"),
                     ({"TEST_SSHD_SYNTAX_FAIL": "1"}, "Bad configuration option")]
    for env, message in gate_failures:
        for existed in (True, False):
            reset(config_text=original_config if existed else None)
            fails(invoke("remote-login", env=env, **enable), "Remote Login remains disabled",
                  "Original failure", message)
            assert disabled.exists() and not running.exists()
            if existed:
                assert managed.read_text() == original_config and managed.stat().st_mode & 0o777 == 0o600
                assert managed.stat().st_uid == os.getuid()
            else:
                assert not managed.exists(), "Rejected first-install configuration was left behind"
            assert authorized_keys.read_text() == old_keys, "Keys were replaced before the gate passed"
            assert json.loads(access.read_text())["members"] == [USER, "intruder"]
            assert not any(line.startswith(("launchctl enable", "launchctl bootstrap", "dseditgroup"))
                           for line in logged())
            assert index("launchctl bootout") < index("sshd")
    print("PASS: rejected configuration restores the previous bytes and metadata or removes the new file; SSH stays off")

    local_bin = home / ".local/bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    (local_bin / "mosh-server").write_text("#!/bin/sh\n")
    (local_bin / "mosh-server").chmod(0o755)
    expected_path = ":".join([str(local_bin), str(fixture / "mise-data/shims"), str(fixture / "brew/bin"),
                              "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    reset()
    output = succeeds(invoke("remote-login", **enable))
    deployed = managed.read_text()
    assert f"AllowUsers {USER}@100.64.0.0/10 {USER}@fd7a:115c:a1e0::/48\n" in deployed
    assert f"SetEnv PATH={expected_path}\n" in deployed and "Match all\n" in deployed
    assert managed.stat().st_mode & 0o777 == 0o644
    assert authorized_keys.read_text() == \
        "# Managed by mac-dev-machine-setup. The remote-login task replaces this file.\n" + phone_line + "\n"
    assert authorized_keys.stat().st_mode & 0o777 == 0o600
    digest = hashlib.sha1(old_keys.encode()).hexdigest()
    key_backups = list(backups.glob(f"*/remote-login-{digest}/authorized_keys"))
    assert len(key_backups) == 1 and key_backups[0].read_text() == old_keys
    assert key_backups[0].stat().st_mode & 0o777 == 0o600 and ssh_dir not in key_backups[0].parents
    assert json.loads(access.read_text()) == {"exists": True, "members": [USER], "nested": {}}
    assert running.exists() and not disabled.exists()
    assert index("tailscale") < index("sudo -v") == index("sudo ") < index("launchctl")
    assert index("launchctl bootout") < index("sshd") and index("sshd -T", last=True) < index("dseditgroup")
    assert index("dseditgroup", last=True) < index("launchctl enable") < index("launchctl bootstrap")
    assert not any(line.startswith("forbidden") for line in logged())
    for tool in (launchctl, fake_sshd, "/usr/bin/install", "/bin/cat"):
        assert any(line.startswith(f"sudo {tool} ") for line in logged()), tool
    assert "Host: test-mac.example.ts.net (100.100.100.10)" in output and f"User: {USER}" in output
    assert "ED25519" in output and "Shields Up is unchanged" in output
    assert "mosh-server is not on the SSH PATH" not in output
    print("PASS: enablement stops first, gates the deployed file, then replaces keys and access before activation")

    second_digest = hashlib.sha1(authorized_keys.read_bytes()).hexdigest()
    succeeds(invoke("remote-login", **enable))
    assert not list(backups.glob(f"*/remote-login-{second_digest}")), "Unchanged keys were backed up again"
    assert not any(line.startswith("dseditgroup") for line in logged()), "A correct access list was edited"
    print("PASS: a repeated enablement keeps unchanged keys and access lists without extra backups or edits")

    activation_failures = [({"TEST_REMOTE_BOOTSTRAP_FAIL": "1"}, {}, "bootstrap: Input/output error"),
                           ({}, {"remote_login_port": closed_port, "remote_login_port_timeout": 0.5},
                            f"127.0.0.1:{closed_port}")]
    for env, overrides, message in activation_failures:
        reset()
        fails(invoke("remote-login", env=env, **enable, **overrides),
              "activation failed and it has been disabled again", "Original failure", message)
        assert disabled.exists() and not running.exists()
        assert index("launchctl bootstrap") < index("launchctl bootout", last=True)
    reset(service_running=False, service_disabled=True)
    fails(invoke("remote-login", env={"TEST_REMOTE_BOOTSTRAP_FAIL": "1", "TEST_REMOTE_STOP_FAIL": "1"}, **enable),
          "shutdown could not be confirmed", "bootout refused", "Original activation failure",
          "bootstrap: Input/output error")
    print("PASS: activation and port-check failures disable Remote Login again and report the original failure")

    reset()
    managed.write_text(deployed)
    revoke = {"revoke_remote_login": True, "remote_login_public_keys": [], "tailscale_cli": offline_tailscale,
              "brew_prefix": str(fixture / "missing-brew")}
    output = succeeds(invoke("remote-login-revoke", check=True, **revoke))
    assert "Check mode only" in output and logged() == []
    unchanged(config_text=deployed)
    output = succeeds(invoke("remote-login-revoke", **revoke))
    assert authorized_keys.read_text() == "" and authorized_keys.stat().st_mode & 0o777 == 0o600
    assert disabled.exists() and not running.exists() and managed.read_text() == deployed
    assert any(backup.read_text() == old_keys for backup in backups.glob("*/remote-login-*/authorized_keys"))
    assert not any(line.startswith(("forbidden", "tailscale", "sshd", "dscl", "dseditgroup", "ssh-keygen",
                                    "launchctl enable", "launchctl bootstrap")) for line in logged()), calls.read_text()
    assert "Existing SSH and mosh sessions may remain active" in output
    reset()
    fails(invoke("remote-login-revoke", env={"TEST_REMOTE_STOP_FAIL": "1"}, **revoke),
          "Could not stop Remote Login", "Authorised keys have not been changed")
    assert authorized_keys.read_text() == old_keys
    print("PASS: offline revocation needs no Tailscale, Homebrew or phone keys, backs up and clears keys, and stays off")

    sshd = Path("/usr/sbin/sshd")
    if sshd.exists():
        real_sshd = command("sshd-real", REAL_SSHD)
        main = fixture / "sshd/sshd_config"
        main.parent.mkdir()
        dropins = managed.parent
        for stale in dropins.iterdir():
            stale.unlink()
        real = {"remote_login_sshd": [real_sshd, "-f", str(main), "-h", str(host_keys / "ssh_host_ed25519_key")]}
        (dropins / "000-earlier.conf").write_text(
            "PasswordAuthentication yes\nAuthenticationMethods any\nPubkeyAuthentication no\n"
            "AuthorizedKeysFile .ssh/authorized_keys .ssh/extra_keys\nSetEnv LANG=C\n")
        (dropins / "100-later.conf").write_text("KbdInteractiveAuthentication yes\nAllowUsers " + USER + "\n")
        include = f"Include {dropins}/*\n"
        cases = [("weaker global settings", include, None),
                 ("another Match block", include + "Match Address 192.168.0.0/16\n    AllowUsers *\n",
                  "another file adds a Match block"),
                 ("managed file not read", "PasswordAuthentication no\n", "does not read"),
                 ("a rule that can block the account", include + f"DenyUsers {USER}\n", "DenyUsers"),
                 ("a setting that refuses every connection", include + "RefuseConnection yes\n", None)]
        for name, text, message in cases:
            main.write_text(text)
            reset()
            result = invoke("remote-login", **enable, **real)
            if name == "a setting that refuses every connection":
                fails(result, "Remote Login remains disabled")
            elif message:
                fails(result, "Remote Login remains disabled", message)
            else:
                succeeds(result)
                assert running.exists() and not disabled.exists(), name
                # Check the deployed limits with the real sshd before a later case restores the old file.
                effective = subprocess.run(
                    [str(sshd), "-T", "-f", str(main), "-h", str(host_keys / "ssh_host_ed25519_key"),
                     "-C", f"user={USER},host=test,addr=100.64.0.1"], text=True, capture_output=True, check=True)
                lines = effective.stdout.splitlines()
                assert "passwordauthentication no" in lines and "authenticationmethods publickey" in lines
                assert [line for line in lines if line.startswith("allowusers ")] == [
                    f"allowusers {USER}@100.64.0.0/10", f"allowusers {USER}@fd7a:115c:a1e0::/48"]
                continue
            assert managed.read_text() == original_config and disabled.exists() and not running.exists(), name
            assert authorized_keys.read_text() == old_keys, name
        print("PASS: the real sshd gate accepts the managed limits over weaker files and refuses other Match "
              "blocks, unread files and account-blocking settings")
    else:
        print("SKIP: the real sshd gate needs /usr/sbin/sshd")
