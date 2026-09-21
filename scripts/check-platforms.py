#!/usr/bin/env python3
"""Exercise the real inventory selector without installing anything."""
import json
import os
import pty
from pathlib import Path
import shutil
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
                                   "install_dotfiles | bool == " + str(platform == "mac").lower()]}}]}]
            path = fixture / "check.yaml"
            path.write_text(json.dumps(play))
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                    text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path),
                                     "-e", "manage_ssh_config=true test_manage=true"], text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
            print(f"PASS: {platform}/{profile} selects its layers, defaults, and optional SSH override")
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
    shutil.copy(root / "install.sh", fixture / "install.sh")
    (fixture / "scripts").mkdir()
    (fixture / "scripts/bootstrap-macos.sh").write_text('echo "bootstrap:$use_1password"\n')
    wrapper = fixture / "scripts/with-sudo-askpass.sh"
    wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    wrapper.chmod(0o755)
    (fixture / "bin").mkdir()
    uname = fixture / "bin/uname"
    uname.write_text('#!/bin/sh\necho Darwin\n')
    uname.chmod(0o755)
    env = dict(os.environ, PATH=str(fixture / "bin") + os.pathsep + os.environ["PATH"])
    for args, answer, expected in (([], None, "false"), ([], "y\n", "true"),
                                   ([], "n\n", "false"), ([], "\n", "false"),
                                   ([], "maybe\nyes\n", "true"),
                                   (["--1password-ssh"], None, "true"),
                                   (["--keep-ssh"], None, "false")):
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(["bash", str(fixture / "install.sh"), "work", *args],
                                       stdin=slave if answer is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            if answer is not None:
                os.write(master, answer.encode())
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stdout + stderr
            assert "bootstrap:" + expected in stdout and "manage_ssh_config=" + expected in stdout, stdout
            assert "machine_type=work" in stdout, stdout
            if answer is not None:
                assert "[y/N]" in stderr, stderr
        finally:
            os.close(master)
            os.close(slave)
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
    print("PASS: startup prompts before bootstrap, supports SSH flags, and preserves SSH without a terminal")
