"""SSH client configuration and macOS Remote Login (SSH server) management.

run(action, config, check=False) is the only public entry point. Every
service, sshd, access-list and privileged file operation goes through
_System, whose commands come from config so that tests can substitute
stateful executables; shipped defaults use the macOS system tools.
"""
from __future__ import annotations

import datetime
import hashlib
import itertools
import json
import os
import platform as host_platform
import pwd
import re
import shutil
import socket
import stat
import string
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ACTIONS = ("ssh", "remote-login-check", "remote-login", "remote-login-revoke")
TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
SSH_SESSION_VARIABLES = ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")

SERVICE = "system/com.openssh.sshd"
SERVICE_PLIST = "/System/Library/LaunchDaemons/ssh.plist"
SERVICE_NOT_LOADED = 113
SERVICE_DISABLED = re.compile(r'"com[.]openssh[.]sshd" => (disabled|true)')
ACCESS_GROUP = "com.apple.access_ssh"
GATE_ADDRESSES = ("100.64.0.1", "192.0.2.1")
PUBLIC_KEY_LINE = re.compile(
    r"(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh[.]com"
    r"|sk-ecdsa-sha2-nistp256@openssh[.]com) [A-Za-z0-9+/]+=*( .*)?")
AUTHORIZED_KEYS_HEADER = "# Managed by mac-dev-machine-setup. The remote-login task replaces this file."
TOOL_HINTS = {
    "mosh-server": "mosh-server is not on the SSH PATH. Run the cli task to install mosh.",
    "herdr": "herdr is not on the SSH PATH. Install it from https://herdr.dev.",
}
SHIELDS_UP = ("Shields Up is unchanged. Before allowing incoming connections, complete the policy "
              'and firewall checks in "Remote access from an iPhone" in README.md.')


def run(action: str, config: dict, *, check: bool = False) -> None:
    """Run one security action; raise RuntimeError on failure."""
    if action not in ACTIONS:
        raise RuntimeError(f"Unknown security action {action!r}; expected one of {', '.join(ACTIONS)}.")
    try:
        _require_normal_user(config)
        _require_profile(config)
        if action == "ssh":
            _manage_ssh(config, check)
        elif action == "remote-login-check":
            _require_mac(config)
            _preflight(config)
            print("Prerequisites passed. No services, SSH configuration, or keys were changed. "
                  "This does not validate the effective SSH settings, firewall, or tailnet policy. "
                  'Read "Remote access from an iPhone" in README.md before enabling access.', flush=True)
        elif action == "remote-login":
            _enable_remote_login(config, check)
        else:
            _revoke_remote_login(config, check)
    except (OSError, shutil.Error, ValueError, TypeError) as error:
        # Paths below give specific recovery messages; this keeps any other failure a RuntimeError.
        raise RuntimeError(f"{action} failed: {error}") from error


# Guards shared by direct callers and full setup.

def _require_normal_user(config: dict) -> None:
    if os.geteuid() == 0 or config.get("user") == "root":
        raise RuntimeError("Run as your normal user, not root. Privileged steps use sudo per operation.")


def _require_profile(config: dict) -> None:
    if config.get("profile") not in ("personal", "work"):
        raise RuntimeError(f"Unsupported profile {config.get('profile')!r}; use personal or work.")


def _require_mac(config: dict) -> None:
    if config.get("platform") != "mac" or host_platform.system() != "Darwin":
        raise RuntimeError("Remote Login commands support macOS only.")


def _require_local_console(action: str) -> None:
    if any(os.environ.get(variable) for variable in SSH_SESSION_VARIABLES):
        raise RuntimeError(
            f"Run {action} from the Mac's local console, not SSH or mosh: this command stops the SSH "
            "listener and can interrupt your session. Do not unset SSH_CONNECTION, SSH_CLIENT or "
            "SSH_TTY to bypass this check. The read-only remote-login-check can run remotely.")


def _invoking_user(config: dict) -> str:
    user = pwd.getpwuid(os.getuid()).pw_name
    if config.get("user") != user:
        raise RuntimeError(f"Configured user {config.get('user')!r} is not the invoking account {user!r}.")
    return user


def _absolute(config: dict, key: str) -> Path:
    value = config.get(key)
    if not isinstance(value, str) or not os.path.isabs(value):
        raise RuntimeError(f"Configuration {key} must be an absolute path, not {value!r}.")
    return Path(value)


def _plain_filename(value: object, key: str) -> str:
    if (not isinstance(value, str) or not value or value in (".", "..") or "/" in value
            or any(character.isspace() or not character.isprintable() for character in value)):
        raise RuntimeError(f"{key} entries must be plain file names in .ssh/, not {value!r}.")
    return value


def _string_list(config: dict, key: str) -> list:
    value = config.get(key) or []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"Configuration {key} must be a list of strings.")
    return value


def _render(name: str, **values: str) -> str:
    return string.Template((TEMPLATES / name).read_text()).substitute(values)


# Private file helpers.

def _ensure_private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def _write_private(path: Path, data: bytes) -> None:
    """Atomically replace path with data, mode 0600."""
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _new_backup_dir(home: Path) -> Path:
    """Create a never-before-used ~/.dev-setup-backups/<timestamp> directory."""
    root = home / ".dev-setup-backups"
    root.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    for attempt in itertools.count():
        candidate = root / (stamp if attempt == 0 else f"{stamp}-{attempt}")
        try:
            candidate.mkdir(mode=0o700)
            return candidate
        except FileExistsError:
            continue
    raise AssertionError("unreachable")


def _skip_agent_and_special_files(directory: str, names: list) -> list:
    # Matches the former rsync -a --exclude=agent/: agent directories and sockets are not backed up.
    skipped = []
    for name in names:
        mode = os.lstat(os.path.join(directory, name)).st_mode
        if (name == "agent" and stat.S_ISDIR(mode)) or not (
                stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
            skipped.append(name)
    return skipped


# SSH client configuration (1Password agent).

def _identity_agent(config: dict) -> str:
    # A forwarded Linux agent is resolved per session; never save its temporary path.
    if config.get("platform") == "linux" and os.environ.get("SSH_AUTH_SOCK"):
        return "SSH_AUTH_SOCK"
    agent = config.get("ssh_agent_socket")
    if not isinstance(agent, str) or not agent or '"' in agent or not agent.isprintable():
        raise RuntimeError("Managed SSH requires an agent socket path in ssh_agent_socket.")
    return agent


def _manage_ssh(config: dict, check: bool) -> None:
    if not config.get("manage_ssh_config"):
        print("Managed SSH configuration not selected; existing SSH files and agents are unchanged.", flush=True)
        return
    if config.get("platform") not in ("mac", "linux"):
        raise RuntimeError(f"Unsupported platform {config.get('platform')!r}.")
    home = _absolute(config, "home")
    repo = _absolute(config, "repo_dir")
    agent = _identity_agent(config)
    personal = _plain_filename(config.get("personal_public_ssh_key"), "personal_public_ssh_key")
    work = _plain_filename(config.get("work_public_ssh_key"), "work_public_ssh_key")
    keys = {}
    for name in (personal, work):
        try:
            data = (repo / ".ssh" / name).read_bytes()
        except OSError as error:
            raise RuntimeError(f"Managed SSH requires the public key file .ssh/{name}: {error}") from error
        if not data.strip():
            raise RuntimeError(f"Managed SSH requires a public key in .ssh/{name}; the file is empty.")
        if b"PRIVATE KEY" in data:
            raise RuntimeError(f".ssh/{name} contains a private key. Keep only public keys in .ssh/.")
        keys[name] = data
    primary, alternate = (personal, work) if config["profile"] == "personal" else (work, personal)
    content = _render("ssh_config", identity_agent=agent, primary_public_key=primary,
                      alternate_public_key=alternate)
    ssh_dir = home / ".ssh"
    if check:
        print(f"Check mode: would back up {ssh_dir}, then write {ssh_dir / 'config'} using "
              f"IdentityAgent \"{agent}\" with {primary} as the GitHub key and copy {personal} and {work}. "
              "Nothing was changed.", flush=True)
        return
    backup = None
    if ssh_dir.exists():
        try:
            backup = _new_backup_dir(home) / "ssh"
            shutil.copytree(ssh_dir, backup, symlinks=True, ignore=_skip_agent_and_special_files)
        except (OSError, shutil.Error) as error:
            raise RuntimeError(f"Could not back up {ssh_dir}: {error}. No managed SSH file was changed.") from error
        print(f"Backed up {ssh_dir} to {backup}.", flush=True)
    try:
        _ensure_private_dir(ssh_dir)
        _write_private(ssh_dir / "config", content.encode())
        for name, data in keys.items():
            _write_private(ssh_dir / name, data)
    except OSError as error:
        saved = f"The previous files are in {backup}." if backup else f"{ssh_dir} did not exist before this run."
        raise RuntimeError(f"Managed SSH configuration may be incomplete: {error}. {saved}") from error
    print(f"Managed SSH uses the 1Password agent ({agent}) with {primary} for github.com and {alternate} "
          "for github-alt.com. Enable the 1Password SSH agent yourself; setup does not enable it or sign in.",
          flush=True)


# Remote Login.

@dataclass(frozen=True)
class _RemoteLogin:
    user: str
    home: Path
    allow_users: tuple
    path: str
    authorized_keys: str
    host: str
    addresses: tuple


def _mise_shims(home: Path) -> str:
    data = os.environ.get("MISE_DATA_DIR", "")
    if not os.path.isabs(data):
        xdg = os.environ.get("XDG_DATA_HOME", "")
        data = os.path.join(xdg if os.path.isabs(xdg) else str(home / ".local/share"), "mise")
    return os.path.join(data, "shims")


def _remote_login_path(config: dict, home: Path) -> str:
    # ~/.local/bin first (as in the interactive shell, for herdr), then mise-managed
    # tools, then the Homebrew prefix that still owns Brew packages such as mosh.
    # The prefix comes from configuration; the Brew CLI itself is not required.
    brew_prefix = config.get("brew_prefix") or "/opt/homebrew"
    entries = [str(home / ".local/bin"), _mise_shims(home), os.path.join(str(brew_prefix), "bin"),
               "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    for entry in entries:
        if not os.path.isabs(entry) or ":" in entry or any(c.isspace() or c in '"\'#' for c in entry):
            raise RuntimeError(f"The SSH command PATH entry {entry!r} must be an absolute path "
                               "without spaces, quotes, '#' or ':'.")
    return ":".join(dict.fromkeys(entries))


def _tool_hints(path: str) -> list:
    return [hint for tool, hint in TOOL_HINTS.items() if shutil.which(tool, path=path) is None]


def _preflight(config: dict) -> _RemoteLogin:
    """Read-only Remote Login prerequisites: no sudo, services, configuration or keys."""
    print("Checking prerequisites without sudo or changes to services, SSH configuration, or keys.", flush=True)
    user = _invoking_user(config)
    home = _absolute(config, "home")
    repo = _absolute(config, "repo_dir")
    key_files = _string_list(config, "remote_login_public_keys")
    sources = _string_list(config, "remote_login_sources")
    if not key_files or not sources:
        raise RuntimeError(
            "Run remote-login as your normal user. In your configuration, list at least one phone public "
            "key file from .ssh/ in remote_login_public_keys and at least one address range in "
            "remote_login_sources.")
    for source in sources:
        if not source or any(c.isspace() or c in '",#' or not c.isprintable() for c in source):
            raise RuntimeError(f"remote_login_sources entry {source!r} must be one address or range.")
    ssh_keygen = config.get("remote_login_ssh_keygen") or "/usr/bin/ssh-keygen"
    key_lines = []
    for name in key_files:
        path = repo / ".ssh" / _plain_filename(name, "remote_login_public_keys")
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError) as error:
            raise RuntimeError(f"Cannot read phone public key file .ssh/{name}: {error}") from error
        if "PRIVATE KEY" in text:
            raise RuntimeError(f"{name} contains a private key. Keep only public keys in .ssh/.")
        lines = text.strip().split("\n")
        if len(lines) != 1 or not PUBLIC_KEY_LINE.fullmatch(lines[0]):
            raise RuntimeError(f'{name} must hold exactly one line: a public key without options, '
                               'for example "ssh-ed25519 AAAA... iphone".')
        result = _execute([ssh_keygen, "-l", "-f", str(path)])
        if result.returncode != 0:
            raise _CommandError([ssh_keygen, "-l", "-f", str(path)], result)
        key_lines.append(lines[0].strip())
    tailscale = config.get("tailscale_cli") or "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    not_connected = (f"Tailscale is not installed at {tailscale} or is not connected. "
                     "Open Tailscale, sign in, connect, and run remote-login-check again.")
    try:
        status = _execute([tailscale, "status", "--json"])
        state = json.loads(status.stdout) if status.returncode == 0 else {}
    except (RuntimeError, ValueError) as error:
        raise RuntimeError(f"{not_connected} ({error})") from error
    if not isinstance(state, dict) or state.get("BackendState") != "Running":
        raise RuntimeError(not_connected)
    self_node = state.get("Self") if isinstance(state.get("Self"), dict) else {}
    addresses = tuple(str(address) for address in self_node.get("TailscaleIPs") or [])
    if not addresses:
        raise RuntimeError("Tailscale is running but reports no tailnet address for this Mac. "
                           "Reconnect Tailscale and run remote-login-check again.")
    path = _remote_login_path(config, home)
    print(f"Phone keys checked: {', '.join(key_files)}. Tailscale is connected ({', '.join(addresses)}).",
          flush=True)
    print(f"SSH commands will use PATH={path}", flush=True)
    for tool in TOOL_HINTS:
        found = shutil.which(tool, path=path)
        print(f"  {tool}: {found or 'not found'}", flush=True)
    return _RemoteLogin(
        user=user, home=home, allow_users=tuple(f"{user}@{source}" for source in sources), path=path,
        authorized_keys="\n".join([AUTHORIZED_KEYS_HEADER, *key_lines]) + "\n",
        host=str(self_node.get("DNSName") or "").rstrip("."), addresses=addresses)


def _enable_remote_login(config: dict, check: bool) -> None:
    if config.get("revoke_remote_login"):
        print("Remote Login revocation was requested; it takes precedence, so enablement is skipped.", flush=True)
        return
    if not config.get("manage_remote_login"):
        print("Remote Login not selected; existing Remote Login access is unchanged.", flush=True)
        return
    _require_mac(config)
    if not check:
        _require_local_console("remote-login")
    settings = _preflight(config)
    if check:
        print("Check mode does not stop Remote Login, replace its configuration, or run the effective server "
              "checks. No runtime security validation has been performed.", flush=True)
        return
    system = _System(config)
    content = _render("sshd_remote_login.conf", allow_users=" ".join(settings.allow_users),
                      remote_login_path=settings.path)
    print("Enabling Remote Login: the SSH listener will stop and all authorised keys will be replaced.", flush=True)
    print("Keep Shields Up on. Complete the README policy and local firewall checks before allowing inbound "
          "traffic.", flush=True)
    system.authorize()
    system.create_host_keys()
    try:
        system.stop()
    except RuntimeError as error:
        raise RuntimeError(f"Could not stop Remote Login: {error} "
                           "No SSH configuration or keys have been replaced.") from error
    system.deploy_config(content, settings)
    try:
        system.replace_authorized_keys(settings.home, settings.authorized_keys)
        system.restrict_access(settings.user)
    except (RuntimeError, OSError) as error:
        raise RuntimeError("Remote Login remains disabled: the checked configuration is installed, but "
                           f"authorised keys or the access list could not be updated: {error}") from error
    system.activate()
    lines = [f"Host: {settings.host} ({', '.join(settings.addresses)})", f"User: {settings.user}",
             "Compare these host key fingerprints when an app connects for the first time:"]
    lines += system.host_key_fingerprints() or ["The host keys do not exist yet."]
    lines += _tool_hints(settings.path)
    lines.append(SHIELDS_UP)
    print("\n".join(lines), flush=True)


def _revoke_remote_login(config: dict, check: bool) -> None:
    if not config.get("revoke_remote_login"):
        print("Remote Login revocation not requested; existing Remote Login access is unchanged.", flush=True)
        return
    _require_mac(config)
    if not check:
        _require_local_console("remote-login-revoke")
    user = _invoking_user(config)
    home = _absolute(config, "home")
    print("Revoking Remote Login: disabling SSH startup/listening and backing up then clearing "
          f"{user}'s authorised keys.", flush=True)
    print("Existing SSH and mosh sessions need separate action. Shields Up is unchanged.", flush=True)
    if check:
        print("Check mode only: Remote Login and authorised keys have not been changed.", flush=True)
        return
    system = _System(config)
    system.authorize()
    try:
        system.stop()
    except RuntimeError as error:
        raise RuntimeError(f"Could not stop Remote Login: {error} Authorised keys have not been changed.") from error
    try:
        system.replace_authorized_keys(home, "")
    except (RuntimeError, OSError) as error:
        raise RuntimeError("Remote Login startup and its listener are disabled, but this account's authorised "
                           f"keys could not be backed up and cleared: {error}") from error
    print("Remote Login startup and its listener are disabled. This account has no authorised SSH keys. "
          "Existing SSH and mosh sessions may remain active. End those sessions separately from the local "
          "console when responding to an incident. Tailscale settings have not been changed. "
          "The managed SSH server configuration is retained.", flush=True)


# Controlled command boundary.

class _CommandError(RuntimeError):
    def __init__(self, argv: list, result: subprocess.CompletedProcess):
        output = result.stderr if isinstance(result.stderr, str) else result.stderr.decode(errors="replace")
        if not output.strip():
            output = result.stdout if isinstance(result.stdout, str) else result.stdout.decode(errors="replace")
        output = output.strip()[-2000:]
        super().__init__(f"`{' '.join(argv)}` failed with exit status {result.returncode}"
                         + (f": {output}" if output else "."))


def _execute(argv: list, *, text: bool = True) -> subprocess.CompletedProcess:
    argv = [str(argument) for argument in argv]
    try:
        return subprocess.run(argv, capture_output=True, text=text, stdin=subprocess.DEVNULL)
    except OSError as error:
        raise RuntimeError(f"Could not run {argv[0]}: {error}") from error


def _config_list(config: dict, key: str, default: list) -> list:
    if key not in config:
        return list(default)
    value = config[key]
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise RuntimeError(f"Configuration {key} must be a list of command arguments.")
    return list(value)


def _attribute(output: str, key: str) -> list:
    """Values of one attribute in dscl -read output (single- or multi-line form)."""
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(key + ":"):
            values = line[len(key) + 1:].split()
            for continuation in lines[index + 1:]:
                if not continuation.startswith(" "):
                    break
                values += continuation.split()
            return values
    return []


class _System:
    """The only code that runs launchctl, sshd, the access list or privileged file writes."""

    def __init__(self, config: dict):
        default_sudo = ["sudo", "-A"] if os.environ.get("SUDO_ASKPASS") else ["sudo"]
        self.sudo = _config_list(config, "remote_login_sudo", default_sudo)
        self.launchctl = config.get("remote_login_launchctl") or "/bin/launchctl"
        self.sshd = _config_list(config, "remote_login_sshd", ["/usr/sbin/sshd"]) or ["/usr/sbin/sshd"]
        self.ssh_keygen = config.get("remote_login_ssh_keygen") or "/usr/bin/ssh-keygen"
        self.dscl = config.get("remote_login_dscl") or "/usr/bin/dscl"
        self.dseditgroup = config.get("remote_login_dseditgroup") or "/usr/sbin/dseditgroup"
        self.config_file = Path(config.get("remote_login_sshd_file") or "/etc/ssh/sshd_config.d/010-remote-login.conf")
        self.config_owner = str(config.get("remote_login_config_owner") or "root")
        self.config_group = str(config.get("remote_login_config_group") or "wheel")
        self.host_key = Path(config.get("remote_login_host_key") or "/etc/ssh/ssh_host_ed25519_key")
        try:
            self.port = int(config.get("remote_login_port") or 22)
            self.port_timeout = float(config.get("remote_login_port_timeout") or 15)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"remote_login_port and remote_login_port_timeout must be numbers: {error}") from error
        if not 0 < self.port < 65536 or not 0 < self.port_timeout <= 300:
            raise RuntimeError("remote_login_port must be 1-65535 and remote_login_port_timeout 0-300 seconds.")
        if not self.config_file.is_absolute() or not self.host_key.is_absolute():
            raise RuntimeError("remote_login_sshd_file and remote_login_host_key must be absolute paths.")

    def _run(self, argv: list, *, privileged: bool = False, check: bool = True,
             text: bool = True) -> subprocess.CompletedProcess:
        result = _execute((self.sudo if privileged else []) + [str(argument) for argument in argv], text=text)
        if check and result.returncode != 0:
            raise _CommandError([str(argument) for argument in argv], result)
        return result

    def _launchctl(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
        return self._run([self.launchctl, *arguments], privileged=True, check=check)

    def authorize(self) -> None:
        if not self.sudo:
            return
        try:
            result = subprocess.run(self.sudo + ["-v"])
        except OSError as error:
            raise RuntimeError(f"Could not run {self.sudo[0]}: {error}") from error
        if result.returncode != 0:
            raise RuntimeError("Sudo authorization failed. Nothing was changed.")

    def create_host_keys(self) -> None:
        if not self.host_key.exists():
            self._run([self.ssh_keygen, "-A"], privileged=True)

    def stop(self) -> None:
        """Disable startup, then unload the listener; confirm both."""
        if not SERVICE_DISABLED.search(self._launchctl("print-disabled", "system").stdout):
            self._launchctl("disable", SERVICE)
        loaded = self._launchctl("print", SERVICE, check=False)
        if loaded.returncode == 0:
            self._launchctl("bootout", SERVICE)
        elif loaded.returncode != SERVICE_NOT_LOADED:
            raise _CommandError([self.launchctl, "print", SERVICE], loaded)
        if not SERVICE_DISABLED.search(self._launchctl("print-disabled", "system").stdout):
            raise RuntimeError("Remote Login startup is still enabled.")
        confirmed = self._launchctl("print", SERVICE, check=False)
        if confirmed.returncode != SERVICE_NOT_LOADED:
            raise RuntimeError(f"The Remote Login listener is still loaded "
                               f"(launchctl print exit status {confirmed.returncode}).")

    def _install(self, source: Path, owner: str, group: str, mode: str) -> None:
        self._run(["/usr/bin/install", "-o", owner, "-g", group, "-m", mode, source, self.config_file],
                  privileged=True)

    def deploy_config(self, content: str, settings: _RemoteLogin) -> None:
        """Install and gate the managed file while stopped; restore the exact previous state on failure."""
        path = self.config_file
        try:
            previous = os.lstat(path)
        except FileNotFoundError:
            previous = None
        except OSError as error:
            raise RuntimeError(f"Cannot inspect {path}: {error}. Remote Login remains disabled.") from error
        if previous is not None and not stat.S_ISREG(previous.st_mode):
            raise RuntimeError(f"{path} must be absent or a regular file, not a symbolic link or other file "
                               "type. Remote Login remains disabled.")
        previous_bytes = None
        if previous is not None:
            try:
                previous_bytes = self._run(["/bin/cat", "--", path], privileged=True, text=False).stdout
            except RuntimeError as error:
                raise RuntimeError(f"Cannot save the previous {path}: {error}. Nothing was replaced; "
                                   "Remote Login remains disabled.") from error
        try:
            scratch_dir = tempfile.TemporaryDirectory(prefix="remote-login-")
        except OSError as error:
            raise RuntimeError(f"Cannot create a private temporary directory: {error}. Nothing was replaced; "
                               "Remote Login remains disabled.") from error
        with scratch_dir as scratch:
            candidate = Path(scratch) / "candidate.conf"
            installing = False
            try:
                candidate.write_text(content)
                self._run(self.sshd + ["-t", "-f", candidate], privileged=True)
                installing = True
                self._install(candidate, self.config_owner, self.config_group, "0644")
                self.check_effective(settings)
            except BaseException as failure:
                if not installing:
                    # The managed file was never touched, so leave its inode and metadata alone.
                    raise RuntimeError(
                        f"Remote Login remains disabled and {path} was not changed: the candidate configuration "
                        "was rejected before deployment. Fix the configuration and run remote-login again from "
                        f"the local console. Original failure: {failure}") from failure
                try:
                    if previous is None:
                        self._run(["/bin/rm", "-f", "--", path], privileged=True)
                    else:
                        snapshot = Path(scratch) / "previous.conf"
                        snapshot.write_bytes(previous_bytes)
                        self._install(snapshot, str(previous.st_uid), str(previous.st_gid),
                                      f"{stat.S_IMODE(previous.st_mode):04o}")
                except BaseException as rollback_failure:
                    raise RuntimeError(
                        f"Remote Login remains disabled. The configuration rollback failed: {rollback_failure}. "
                        f"Original deployment failure: {failure}") from failure
                raise RuntimeError(
                    "Remote Login remains disabled and the previous configuration has been restored (or the new "
                    "file removed). Fix the configuration and run remote-login again from the local console. "
                    f"Original failure: {failure}") from failure

    def check_effective(self, settings: _RemoteLogin) -> None:
        """Refuse unless sshd -T applies the managed limits and nothing else can add or block logins."""
        path = self.config_file
        required = ["passwordauthentication no", "kbdinteractiveauthentication no",
                    "authenticationmethods publickey", "pubkeyauthentication yes",
                    "authorizedkeysfile .ssh/authorized_keys", "authorizedkeyscommand none",
                    "trustedusercakeys none"]
        expected_allow = [f"allowusers {entry}" for entry in settings.allow_users]
        for address in GATE_ADDRESSES:
            result = self._run(self.sshd + ["-T", "-ddd", "-C",
                                            f"user={settings.user},host=remote-login-check,addr={address}"],
                               privileged=True)
            lines = result.stdout.splitlines()
            if (f"parse_server_config_depth: config {path} len " not in result.stderr
                    or re.findall(r"checking syntax for 'Match [^']*'", result.stderr)
                    != ["checking syntax for 'Match all'"]):
                raise RuntimeError(
                    f"The SSH server does not read {path}, or another file adds a Match block. Remote Login "
                    "needs its own Match block to be the only one. Fix the SSH server configuration, then run "
                    "remote-login again.")
            setenv = " ".join(line for line in lines if line.startswith("setenv ")).split(" ")
            if (any(line not in lines for line in required)
                    or [line for line in lines if line.startswith("allowusers ")] != expected_allow
                    or f"PATH={settings.path}" not in setenv):
                raise RuntimeError(
                    f"The SSH server would not apply the Remote Login limits to connections from {address}. "
                    "Another file in /etc/ssh overrides them. Fix that file, then run remote-login again.")
            if (any(re.match(r"(denyusers|denygroups|allowgroups) ", line) for line in lines)
                    or "refuseconnection no" not in lines or "forcecommand none" not in lines
                    or "chrootdirectory none" not in lines or "permittty yes" not in lines
                    or "maxsessions 0" in lines):
                raise RuntimeError(
                    "Another file in /etc/ssh sets DenyUsers, DenyGroups, AllowGroups, RefuseConnection, "
                    "ForceCommand, ChrootDirectory, PermitTTY no, or MaxSessions 0. These settings can stop your "
                    "account from opening a terminal session. Remove them, then run remote-login again.")

    @staticmethod
    def replace_authorized_keys(home: Path, content: str) -> None:
        """Back up a differing nonempty authorized_keys outside ~/.ssh, then replace it whole."""
        ssh_dir = home / ".ssh"
        _ensure_private_dir(ssh_dir)
        target = ssh_dir / "authorized_keys"
        try:
            current = os.lstat(target)
        except FileNotFoundError:
            current = None
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise RuntimeError("The authorised keys path must be absent or a regular file, not a symbolic link.")
        desired = content.encode()
        if current is not None and current.st_size > 0:
            existing = target.read_bytes()
            digest = hashlib.sha1(existing).hexdigest()
            if digest != hashlib.sha1(desired).hexdigest():
                backup = _new_backup_dir(home) / f"remote-login-{digest}"
                backup.mkdir(mode=0o700)
                _write_private(backup / "authorized_keys", existing)
                print(f"Backed up the previous authorised keys to {backup / 'authorized_keys'}.", flush=True)
        _write_private(target, desired)

    def _access_list(self) -> tuple:
        result = self._run([self.dscl, ".", "-read", f"/Groups/{ACCESS_GROUP}", "GroupMembership",
                            "NestedGroups"], check=False)
        return (result.returncode, _attribute(result.stdout, "GroupMembership"),
                _attribute(result.stdout, "NestedGroups"))

    def restrict_access(self, user: str) -> None:
        """Make the invoking account the only Remote Login access-list member."""
        status, members, nested = self._access_list()
        if status == 0 and members == [user] and not nested:
            return
        group = f"/Groups/{ACCESS_GROUP}"
        if self._run([self.dscl, ".", "-read", group], check=False).returncode != 0:
            self._run([self.dseditgroup, "-o", "create", "-q", "-r", "SSH Service ACL", "-c", "SSH Service ACL",
                       ACCESS_GROUP], privileged=True)
        self._run([self.dseditgroup, "-o", "edit", "-a", user, "-t", "user", ACCESS_GROUP], privileged=True)
        _, members, nested = self._access_list()
        for member in members:
            if member != user:
                self._run([self.dseditgroup, "-o", "edit", "-q", "-d", member, "-t", "user", ACCESS_GROUP],
                          privileged=True)
        for guid in nested:
            found = self._run([self.dscl, ".", "-search", "/Groups", "GeneratedUID", guid], check=False)
            name = found.stdout.split()[0] if found.returncode == 0 and found.stdout.split() else ""
            if name:
                self._run([self.dseditgroup, "-o", "edit", "-q", "-d", name, "-t", "group", ACCESS_GROUP],
                          privileged=True)
            else:
                self._run([self.dscl, ".", "-delete", group, "NestedGroups", guid], privileged=True)
        status, members, nested = self._access_list()
        if status != 0 or members != [user] or nested:
            raise RuntimeError(f"The Remote Login access list could not be limited to {user} "
                               f"(members {members}, nested groups {nested}). Remote Login remains disabled.")

    def _wait_for_port(self) -> None:
        deadline = time.monotonic() + self.port_timeout
        while True:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                    return
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Nothing accepted connections on 127.0.0.1:{self.port} within "
                                       f"{self.port_timeout:g} seconds: {error}") from error
            time.sleep(0.2)

    def activate(self) -> None:
        """Start Remote Login; on any failure disable it again and report the original failure."""
        try:
            self._launchctl("enable", SERVICE)
            self._launchctl("bootstrap", "system", SERVICE_PLIST)
            self._wait_for_port()
        except BaseException as failure:
            try:
                self.stop()
            except BaseException as stop_failure:
                raise RuntimeError(
                    f"Remote Login activation failed and its shutdown could not be confirmed: {stop_failure}. "
                    "Use the local console to disable Remote Login before fixing the error. "
                    f"Original activation failure: {failure}") from failure
            raise RuntimeError(
                "Remote Login activation failed and it has been disabled again. Fix the error and run "
                "remote-login again from the local console; do not bypass the checks by enabling it manually. "
                f"Original failure: {failure}") from failure

    def host_key_fingerprints(self) -> list:
        return [self._run([self.ssh_keygen, "-l", "-f", key]).stdout.strip()
                for key in sorted(self.host_key.parent.glob("ssh_host_*_key.pub"))]
