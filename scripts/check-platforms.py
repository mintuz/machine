#!/usr/bin/env python3
"""Exercise the real inventory selector without installing anything."""
import json
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
                                   "manage_ssh_config | bool == " + str(platform == "mac").lower(),
                                   "install_dotfiles | bool == " + str(platform == "mac").lower()]}}]}]
            path = fixture / "check.yaml"
            path.write_text(json.dumps(play))
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                    text=True, capture_output=True)
            assert result.returncode == 0, result.stdout + result.stderr
            print(f"PASS: {platform}/{profile} selects its four layers and SSH/dotfiles defaults")
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
