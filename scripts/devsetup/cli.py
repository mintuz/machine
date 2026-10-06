"""Command-line entry point: load the config once, then route each action to its module.

Modules are imported only when an action needs them and share one interface:
``run(action, config, *, check=False)``. With ``--check`` every step is asked
to report instead of change; it is a limited preview, not a full simulation.
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


def dispatch(action: str, config: dict, modules, *, check: bool = False) -> None:
    """Run one action. ``modules`` provides host, software, and security objects."""
    def step(module: str, name: str) -> None:
        getattr(modules, module).run(name, config, check=check)

    if action in MAC_ONLY and config["platform"] != "mac":
        print(f"{action}: skipped; it applies to macOS only.")
        return
    if action in PREFLIGHT:
        step("host", "preflight")
    if action == "install":
        _install(config, step)
    elif action == "bootstrap":
        step("host", "bootstrap")
    elif action == "cli":
        step("software", "cli")
        step("host", "fzf")
    elif action in SOFTWARE:
        step("software", action)
    elif action in HOST:
        step("host", action)
    elif action in SECURITY:
        step("security", action)
    else:
        raise ValueError(f"Unknown action {action!r}")


def _install(config: dict, step) -> None:
    """Full configuration in the order of the old setup playbook."""
    mac = config["platform"] == "mac"
    if config["manage_ssh_config"]:
        step("security", "ssh")
    step("host", "git")
    step("software", "cli")
    step("host", "fzf")
    if mac and config["revoke_remote_login"]:
        step("security", "remote-login-revoke")
    elif mac and config["manage_remote_login"]:
        step("security", "remote-login")
    if mac:
        step("software", "gui")
    step("host", "zsh")
    if mac:
        step("software", "app-store")
        step("host", "osx")
    step("software", "node")
    if config["install_dotfiles"]:
        step("host", "dotfiles")
    if mac:
        step("host", "dock")


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
    common.add_argument("--check", action="store_true",
                        help="report supported changes without making them; a limited preview, "
                             "not a full simulation of every step")
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
        mode = " (check mode: no changes)" if args.check else ""
        print(f"{args.action}: {config['platform']} / {config['profile']}{mode}")
        dispatch(args.action, config, _Modules(), check=args.check)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
