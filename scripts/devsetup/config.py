"""Load defaults.toml plus explicit local overrides into one plain config dict.

Validation happens here, before any module does mutable work: the OS must be
ARM64 macOS or ARM64 Ubuntu, the profile personal or work, and the caller a
normal user. Detection inputs are keyword arguments so checks can describe a
host without overriding the real one through the environment.
"""
from __future__ import annotations

import os
import pwd
import shutil
import tomllib
from pathlib import Path
from typing import Mapping, Sequence

PROFILES = ("personal", "work")
DEFAULT_PROFILE = "personal"
PLATFORMS = ("mac", "linux")
PER_RUN_FLAGS = ("manage_ssh_config", "install_dotfiles", "manage_remote_login", "revoke_remote_login")
STRING_KEYS = ("git_email", "git_name", "dotfiles_repo", "dotfiles_version",
               "personal_public_ssh_key", "work_public_ssh_key", "shell_path",
               "ssh_agent_socket", "pnpm_home", "brew_prefix")
LIST_KEYS = ("dotfiles_conflict_paths", "remote_login_public_keys", "remote_login_sources",
             "pnpm_global_packages")
MAC_PATH_KEYS = ("remote_login_sshd_file", "tailscale_cli")
PATH_KEYS = ("shell_path", "pnpm_home", "brew_prefix") + MAC_PATH_KEYS
# Detected per run; a settings file cannot replace them.
DETECTED_KEYS = ("home", "repo_dir", "platform", "user", "mise")


class ConfigError(RuntimeError):
    """Invalid host, profile, or settings; raised before any change is made."""


def detect_platform(system: str, machine: str, os_release: Path) -> str:
    """Return 'mac' or 'linux' for supported ARM64 hosts, else raise ConfigError."""
    if system == "Darwin":
        if machine != "arm64":
            raise ConfigError(f"Only Apple silicon (arm64) Macs are supported, not {machine}. "
                              "Run setup natively, not under Rosetta.")
        return "mac"
    if system == "Linux":
        if machine not in ("aarch64", "arm64"):
            raise ConfigError(f"Only ARM64 (aarch64) Ubuntu is supported, not {machine}.")
        if _os_release_id(os_release) != "ubuntu":
            raise ConfigError("Only Ubuntu is supported on Linux.")
        return "linux"
    raise ConfigError("Only macOS and Ubuntu are supported.")


def _os_release_id(path: Path) -> str:
    try:
        lines = path.read_text().splitlines()
    except OSError as error:
        raise ConfigError(f"Cannot read {path} to identify the Linux distribution: {error}") from error
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() == "ID":
            return value.strip().strip("'\"")
    return ""


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as error:
        raise ConfigError(f"Cannot read settings file {path}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"Invalid TOML in {path}: {error}") from error


def _layer(settings: dict, platform: str, source: Path) -> dict:
    """Flatten one file: shared keys, then the table for the detected platform."""
    for key in DETECTED_KEYS + ("machine_type",):
        if key in settings:
            hint = " Use --profile or 'profile' instead." if key == "machine_type" else ""
            raise ConfigError(f"{source}: '{key}' cannot be set in a settings file.{hint}")
    merged = {key: value for key, value in settings.items() if key not in PLATFORMS}
    table = settings.get(platform, {})
    if not isinstance(table, dict):
        raise ConfigError(f"{source}: [{platform}] must be a table.")
    for key in DETECTED_KEYS + ("profile",):
        if key in table:
            raise ConfigError(f"{source}: '{key}' cannot be set in [{platform}].")
    merged.update(table)
    return merged


def _select_profile(cli_profile: str | None, environ: Mapping[str, str],
                    file_profiles: Sequence[tuple[Path, object]]) -> str:
    sources = []
    if cli_profile is not None:
        sources.append(("--profile", cli_profile))
    if environ.get("DEVSETUP_PROFILE"):
        sources.append(("DEVSETUP_PROFILE", environ["DEVSETUP_PROFILE"]))
    sources.extend((str(path), value) for path, value in file_profiles)
    for source, value in sources:
        if value not in PROFILES:
            raise ConfigError(f"Unsupported profile {value!r} from {source}. Use personal or work.")
    chosen = {value for _, value in sources}
    if len(chosen) > 1:
        detail = ", ".join(f"{source}={value}" for source, value in sources)
        raise ConfigError(f"Conflicting profiles: {detail}.")
    return chosen.pop() if chosen else DEFAULT_PROFILE


def _validate(config: dict) -> None:
    for key in STRING_KEYS:
        if not isinstance(config.get(key), str) or not config[key]:
            raise ConfigError(f"Setting '{key}' must be a non-empty string.")
    for key in LIST_KEYS:
        value = config.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ConfigError(f"Setting '{key}' must be a list of non-empty strings.")
    for key in PER_RUN_FLAGS:
        if not isinstance(config.get(key), bool):
            raise ConfigError(f"Setting '{key}' must be true or false.")
    if config["platform"] == "mac":
        for key in MAC_PATH_KEYS:
            if not isinstance(config.get(key), str) or not config[key]:
                raise ConfigError(f"Setting '{key}' must be a non-empty string on macOS.")


def _expand(value: str, home: Path) -> str:
    if value == "~" or value.startswith("~/"):
        value = str(home) + value[1:]
    return value


def load(*, repo_dir: Path, profile: str | None = None, overrides: Sequence[Path] = (),
         flags: Mapping[str, bool] | None = None, mise: str | None = None,
         environ: Mapping[str, str] | None = None, system: str | None = None,
         machine: str | None = None, os_release: Path = Path("/etc/os-release"),
         euid: int | None = None, user: str | None = None) -> dict:
    """Return the merged, validated settings for this run.

    Precedence: defaults.toml (shared, then [mac]/[linux]), each explicit override
    file in order (shared, then platform table), then per-run ``flags``.
    """
    environ = os.environ if environ is None else environ
    if (os.geteuid() if euid is None else euid) == 0:
        raise ConfigError("Run setup as your normal user with sudo access, not root.")
    uname = os.uname()
    platform = detect_platform(uname.sysname if system is None else system,
                               uname.machine if machine is None else machine, os_release)

    repo_dir = Path(repo_dir).resolve()
    file_profiles = []
    config: dict = {}
    for path in (repo_dir / "defaults.toml", *map(Path, overrides)):
        layer = _layer(_read_toml(path), platform, path)
        if "profile" in layer:
            file_profiles.append((path, layer.pop("profile")))
        config.update(layer)

    for key, value in (flags or {}).items():
        if key not in PER_RUN_FLAGS:
            raise ConfigError(f"Unknown per-run flag '{key}'.")
        config[key] = value

    account = pwd.getpwuid(os.getuid())
    home = Path(environ.get("HOME") or account.pw_dir).resolve()
    config.update(platform=platform, home=str(home), repo_dir=str(repo_dir),
                  user=user or account.pw_name,
                  profile=_select_profile(profile, environ, file_profiles))
    _validate(config)

    for key in PATH_KEYS:
        if key in config:
            config[key] = _expand(config[key], home)
            if not Path(config[key]).is_absolute():
                raise ConfigError(f"Setting '{key}' must be an absolute path or start with ~/.")
    if platform == "linux" and environ.get("SSH_AUTH_SOCK"):
        config["ssh_agent_socket"] = "SSH_AUTH_SOCK"
    else:
        config["ssh_agent_socket"] = _expand(config["ssh_agent_socket"], home)

    mise = mise or shutil.which("mise", path=environ.get("PATH"))
    if not mise:
        raise ConfigError("mise is not installed. Run ./install.sh --bootstrap-only first.")
    if not Path(mise).is_absolute():
        raise ConfigError(f"The mise executable path must be absolute, not {mise!r}.")
    config["mise"] = mise
    return config
