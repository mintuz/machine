#!/usr/bin/env python3
"""Check headless privilege handling and runtime-update failures with fake tools."""
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
    (fixture / ".ssh").mkdir()
    for profile in ("personal", "work"):
        (fixture / f".ssh/{profile}.pub").write_text("ssh-ed25519 AAAA test\n")
    for run, profile in (("first", "personal"), ("second", "work")):
        play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
                 "vars": {"ansible_facts": {"env": {"HOME": str(target)},
                                            "date_time": {"iso8601_basic": run}},
                          "machine_type": profile, "ssh_agent_socket": "/tmp/test-agent.sock",
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
