"""Load remote-login.toml and the optional remote-login.local.toml for the Remote Login commands.

Validation happens here, before any module does mutable work: the OS must be
ARM64 macOS or ARM64 Ubuntu, the profile personal or work, and the caller a
normal user. The local file is the owner's untracked copy of the settings;
it cannot set detected values or the private command substitutions that the
security checks inject directly.
"""
from __future__ import annotations

import os
import pwd
import tomllib
from pathlib import Path
from typing import Mapping

PROFILES = ("personal", "work")
DEFAULT_PROFILE = "personal"
SETTINGS_FILES = ("remote-login.toml", "remote-login.local.toml")
LIST_KEYS = ("remote_login_public_keys", "remote_login_sources")
PATH_KEYS = ("remote_login_sshd_file", "tailscale_cli")
# Detected or chosen per run; a settings file cannot set them.
RUN_KEYS = ("home", "repo_dir", "platform", "user", "profile", "revoke_remote_login")
# These substitutions belong to isolated direct module tests, not settings files.
# The remote_login_sshd list and remote_login_launchctl path stay available for validation.
TEST_ONLY_KEYS = (
    "remote_login_sudo", "remote_login_ssh_keygen", "remote_login_dscl",
    "remote_login_dseditgroup", "remote_login_host_key", "remote_login_port",
    "remote_login_port_timeout", "remote_login_config_owner", "remote_login_config_group",
)


class ConfigError(RuntimeError):
    """Invalid host, profile, or settings; raised before any change is made."""


def detect_platform() -> str:
    """Return 'mac' or 'linux' for supported ARM64 hosts, else raise ConfigError."""
    uname = os.uname()
    if uname.sysname == "Darwin":
        if uname.machine != "arm64":
            raise ConfigError(f"Only Apple silicon (arm64) Macs are supported, not {uname.machine}. "
                              "Run setup natively, not under Rosetta.")
        return "mac"
    if uname.sysname == "Linux":
        if uname.machine not in ("aarch64", "arm64"):
            raise ConfigError(f"Only ARM64 (aarch64) Ubuntu is supported, not {uname.machine}.")
        if _os_release_id(Path("/etc/os-release")) != "ubuntu":
            raise ConfigError("Only Ubuntu is supported on Linux.")
        return "linux"
    raise ConfigError("Only macOS and Ubuntu are supported.")


def _os_release_id(path: Path) -> str:
    try:
        for line in path.read_text().splitlines():
            if line.startswith("ID="):
                return line[3:].strip().strip('"')
    except OSError:
        pass
    return ""


def _read_settings(path: Path) -> dict:
    try:
        with path.open("rb") as source:
            settings = tomllib.load(source)
    except OSError as error:
        raise ConfigError(f"Cannot read settings file {path}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"Invalid TOML in {path}: {error}") from error
    for key in settings:
        if key in RUN_KEYS or key in TEST_ONLY_KEYS:
            raise ConfigError(f"{path}: '{key}' cannot be set in a settings file.")
    return settings


def _select_profile(cli_profile: str | None, environ: Mapping[str, str]) -> str:
    sources = []
    if cli_profile is not None:
        sources.append(("--profile", cli_profile))
    if environ.get("DEVSETUP_PROFILE"):
        sources.append(("DEVSETUP_PROFILE", environ["DEVSETUP_PROFILE"]))
    for source, value in sources:
        if value not in PROFILES:
            raise ConfigError(f"Unsupported profile {value!r} from {source}. Use personal or work.")
    chosen = {value for _, value in sources}
    if len(chosen) > 1:
        detail = ", ".join(f"{source}={value}" for source, value in sources)
        raise ConfigError(f"Conflicting profiles: {detail}.")
    return chosen.pop() if chosen else DEFAULT_PROFILE


def _validate(config: dict, home: Path) -> None:
    for key in LIST_KEYS:
        value = config.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ConfigError(f"Setting '{key}' must be a list of non-empty strings.")
    for key in PATH_KEYS:
        value = config.get(key)
        if not isinstance(value, str) or not value:
            raise ConfigError(f"Setting '{key}' must be a non-empty string.")
        if value == "~" or value.startswith("~/"):
            value = config[key] = str(home) + value[1:]
        if not Path(value).is_absolute():
            raise ConfigError(f"Setting '{key}' must be an absolute path or start with ~/.")
    if "remote_login_sshd" in config:
        command = config["remote_login_sshd"]
        if not isinstance(command, list) or not command or not all(
                isinstance(part, str) and part for part in command):
            raise ConfigError("Setting 'remote_login_sshd' must be a nonempty list of command arguments.")
    if "remote_login_launchctl" in config:
        command = config["remote_login_launchctl"]
        if not isinstance(command, str) or not Path(command).is_absolute():
            raise ConfigError("Setting 'remote_login_launchctl' must be an absolute executable path.")


def load(*, repo_dir: Path, profile: str | None = None, revoke: bool = False) -> dict:
    """Return the validated settings for this run.

    remote-login.toml loads first, then remote-login.local.toml when it exists;
    a later file replaces a key. Unknown keys pass through untouched.
    """
    if os.geteuid() == 0:
        raise ConfigError("Run setup as your normal user with sudo access, not root.")
    platform = detect_platform()
    repo_dir = Path(repo_dir).resolve()
    config: dict = {}
    for name in SETTINGS_FILES:
        path = repo_dir / name
        if path.exists() or name == SETTINGS_FILES[0]:
            config.update(_read_settings(path))
    account = pwd.getpwuid(os.getuid())
    home = Path(os.environ.get("HOME") or account.pw_dir).resolve()
    config.update(platform=platform, home=str(home), repo_dir=str(repo_dir), user=account.pw_name,
                  profile=_select_profile(profile, os.environ), revoke_remote_login=revoke)
    _validate(config, home)
    return config
