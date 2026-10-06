"""Command-line entry point: load the config once, then route each action to its module.

Modules are imported only when an action needs them and share one interface:
``run(action, config)``. Software and security also accept ``check=``.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

from devsetup import config as config_module

REPO_DIR = Path(__file__).resolve().parents[2]
MAC_ONLY = ("gui", "app-store", "osx", "dock")
SOFTWARE = ("packages", "gui", "app-store", "node", "update")
HOST = ("git", "zsh", "osx", "dock", "dotfiles")
SECURITY = ("ssh", "remote-login-check", "remote-login", "remote-login-revoke")
# Actions that check git, curl, and disk space first, as the old setup playbook did.
PREFLIGHT = ("install", "cli", "gui", "app-store", "osx", "dock", "dotfiles", "git", "zsh", "node", "ssh")
# A direct component command is its own opt-in for that component.
FORCED_FLAGS = {
    "ssh": "manage_ssh_config",
    "dotfiles": "install_dotfiles",
    "remote-login": "manage_remote_login",
    "remote-login-revoke": "revoke_remote_login",
}
ACTIONS = {
    "install": "Configure everything for the profile (no bootstrap or prompts)",
    "bootstrap": "Post-mise first-run steps used by install.sh",
    "packages": "Preview the selected package inventories without changes",
    "cli": "Install CLI packages and fzf shell integration",
    "gui": "Install or upgrade Mac desktop apps",
    "app-store": "Install Mac App Store apps",
    "osx": "Apply macOS preferences",
    "dock": "Lay out the macOS Dock",
    "dotfiles": "Install or refresh the external dotfiles",
    "git": "Install Git and apply global Git settings",
    "zsh": "Set the login shell and install oh-my-zsh",
    "node": "Install Node.js and global pnpm packages",
    "update": "Update installed tools, apps, and models",
    "ssh": "Back up and configure SSH for the 1Password agent",
    "remote-login-check": "Check Remote Login prerequisites without changes",
    "remote-login": "Enable key-only tailnet Remote Login on this Mac",
    "remote-login-revoke": "Disable Remote Login and clear this account's keys",
}


class _Modules:
    """Import devsetup.<name> on first use so one missing module affects only its actions."""

    def __getattr__(self, name: str):
        return importlib.import_module(f"devsetup.{name}")


def dispatch(action: str, config: dict, modules) -> None:
    """Run one action. ``modules`` provides host, software, and security objects."""
    host, mac = modules.host, config["platform"] == "mac"
    if action in MAC_ONLY and not mac:
        print(f"{action}: skipped; it applies to macOS only.")
        return
    if action in PREFLIGHT:
        host.run("preflight", config)
    if action == "install":
        _install(config, modules)
    elif action == "bootstrap":
        host.run("bootstrap", config)
    elif action == "cli":
        modules.software.run("cli", config)
        host.run("fzf", config)
    elif action in SOFTWARE:
        modules.software.run(action, config)
    elif action in HOST:
        host.run(action, config)
    elif action in SECURITY:
        modules.security.run(action, config)
    else:
        raise ValueError(f"Unknown action {action!r}")


def _install(config: dict, modules) -> None:
    """Full configuration in the order of the old setup playbook."""
    host, software, security = modules.host, modules.software, modules.security
    mac = config["platform"] == "mac"
    if config["manage_ssh_config"]:
        security.run("ssh", config)
    host.run("git", config)
    software.run("cli", config)
    host.run("fzf", config)
    if mac and config["revoke_remote_login"]:
        security.run("remote-login-revoke", config)
    elif mac and config["manage_remote_login"]:
        security.run("remote-login", config)
    if mac:
        software.run("gui", config)
    host.run("zsh", config)
    if mac:
        software.run("app-store", config)
        host.run("osx", config)
    software.run("node", config)
    if config["install_dotfiles"]:
        host.run("dotfiles", config)
    if mac:
        host.run("dock", config)


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", choices=config_module.PROFILES,
                        help="personal or work (default personal; also DEVSETUP_PROFILE)")
    common.add_argument("--config", dest="overrides", action="append", type=Path, default=[],
                        metavar="PATH", help="explicit local TOML settings; repeat to layer")
    common.add_argument("--mise", help="absolute path of the mise executable (default: mise on PATH)")
    choices = (
        ("manage_ssh_config", "--1password-ssh", "--keep-ssh"),
        ("install_dotfiles", "--dotfiles", "--skip-dotfiles"),
        ("manage_remote_login", "--remote-login", "--keep-remote-login"),
    )
    for dest, on, off in choices:
        group = common.add_mutually_exclusive_group()
        group.add_argument(on, dest=dest, action="store_const", const=True)
        group.add_argument(off, dest=dest, action="store_const", const=False)
    common.add_argument("--revoke-remote-login", dest="revoke_remote_login", action="store_const",
                        const=True, help="revoke Remote Login; wins over --remote-login")
    parser = argparse.ArgumentParser(prog="setup.py", description="Configure this Mac or Ubuntu machine.")
    actions = parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    for name, summary in ACTIONS.items():
        actions.add_parser(name, parents=[common], help=summary, description=summary)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse options; ``.flags`` holds the per-run flags this command sets."""
    parser = _parser()
    args = parser.parse_args(argv)
    args.flags = {dest: getattr(args, dest) for dest in config_module.PER_RUN_FLAGS
                  if getattr(args, dest) is not None}
    # mise tasks run from the repository; resolve --config from where the user ran them.
    origin = Path(os.environ.get("MISE_ORIGINAL_CWD", "."))
    args.overrides = [origin / path for path in args.overrides]
    forced = FORCED_FLAGS.get(args.action)
    if forced:
        if args.flags.get(forced) is False:
            parser.error(f"{args.action} cannot be combined with an option that turns it off.")
        args.flags[forced] = True
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = config_module.load(repo_dir=REPO_DIR, profile=args.profile, overrides=args.overrides,
                                    flags=args.flags, mise=args.mise)
        prefix = config["brew_prefix"]
        os.environ["PATH"] = os.pathsep.join([f"{prefix}/bin", f"{prefix}/sbin", os.environ.get("PATH", "")])
        print(f"{args.action}: {config['platform']} / {config['profile']}")
        dispatch(args.action, config, _Modules())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
