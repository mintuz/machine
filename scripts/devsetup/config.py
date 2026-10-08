"""Load defaults.toml plus one optional override file into one plain config dict.

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
from typing import Mapping

PROFILES = ("personal", "work")
DEFAULT_PROFILE = "personal"
PLATFORMS = ("mac", "linux")
STEPS = ("ssh", "git", "cli", "remote-login", "gui", "zsh", "app-store",
         "osx", "node", "dotfiles", "dock")
PER_RUN_FLAGS = (*STEPS, "revoke_remote_login")
STRING_KEYS = ("git_email", "git_name", "dotfiles_repo", "dotfiles_version",
               "personal_public_ssh_key", "work_public_ssh_key", "shell_path",
               "ssh_agent_socket", "pnpm_home", "brew_prefix")
LIST_KEYS = ("dotfiles_conflict_paths", "remote_login_public_keys", "remote_login_sources",
             "pnpm_global_packages")
MAC_PATH_KEYS = ("remote_login_sshd_file", "tailscale_cli")
PATH_KEYS = ("shell_path", "pnpm_home", "brew_prefix", "brew") + MAC_PATH_KEYS
# Detected per run; a settings file cannot replace them.
DETECTED_KEYS = ("home", "repo_dir", "platform", "user", "mise")
# These substitutions belong to isolated direct module tests, not user settings.
# Keep the existing sshd and launchctl overrides available for validation.
TEST_ONLY_KEYS = (
    "remote_login_sudo", "remote_login_ssh_keygen", "remote_login_dscl",
    "remote_login_dseditgroup", "remote_login_host_key", "remote_login_port",
    "remote_login_port_timeout", "remote_login_config_owner", "remote_login_config_group",
)


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


def _merge(target: dict, layer: dict) -> None:
    """Merge ordinary settings by replacement and the finite steps table by key."""
    for key, value in layer.items():
        if key == "steps":
            target["steps"] = {**target.get("steps", {}), **value}
        else:
            target[key] = value


def _settings_table(table: dict, source: Path, label: str) -> None:
    forbidden = (*DETECTED_KEYS, "machine_type", "profile", *TEST_ONLY_KEYS)
    for key, value in table.items():
        if key in forbidden:
            raise ConfigError(f"{source}: '{key}' cannot be set in {label}.")
        if key == "steps":
            if not isinstance(value, dict):
                raise ConfigError(f"{source}: {label}.steps must be a table.")
            for step, enabled in value.items():
                if step not in STEPS:
                    raise ConfigError(f"{source}: unknown step '{step}' in {label}.steps.")
                if not isinstance(enabled, bool):
                    raise ConfigError(f"{source}: steps.{step} must be true or false.")


def _layer(settings: dict, platform: str, source: Path) -> dict:
    """Validate the complete file, then apply shared and selected-platform settings."""
    shared = {key: value for key, value in settings.items() if key not in PLATFORMS}
    _settings_table(shared, source, "shared settings")
    for name in PLATFORMS:
        table = settings.get(name, {})
        if not isinstance(table, dict):
            raise ConfigError(f"{source}: [{name}] must be a table.")
        _settings_table(table, source, f"[{name}]")
    merged = {}
    _merge(merged, shared)
    _merge(merged, settings.get(platform, {}))
    return merged


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


def _validate(config: dict) -> None:
    for key in STRING_KEYS:
        if not isinstance(config.get(key), str) or not config[key]:
            raise ConfigError(f"Setting '{key}' must be a non-empty string.")
    for key in LIST_KEYS:
        value = config.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ConfigError(f"Setting '{key}' must be a list of non-empty strings.")
    if not isinstance(config.get("revoke_remote_login"), bool):
        raise ConfigError("Setting 'revoke_remote_login' must be true or false.")
    steps = config.get("steps")
    if not isinstance(steps, dict) or set(steps) != set(STEPS):
        raise ConfigError("The defaults must define every supported step in [steps].")
    if not all(isinstance(value, bool) for value in steps.values()):
        raise ConfigError("Every [steps] value must be true or false.")
    if "remote_login_sshd" in config:
        command = config["remote_login_sshd"]
        if not isinstance(command, list) or not command or not all(
                isinstance(part, str) and part for part in command):
            raise ConfigError("Setting 'remote_login_sshd' must be a nonempty list of command arguments.")
    if "remote_login_launchctl" in config:
        command = config["remote_login_launchctl"]
        if not isinstance(command, str) or not Path(command).is_absolute():
            raise ConfigError("Setting 'remote_login_launchctl' must be an absolute executable path.")
    if config["platform"] == "mac":
        for key in MAC_PATH_KEYS:
            if not isinstance(config.get(key), str) or not config[key]:
                raise ConfigError(f"Setting '{key}' must be a non-empty string on macOS.")
        for key in ("macos_preferences", "dock_items"):
            rows = config.get(key)
            if not isinstance(rows, list) or not all(isinstance(row, list) and row
                    and all(isinstance(value, str) for value in row) for row in rows):
                raise ConfigError(f"Setting '{key}' must be a list of argument lists.")
        for row in config["macos_preferences"]:
            if len(row) not in (3, 4) or not all(row[:2]):
                raise ConfigError("Each macos_preferences entry needs a domain, key and value, "
                                  "with an optional value type.")
            if len(row) == 4 and row[2] not in ("-bool", "-int", "-float", "-string", "-date", "-data"):
                raise ConfigError(f"Unsupported macOS preference type {row[2]!r}.")
        for row in config["dock_items"]:
            if any(not part for part in row[1:]) or (row[0] and not Path(_expand(
                    row[0], Path(config["home"]))).is_absolute()):
                raise ConfigError("Each dock_items entry must start with an absolute path, ~/ or "
                                  "an empty spacer path, followed by nonempty arguments.")


def _expand(value: str, home: Path) -> str:
    if value == "~" or value.startswith("~/"):
        value = str(home) + value[1:]
    return value


def load(*, repo_dir: Path, profile: str | None = None, override: Path | None = None,
         flags: Mapping[str, bool] | None = None, mise: str | None = None,
         environ: Mapping[str, str] | None = None, system: str | None = None,
         machine: str | None = None, os_release: Path = Path("/etc/os-release"),
         euid: int | None = None, user: str | None = None) -> dict:
    """Return the merged, validated settings for this run.

    Precedence: defaults.toml (shared, then [mac]/[linux]), the optional ``override``
    file (shared, then platform table), then per-run ``flags``. Unknown keys pass
    through untouched; ``[steps]`` merges by key.
    """
    environ = os.environ if environ is None else environ
    if (os.geteuid() if euid is None else euid) == 0:
        raise ConfigError("Run setup as your normal user with sudo access, not root.")
    uname = os.uname()
    platform = detect_platform(uname.sysname if system is None else system,
                               uname.machine if machine is None else machine, os_release)

    repo_dir = Path(repo_dir).resolve()
    config: dict = {}
    files = [repo_dir / "defaults.toml"]
    if override is not None:
        files.append(Path(override))
    for path in files:
        _merge(config, _layer(_read_toml(path), platform, path))

    for key, value in (flags or {}).items():
        if key not in PER_RUN_FLAGS:
            raise ConfigError(f"Unknown per-run flag '{key}'.")
        if not isinstance(value, bool):
            raise ConfigError(f"Per-run choice '{key}' must be true or false.")
        if key == "revoke_remote_login":
            config[key] = value
        else:
            config["steps"][key] = value

    account = pwd.getpwuid(os.getuid())
    home = Path(environ.get("HOME") or account.pw_dir).resolve()
    config.update(platform=platform, home=str(home), repo_dir=str(repo_dir),
                  user=user or account.pw_name, profile=_select_profile(profile, environ))
    _validate(config)
    # Homebrew owns native formulae and casks; its executable defaults to the prefix.
    brew = config.setdefault("brew", f"{config['brew_prefix']}/bin/brew")
    if not isinstance(brew, str) or not brew:
        raise ConfigError("Setting 'brew' must be a non-empty string.")

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
