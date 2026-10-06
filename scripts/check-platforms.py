#!/usr/bin/env python3
"""Exercise the real inventory selector without installing anything."""
import json
import os
import pty
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory)
    for platform in ("shared", "mac", "linux"):
        for profile in ("", "personal", "work"):
            folder = fixture / "packages" / platform / profile
            folder.mkdir(parents=True)
            (folder / "Brewfile.cli").write_text('brew "git"\n')
    shutil.copytree(root / "ansible/vars", fixture / "ansible/vars")
    for system, distribution, platform in (("Darwin", "MacOSX", "mac"), ("Linux", "Ubuntu", "linux")):
        for profile in ("personal", "work"):
            expected = [str(fixture / "packages" / layer / "Brewfile.cli") for layer in
                        ("shared", f"shared/{profile}", platform, f"{platform}/{profile}")]
            play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
                     "vars": {"ansible_facts": {"system": system, "distribution": distribution, "env": {"HOME": directory}}, "machine_type": profile},
                     "tasks": [{"ansible.builtin.import_tasks": str(root / "ansible/tasks/platform.yaml")},
                               {"ansible.builtin.assert": {"that": [
                                   "package_files == " + json.dumps(expected),
                                   "(manage_ssh_config | bool) == (test_manage | default(false) | bool)",
                                   "ssh_agent_socket == " + json.dumps("~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock" if platform == "mac" else "~/.1password/agent.sock"),
                                   "(install_dotfiles | bool) == (test_dotfiles | default(true) | bool)"]}}]}]
            path = fixture / "check.yaml"
            path.write_text(json.dumps(play))
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                    text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path),
                                     "-e", "manage_ssh_config=true test_manage=true install_dotfiles=false test_dotfiles=false"], text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
            print(f"PASS: {platform}/{profile} selects its layers, defaults, and SSH/dotfiles overrides")
    play[0]["vars"]["ansible_facts"]["env"]["SSH_AUTH_SOCK"] = "/tmp/session-specific-agent"
    play[0]["tasks"][-1] = {"ansible.builtin.assert": {"that": "ssh_agent_socket == 'SSH_AUTH_SOCK'"}}
    path.write_text(json.dumps(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    print("PASS: Ubuntu uses the forwarded agent variable rather than a session-specific socket path")
    play[0]["vars"]["machine_type"] = "../personal"
    path.write_text(json.dumps(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                            text=True, capture_output=True)
    assert result.returncode != 0 and "Unsupported OS or profile" in result.stdout, result.stdout + result.stderr
    print("PASS: invalid profile rejected")
    play[0]["vars"]["machine_type"] = "personal"
    play[0]["vars"]["ansible_facts"]["distribution"] = "Fedora"
    path.write_text(json.dumps(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                            text=True, capture_output=True)
    assert result.returncode != 0 and "Unsupported OS or profile" in result.stdout, result.stdout + result.stderr
    print("PASS: unsupported distribution rejected")

    play[0]["vars"]["ansible_facts"]["distribution"] = "Ubuntu"
    play[0]["tasks"] = play[0]["tasks"][:1]
    path.write_text(json.dumps(play))
    invalid = fixture / "packages/shared/Brewfile.clii"
    invalid.write_text('brew "git"\n')
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)], text=True, capture_output=True)
    assert result.returncode != 0 and "Invalid package inventory" in result.stdout, result.stdout + result.stderr
    invalid.unlink()
    (fixture / "packages/shared/Brewfile.cli").unlink()
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)], text=True, capture_output=True)
    assert result.returncode != 0 and "Missing shared CLI inventory" in result.stdout, result.stdout + result.stderr
    print("PASS: missing and misspelled package inventories are rejected")

result = subprocess.run(["bash", str(root / "install.sh"), "invalid"], text=True, capture_output=True)
assert result.returncode == 64 and "Usage:" in result.stderr, result.stdout + result.stderr
print("PASS: bootstrap rejects an invalid profile before installing anything")

# Exercise the actual startup prompt with a terminal; bootstrap and Ansible are inert.
with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory)
    installer = fixture / "install.sh"
    installer.write_text((root / "install.sh").read_text().replace(
        "source /etc/os-release", "source " + shlex.quote(str(fixture / "os-release"))))
    installer.chmod(0o755)
    (fixture / "os-release").write_text("ID=ubuntu\n")
    (fixture / "scripts").mkdir()
    (fixture / "scripts/bootstrap-macos.sh").write_text('echo "bootstrap:$use_1password"\n')
    (fixture / "scripts/bootstrap-ubuntu.sh").write_text('echo "bootstrap:$use_1password"\n')
    wrapper = fixture / "scripts/with-sudo-askpass.sh"
    wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    wrapper.chmod(0o755)
    (fixture / "scripts/remote-login.sh").write_text(
        'echo "remote-preflight"\nexit "${TEST_PREFLIGHT_STATUS:-0}"\n')
    (fixture / "bin").mkdir()
    uname = fixture / "bin/uname"
    uname.write_text('#!/bin/sh\nprintf "%s\\n" "${TEST_SYSTEM:-Darwin}"\n')
    uname.chmod(0o755)
    env = dict(os.environ, PATH=str(fixture / "bin") + os.pathsep + os.environ["PATH"])
    for variable in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
        env.pop(variable, None)
    cases = [
        ("Darwin", [], None, "false", "true"),
        ("Darwin", [], "y\n", "true", "true"),
        ("Darwin", [], "n\n", "false", "true"),
        ("Darwin", [], "\n", "false", "true"),
        ("Darwin", [], "maybe\nyes\n", "true", "true"),
        ("Darwin", ["--1password-ssh"], None, "true", "true"),
        ("Darwin", ["--keep-ssh", "--skip-dotfiles"], None, "false", "false"),
        ("Linux", [], None, "false", "true"),
        ("Linux", [], "n\n\n", "false", "true"),
        ("Linux", [], "y\nn\n", "true", "false"),
        ("Linux", [], "n\nmaybe\ny\n", "false", "true"),
        ("Linux", ["--keep-ssh", "--skip-dotfiles"], None, "false", "false"),
        ("Linux", ["--1password-ssh", "--dotfiles"], None, "true", "true"),
    ]
    for system, args, answer, expected, dotfiles in cases:
        env["TEST_SYSTEM"] = system
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(["bash", str(fixture / "install.sh"), "work", *args],
                                       stdin=slave if answer is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            if answer is not None:
                os.write(master, (answer + ("n\n" if system == "Darwin" else "")).encode())
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stdout + stderr
            assert "bootstrap:" + expected in stdout and "manage_ssh_config=" + expected in stdout, stdout
            assert "machine_type=work" in stdout and "install_dotfiles=" + dotfiles in stdout, stdout
            assert "manage_remote_login=false" in stdout and "remote-preflight" not in stdout, stdout
            if system == "Linux" and answer is not None:
                assert "[Y/n]" in stderr, stderr
            if answer is not None:
                assert "[y/N]" in stderr, stderr
        finally:
            os.close(master)
            os.close(slave)
    for profile, answer, remote_session, preflight_status, expected in (
        ("personal", "y\n", False, "0", "true"),
        ("personal", "\n", False, "0", "false"),
        ("personal", "maybe\nno\n", False, "0", "false"),
        ("personal", "\x04", False, "0", "false"),
        ("personal", "yes\n", False, "42", "true"),
        ("personal", "", True, "0", "false"),
        ("--bootstrap-only", "", False, "0", "false"),
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
            assert ("remote-preflight" in stdout) == (expected == "true"), stdout
            if preflight_status != "0" or profile == "--bootstrap-only":
                assert "ansible-playbook" not in stdout, "Setup ran despite failed preflight or bootstrap-only mode"
            else:
                assert "manage_remote_login=" + expected in stdout, stdout
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            os.close(master)
            os.close(slave)
    print("PASS: Remote Login prompt is opt-in, preserves access on EOF or remote sessions, and stops on preflight failure")
    env["TEST_SYSTEM"] = "Darwin"
    result = subprocess.run(["bash", str(fixture / "install.sh"), "--bootstrap-only", "--1password-ssh"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0 and "bootstrap:true" in result.stdout and "ansible-playbook" not in result.stdout
    shutil.copy(root / "new-mac.sh", fixture / "new-mac.sh")
    result = subprocess.run(["bash", str(fixture / "new-mac.sh"), "--keep-ssh"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0 and "bootstrap:false" in result.stdout and "ansible-playbook" not in result.stdout
    result = subprocess.run(["bash", str(fixture / "install.sh"), "--keep-ssh", "--1password-ssh"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 64 and "bootstrap:" not in result.stdout
    result = subprocess.run(["bash", str(fixture / "install.sh"), "--dotfiles", "--skip-dotfiles"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 64 and "bootstrap:" not in result.stdout
    print("PASS: startup SSH/dotfiles prompts, defaults, opt-outs, and unattended flags on both platforms")
