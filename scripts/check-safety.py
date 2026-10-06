#!/usr/bin/env python3
"""Check headless privilege handling, runtime-update failures, and Remote Login with fake tools."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory)
    binary = fixture / "bin"
    binary.mkdir()

    def command(name, body):
        path = binary / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"])
    command("sudo", 'exit "${TEST_SUDO_STATUS:-0}"')
    result = subprocess.run(["bash", str(root / "scripts/with-sudo-askpass.sh"),
                             "sh", "-c", "exit 23"], env=env, start_new_session=True,
                            text=True, capture_output=True)
    assert result.returncode == 23, result.stdout + result.stderr
    env["TEST_SUDO_STATUS"] = "1"
    result = subprocess.run(["bash", str(root / "scripts/with-sudo-askpass.sh"), "true"],
                            env=env, start_new_session=True, text=True, capture_output=True)
    assert result.returncode == 1 and "terminal" in result.stderr, result.stdout + result.stderr
    print("PASS: headless sudo uses existing authorization and preserves command failures")

    command("brew", 'printf "%s\\n" "$TEST_BREW_PREFIX"')
    command("npm", 'exit "${TEST_UPDATE_STATUS:-0}"')
    command("pnpm", 'exit 0')
    command("ollama", '''if [ "$1" = list ]; then
  printf 'NAME ID SIZE\nfirst:latest id 1\nsecond:latest id 2\n'
else
  printf '%s\n' "$2" >> "$TEST_PULLS"
  exit "${TEST_UPDATE_STATUS:-0}"
fi''')
    env.update(TEST_BREW_PREFIX=directory, TEST_PULLS=str(fixture / "pulls"))
    play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
             "environment": {"PATH": env["PATH"], "TEST_BREW_PREFIX": directory,
                             "TEST_PULLS": env["TEST_PULLS"],
                             "TEST_UPDATE_STATUS": "{{ test_update_status }}"},
             "vars": {"platform": "linux", "ansible_facts": {"env": {"HOME": directory}},
                      "pnpm_home": directory + "/pnpm"},
             "tasks": [{"ansible.builtin.import_tasks": str(root / "ansible/tasks/update.yaml")}]}]
    path = fixture / "check.yaml"
    path.write_text(json.dumps(play))
    for status in ("0", "42"):
        (fixture / "pulls").write_text("")
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path),
                                 "--tags", "runtime-update", "-e", "test_update_status=" + status],
                                env=env, text=True, capture_output=True)
        assert (result.returncode == 0) == (status == "0"), result.stdout + result.stderr
        expected = ["first:latest", "second:latest"] if status == "0" else ["first:latest"]
        assert (fixture / "pulls").read_text().splitlines() == expected, result.stdout + result.stderr
        if status != "0":
            assert "Update failures" in result.stdout, result.stdout + result.stderr
    print("PASS: runtime updates complete on success and return failures without masking an earlier model failure")

    target = fixture / "home"
    (target / ".ssh").mkdir(parents=True)
    (target / ".ssh/config").write_text("# original SSH config\n")
    for system, distribution in (("Darwin", "MacOSX"), ("Linux", "Ubuntu")):
        facts = {"env": {"HOME": str(target), "SSH_AUTH_SOCK": "/tmp/forwarded-agent"},
                 "system": system, "distribution": distribution,
                 "date_time": {"iso8601_basic": "declined"}}
        result = subprocess.run(["ansible-playbook", str(root / "local.yaml"), "--tags", "ssh",
                                 "-e", json.dumps({"ansible_facts": facts, "manage_ssh_config": False})],
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (target / ".ssh/config").read_text() == "# original SSH config\n"
        assert not (target / ".dev-setup-backups").exists()
    print("PASS: declining managed SSH leaves configuration untouched on both platforms")
    (fixture / ".ssh").mkdir()
    for profile in ("personal", "work"):
        (fixture / f".ssh/{profile}.pub").write_text("ssh-ed25519 AAAA test\n")
    for run, profile in (("first", "personal"), ("second", "work")):
        play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
                 "vars": {"ansible_facts": {"env": {"HOME": str(target)},
                                            "date_time": {"iso8601_basic": run}},
                          "machine_type": profile, "ssh_agent_socket": "SSH_AUTH_SOCK" if run == "second" else "/tmp/test-agent.sock",
                          "personal_public_ssh_key": "personal.pub", "work_public_ssh_key": "work.pub"},
                 "tasks": [{"ansible.builtin.import_tasks": str(root / "ansible/tasks/security.yaml")}]}]
        path.write_text(json.dumps(play))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path), "--tags", "packages,ssh"],
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
    backups = target / ".dev-setup-backups"
    assert (backups / "first/ssh/config").read_text() == "# original SSH config\n"
    assert "IdentityFile ~/.ssh/personal.pub" in (backups / "second/ssh/config").read_text()
    assert (target / ".ssh/config").stat().st_mode & 0o777 == 0o600
    assert 'IdentityAgent "SSH_AUTH_SOCK"' in (target / ".ssh/config").read_text()
    print("PASS: managed SSH preserves successive backups even with mixed preview/setup tags")

    command("brew", '''if [ "$1" = unlink ]; then
  printf 'unlinked\n' >> "$TEST_UNLINKS"
else
  printf '%s\n' "$TEST_BREW_PREFIX"
fi''')
    nvm_script = fixture / "opt/nvm/nvm.sh"
    nvm_script.parent.mkdir(parents=True)
    nvm_script.write_text('nvm() { printf "%s\\n" "$TEST_NVM_DEFAULT"; }\n')
    unlinks = fixture / "unlinks"
    for default, expected in (("N/A", ""), ("/usr/bin/node", ""),
                              (str(target / ".nvm/versions/node/v24/bin/node"), "unlinked\n")):
        unlinks.write_text("")
        play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
                 "environment": {"PATH": env["PATH"], "TEST_BREW_PREFIX": directory,
                                 "TEST_NVM_DEFAULT": default, "TEST_UNLINKS": str(unlinks)},
                 "vars": {"ansible_facts": {"env": {"HOME": str(target)}}},
                 "tasks": [{"ansible.builtin.import_tasks": str(root / "ansible/tasks/brew-unlink-node.yaml")}]}]
        path.write_text(json.dumps(play))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert unlinks.read_text() == expected, "Homebrew Node was unlinked without an nvm replacement"
    print("PASS: Homebrew Node is unlinked only after nvm has its own default runtime")

    (fixture / "nvm.sh").write_text('nvm() { case "$1" in install) return 42;; which) return 1;; *) return 0;; esac; }\n')
    play[0]["vars"].update(platform="linux", pnpm_home=str(target / "pnpm"), pnpm_global_packages=[])
    play[0]["tasks"] = [{"ansible.builtin.import_tasks": str(root / "ansible/tasks/node.yaml")}]
    path.write_text(json.dumps(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path),
                             "--start-at-task", "Install latest lts version of node"],
                            env=env, text=True, capture_output=True)
    assert result.returncode != 0, "An nvm installation failure was masked by a successful alias command"
    print("PASS: a failed Node installation stops setup")

    remote_calls = fixture / "remote-login-calls"
    command("tailscale", f'echo "$*" >> "{remote_calls}"\necho \'{{"BackendState": "Running", "Self": {{}}}}\'')
    remote_home = fixture / "remote-home"
    (remote_home / ".ssh").mkdir(parents=True)
    mac = {"system": "Darwin", "distribution": "MacOSX", "env": {"HOME": str(remote_home)},
           "user_id": "tester", "date_time": {"iso8601_basic": "remote"}}
    linux = dict(mac, system="Linux", distribution="Ubuntu")
    for facts, extra in ((mac, {}), (linux, {}), (linux, {"manage_remote_login": True}), (mac, {"manage_remote_login": True})):
        # --check and explicit empty keys keep the run harmless even if a guard regresses.
        result = subprocess.run(["ansible-playbook", str(root / "local.yaml"), "--check", "--tags", "remote-login", "-e",
                                 json.dumps({"ansible_facts": facts, "ansible_become": False, "remote_login_public_keys": [],
                                             "tailscale_cli": str(binary / "tailscale"), **extra})],
                                text=True, capture_output=True)
        if facts is mac and extra:
            assert result.returncode != 0 and "remote_login_public_keys" in result.stdout, result.stdout + result.stderr
        else:
            assert result.returncode == 0, result.stdout + result.stderr
    assert not remote_calls.exists() and not any((remote_home / ".ssh").iterdir())
    print("PASS: Remote Login runs only when requested on macOS, and stops before changes without phone keys")

    # Exercise the real preflight tasks from an SSH session in an isolated home.
    subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                    "-f", str(fixture / ".ssh/phone")], check=True)
    preflight_keys = remote_home / ".ssh/authorized_keys"
    preflight_keys.write_text("existing access must survive preflight\n")
    play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
             "vars": {"ansible_facts": dict(mac, env=dict(mac["env"], SSH_CONNECTION="remote-session")),
                      "ansible_become": False, "remote_login_public_keys": ["phone.pub"],
                      "remote_login_sources": ["100.64.0.0/10"],
                      "tailscale_cli": str(binary / "tailscale")},
             "tasks": [{"ansible.builtin.import_tasks": str(root / "ansible/tasks/mac/remote-login.yaml")}]}]
    path.write_text(json.dumps(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path),
                             "--check", "--tags", "remote-login-preflight"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert preflight_keys.read_text() == "existing access must survive preflight\n"
    assert not (remote_home / ".dev-setup-backups").exists()
    assert "changed=0" in result.stdout, result.stdout + result.stderr
    print("PASS: Remote Login preflight checks valid keys remotely without replacing existing access")

    # Exercise revocation through the real entry point without host services.
    remote_running = fixture / "remote-running"
    remote_disabled = fixture / "remote-disabled"
    remote_service_calls = fixture / "remote-service-calls"
    command("launchctl", '''
printf '%s\\n' "$*" >> "$TEST_REMOTE_CALLS"
case "$*" in
  "print-disabled system")
    if [ -f "$TEST_REMOTE_DISABLED" ]; then state=disabled; else state=enabled; fi
    printf '"com.openssh.sshd" => %s\\n' "$state" ;;
  "print system/com.openssh.sshd")
    if [ -f "$TEST_REMOTE_RUNNING" ]; then exit 0; else exit 113; fi ;;
  "disable system/com.openssh.sshd") touch "$TEST_REMOTE_DISABLED" ;;
  "bootout system/com.openssh.sshd")
    if [ "${TEST_REMOTE_STOP_FAIL:-0}" = 1 ]; then exit 5; fi
    rm -f "$TEST_REMOTE_RUNNING" ;;
  "enable system/com.openssh.sshd") rm -f "$TEST_REMOTE_DISABLED" ;;
  "bootstrap system /System/Library/LaunchDaemons/ssh.plist")
    touch "$TEST_REMOTE_RUNNING"
    if [ "${TEST_REMOTE_BOOTSTRAP_FAIL:-0}" = 1 ]; then exit 5; fi ;;
  *) exit 99 ;;
esac''')
    remote_env = dict(env, TEST_REMOTE_RUNNING=str(remote_running),
                      TEST_REMOTE_DISABLED=str(remote_disabled), TEST_REMOTE_CALLS=str(remote_service_calls))
    # Revocation must not depend on working Homebrew or Tailscale.
    forbidden_calls = fixture / "remote-forbidden-calls"
    command("brew", f'echo brew >> "{forbidden_calls}"\nexit 99')
    command("tailscale", f'echo tailscale >> "{forbidden_calls}"\nexit 99')
    old_phone_key = "ssh-ed25519 AAAA lost-phone-fixture\n"
    authorized_keys = remote_home / ".ssh/authorized_keys"
    authorized_keys.write_text(old_phone_key)
    remote_running.touch()
    revoke_vars = {"ansible_facts": mac, "ansible_become": False, "revoke_remote_login": True,
                   "remote_login_public_keys": [], "remote_login_launchctl": str(binary / "launchctl"),
                   "tailscale_cli": str(binary / "tailscale")}
    # A detected remote session must fail before shutdown or key replacement.
    for tag, opt_in in (("remote-login", "manage_remote_login"),
                        ("remote-login-revoke", "revoke_remote_login")):
        for variable in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
            remote_facts = dict(mac, env=dict(mac["env"], **{variable: "remote-session"}))
            request_vars = dict(revoke_vars, ansible_facts=remote_facts, revoke_remote_login=False)
            request_vars[opt_in] = True
            result = subprocess.run(
                ["ansible-playbook", str(root / "local.yaml"), "--tags", tag, "-e",
                 json.dumps(request_vars)],
                env=remote_env, text=True, capture_output=True)
            assert result.returncode != 0 and "local console" in result.stdout, result.stdout + result.stderr
            assert authorized_keys.read_text() == old_phone_key and remote_running.exists()
            assert not remote_disabled.exists() and not remote_service_calls.exists()
    print("PASS: detected SSH sessions cannot enable or revoke access through direct Ansible runs")

    for facts, opted_in, check_mode in ((linux, True, False), (mac, False, False), (mac, True, True)):
        args = ["ansible-playbook", str(root / "local.yaml"), "--tags", "remote-login-revoke", "-e",
                json.dumps(dict(revoke_vars, ansible_facts=facts, revoke_remote_login=opted_in))]
        result = subprocess.run(args + (["--check"] if check_mode else []),
                                env=remote_env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert authorized_keys.read_text() == old_phone_key and remote_running.exists()
        assert not remote_disabled.exists()
    result = subprocess.run(["ansible-playbook", str(root / "local.yaml"), "--tags", "remote-login-revoke",
                             "-e", json.dumps(revoke_vars)], env=remote_env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert authorized_keys.read_text() == "" and remote_disabled.exists() and not remote_running.exists()
    key_backups = list((remote_home / ".dev-setup-backups").rglob("authorized_keys"))
    assert any(backup.read_text() == old_phone_key for backup in key_backups)
    assert not forbidden_calls.exists(), "Revocation invoked Homebrew or Tailscale"
    assert not any(line.startswith(("enable ", "bootstrap ")) for line in remote_service_calls.read_text().splitlines())
    print("PASS: explicit macOS revocation removes the last key offline, preserves a backup, and leaves SSH disabled")

    activation_vars = dict(revoke_vars, platform="mac", manage_remote_login=True, revoke_remote_login=False)
    result = subprocess.run(["ansible-playbook", str(root / "local.yaml"), "--tags", "remote-login",
                             "--start-at-task", "Start Remote Login at boot", "-e", json.dumps(activation_vars)],
                            env=dict(remote_env, TEST_REMOTE_BOOTSTRAP_FAIL="1"), text=True, capture_output=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert remote_disabled.exists() and not remote_running.exists()
    assert authorized_keys.read_text() == "" and not forbidden_calls.exists()
    print("PASS: a partial SSH activation failure is reported and leaves startup and the listener disabled")

    sshd = Path("/usr/sbin/sshd")
    if os.uname().sysname == "Darwin" and sshd.exists():
        config = fixture / "sshd"
        (config / "sshd_config.d").mkdir(parents=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(config / "host_key")], check=True)
        managed = config / "sshd_config.d/010-remote-login.conf"
        settings = {"remote_login_allow_users": ["tester@100.64.0.0/10", "tester@fd7a:115c:a1e0::/48"],
                    "remote_login_path": "/opt/homebrew/bin:/usr/bin:/bin", "remote_login_sshd_file": str(managed),
                    "remote_login_sshd": [str(sshd), "-f", str(config / "sshd_config"), "-h", str(config / "host_key")],
                    "ansible_facts": {"user_id": "tester"}, "ansible_become": False}
        play = [{"hosts": "localhost", "connection": "local", "gather_facts": False, "vars": settings,
                 "tasks": [{"ansible.builtin.template": {
                               "src": str(root / "ansible/templates/sshd_remote_login.conf.j2"), "dest": str(managed)}},
                           {"ansible.builtin.import_tasks": str(root / "ansible/tasks/mac/remote-login-check.yaml")}]}]
        path.write_text(json.dumps(play))
        # Files before and after the managed file weaken global settings.
        (config / "sshd_config.d/000-earlier.conf").write_text(
            "PasswordAuthentication yes\nAuthenticationMethods any\nPubkeyAuthentication no\n"
            "AuthorizedKeysFile .ssh/authorized_keys .ssh/extra_keys\nSetEnv LANG=C\n")
        (config / "sshd_config.d/100-later.conf").write_text("KbdInteractiveAuthentication yes\nAllowUsers tester\n")
        include = f"Include {config}/sshd_config.d/*\n"
        cases = [("weaker global settings", lambda: include, True),
                 ("another Match block", lambda: include + "Match Address 192.168.0.0/16\n    AllowUsers tester\n", False),
                 ("managed file not read; its settings under a conditional Match",
                  lambda: managed.read_text().replace("Match all", "Match Address *,!192.168.0.0/16"), False),
                 ("a rule that can block the account", lambda: include + "DenyUsers tester\n", False),
                 ("a setting that refuses every connection", lambda: include + "RefuseConnection yes\n", False)]
        for name, main, passes in cases:
            (config / "sshd_config").write_text(main())
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)], text=True, capture_output=True)
            assert (result.returncode == 0) == passes, name + "\n" + result.stdout + result.stderr
        print("PASS: Remote Login SSH settings override weaker global settings, and other Match blocks or account rules stop the run")

        # The real deployment helper must stop acceptance before it validates or
        # replaces configuration, and restore rejected changes while staying off.
        command("sshd", '''
if [ -f "$TEST_REMOTE_RUNNING" ]; then
  echo "SSH configuration was checked while the listener was running" >&2
  exit 91
fi
exec /usr/sbin/sshd "$@"''')
        deployment_settings = dict(settings, remote_login_launchctl=str(binary / "launchctl"),
                                   remote_login_config_owner=str(os.getuid()),
                                   remote_login_config_group=str(os.getgid()),
                                   remote_login_sshd=[str(binary / "sshd"), "-f", str(config / "sshd_config"),
                                                      "-h", str(config / "host_key")])
        play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
                 "vars": deployment_settings,
                 "tasks": [{"ansible.builtin.import_tasks": str(root / "ansible/tasks/mac/remote-login-config.yaml")}]}]
        path.write_text(json.dumps(play))
        original_config = "# Administrator policy before setup\nDenyUsers *\n"
        for existed in (True, False):
            if existed:
                managed.write_text(original_config)
                managed.chmod(0o600)
            else:
                managed.unlink()
            remote_running.touch()
            remote_disabled.unlink(missing_ok=True)
            (config / "sshd_config").write_text(include + "Match Address 192.0.2.0/24\n    AllowUsers *\n")
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                    env=remote_env, text=True, capture_output=True)
            assert result.returncode != 0, result.stdout + result.stderr
            assert remote_disabled.exists() and not remote_running.exists()
            if existed:
                assert managed.read_text() == original_config
                assert managed.stat().st_mode & 0o777 == 0o600
            else:
                assert not managed.exists(), "Rejected first-install configuration was left behind"
        managed.write_text(original_config)
        remote_running.touch()
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                env=dict(remote_env, TEST_REMOTE_STOP_FAIL="1"), text=True, capture_output=True)
        assert result.returncode != 0, result.stdout + result.stderr
        assert managed.read_text() == original_config and remote_running.exists()
        (config / "sshd_config").write_text(include)
        remote_disabled.unlink(missing_ok=True)
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path), "--check"],
                                env=remote_env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert managed.read_text() == original_config and remote_running.exists() and not remote_disabled.exists()
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                env=remote_env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert remote_disabled.exists() and not remote_running.exists()
        effective = subprocess.run([str(sshd), "-T", "-f", str(config / "sshd_config"),
                                    "-h", str(config / "host_key"), "-C", "user=tester,host=test,addr=100.64.0.1"],
                                   text=True, capture_output=True, check=True)
        assert "passwordauthentication no" in effective.stdout.splitlines()
        assert [line for line in effective.stdout.splitlines() if line.startswith("allowusers ")] == [
            "allowusers tester@100.64.0.0/10", "allowusers tester@fd7a:115c:a1e0::/48"]
        print("PASS: rejected SSH configuration is restored or removed, stop failures prevent writes, and valid deployment stays off until activation")
    else:
        print("SKIP: the Remote Login SSH settings check needs macOS /usr/sbin/sshd")
