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
SOFTWARE = ("packages", "gui", "app-store", "node")
HOST = ("git", "zsh", "osx", "dock", "dotfiles")
SECURITY = ("ssh", "remote-login-check", "remote-login", "remote-login-revoke")
# Actions that check git, curl, and disk space first, as the old setup playbook did.
PREFLIGHT = ("install", "cli", "gui", "app-store", "osx", "dock", "dotfiles", "git", "zsh", "node", "ssh")
ACTIONS = {
    "install": "Configure everything for the profile (no bootstrap or prompts)",
    "bootstrap": "Post-mise first-run steps used by install.sh",
    "packages": "Preview the selected package inventories without changes",
    "cli": "Install native CLI tools, every mise tool and fzf integration",
    "gui": "Install or upgrade Mac desktop apps",
    "app-store": "Install Mac App Store apps",
    "osx": "Apply macOS preferences",
    "dock": "Lay out the macOS Dock",
    "dotfiles": "Install or refresh the external dotfiles",
    "git": "Install Git and apply global Git settings",
    "zsh": "Set the login shell and install oh-my-zsh",
    "node": "Add the Ubuntu PNPM_HOME shell block",
    "ssh": "Back up and configure SSH for the 1Password agent",
    "remote-login-check": "Check Remote Login prerequisites without changes",
    "remote-login": "Enable key-only tailnet Remote Login on this Mac",
    "remote-login-revoke": "Disable Remote Login and clear this account's keys",
}


class _Modules:
    """Import devsetup.<name> on first use so one missing module affects only its actions."""

    def __getattr__(self, name: str):
        return importlib.import_module(f"devsetup.{name}")


def dispatch(action: str, config: dict, modules, *, check: bool = False) -> list[str]:
    """Run one action. ``modules`` provides host, software, and security objects.

    Return the non-fatal problems from all steps. They are also listed at the
    end of the output, including when a later step stops with an error.
    """
    issues: list[str] = []

    def step(module: str, name: str) -> None:
        issues.extend(getattr(modules, module).run(name, config, check=check) or [])

    if action in MAC_ONLY and config["platform"] != "mac":
        print(f"{action}: skipped; it applies to macOS only.")
        return issues
    try:
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
    finally:
        if issues:
            print("\nThese items need attention:", flush=True)
            for issue in issues:
                print(f"  - {issue}", flush=True)
    return issues


def _install(config: dict, step) -> None:
    """Filter the fixed setup order; exclusions never suppress explicit revocation."""
    def enabled(name: str) -> bool:
        if config["platform"] != "mac" and name in (*MAC_ONLY, "remote-login"):
            print(f"{name}: not applicable on this platform.")
            return False
        if not config["steps"][name]:
            print(f"{name}: skipped by configuration.")
            return False
        return True

    if enabled("ssh"):
        step("security", "ssh")
    if enabled("git"):
        step("host", "git")
    if enabled("cli"):
        step("software", "cli")
        step("host", "fzf")
    if config["platform"] == "mac" and config["revoke_remote_login"]:
        step("security", "remote-login-revoke")
    elif enabled("remote-login"):
        step("security", "remote-login")
    if enabled("gui"):
        step("software", "gui")
    if enabled("zsh"):
        step("host", "zsh")
    if enabled("app-store"):
        step("software", "app-store")
    if enabled("osx"):
        step("host", "osx")
    if enabled("node"):
        step("software", "node")
    if enabled("dotfiles"):
        step("host", "dotfiles")
    if enabled("dock"):
        step("host", "dock")


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common.add_argument("--profile", choices=config_module.PROFILES,
                        help="personal or work (default personal; also DEVSETUP_PROFILE)")
    common.add_argument("--config", type=Path, default=None, metavar="PATH",
                        help="explicit local TOML settings file")
    common.add_argument("--mise", help="absolute path of the mise executable (default: mise on PATH)")
    common.add_argument("--skip", action="append", choices=config_module.STEPS, default=[],
                        metavar="STEP", help="exclude a named component for this aggregate run; repeatable")
    choices = (
        ("ssh", "--1password-ssh", "--keep-ssh"),
        ("dotfiles", "--dotfiles", "--skip-dotfiles"),
        ("remote-login", "--remote-login", "--keep-remote-login"),
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
    parser = argparse.ArgumentParser(prog="setup.py", description="Configure this Mac or Ubuntu machine.",
                                     allow_abbrev=False)
    actions = parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    for name, summary in ACTIONS.items():
        actions.add_parser(name, parents=[common], help=summary, description=summary, allow_abbrev=False)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse options; ``.flags`` holds the per-run flags this command sets."""
    parser = _parser()
    args = parser.parse_args(argv)
    args.flags = {dest: getattr(args, dest) for dest in ("ssh", "dotfiles", "remote-login", "revoke_remote_login")
                  if getattr(args, dest) is not None}
    if args.skip and args.action not in ("install", "bootstrap"):
        parser.error("--skip is only valid for aggregate setup and bootstrap hand-off.")
    for name in args.skip:
        if args.flags.get(name) is True:
            parser.error(f"--skip {name} conflicts with an explicit request to enable that component.")
        args.flags[name] = False
    if args.flags.get("revoke_remote_login") and args.action not in (
            "install", "remote-login", "remote-login-revoke"):
        parser.error("Revocation requires install, remote-login or remote-login-revoke.")
    if args.action in config_module.STEPS and args.flags.get(args.action) is False:
        parser.error(f"{args.action} cannot be combined with an option that turns it off.")
    # mise tasks run from the repository; resolve --config from where the user ran them.
    if args.config is not None:
        args.config = Path(os.environ.get("MISE_ORIGINAL_CWD", ".")) / args.config
    if args.action == "remote-login-revoke":
        args.flags["revoke_remote_login"] = True
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = config_module.load(repo_dir=REPO_DIR, profile=args.profile, override=args.config,
                                    flags=args.flags, mise=args.mise)
        if args.action in config_module.STEPS:
            if not config["steps"][args.action]:
                print(f"{args.action}: explicit command overrides the configured exclusion.")
            config["steps"][args.action] = True
        prefix = config["brew_prefix"]
        os.environ["PATH"] = os.pathsep.join([f"{prefix}/bin", f"{prefix}/sbin", os.environ.get("PATH", "")])
        mode = " (check mode: no changes)" if args.check else ""
        print(f"{args.action}: {config['platform']} / {config['profile']}{mode}")
        issues = dispatch(args.action, config, _Modules(), check=args.check)
        if issues:
            count = "1 item needs" if len(issues) == 1 else f"{len(issues)} items need"
            raise RuntimeError(f"{args.action} finished, but {count} attention. See the list above.")
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
