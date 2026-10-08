"""Command-line entry point: load the config once, then route each action to security.py.

``run(action, config, *, check=False)`` is the module interface. With
``--check`` the action reports instead of changing; it is a limited preview,
not a full simulation.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from devsetup import config as config_module
from devsetup import security

REPO_DIR = Path(__file__).resolve().parents[2]
ACTIONS = {
    "remote-login-check": "Check Remote Login prerequisites without changes",
    "remote-login": "Enable key-only tailnet Remote Login on this Mac",
    "remote-login-revoke": "Disable Remote Login and clear this account's keys",
}


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common.add_argument("--profile", choices=config_module.PROFILES,
                        help="personal or work (default personal; also DEVSETUP_PROFILE)")
    common.add_argument("--config", type=Path, default=None, metavar="PATH",
                        help="explicit local TOML settings file")
    common.add_argument("--mise", help="absolute path of the mise executable (default: mise on PATH)")
    group = common.add_mutually_exclusive_group()
    group.add_argument("--remote-login", dest="remote-login", action="store_const", const=True)
    group.add_argument("--keep-remote-login", dest="remote-login", action="store_const", const=False)
    common.add_argument("--revoke-remote-login", dest="revoke_remote_login", action="store_const",
                        const=True, help="revoke Remote Login; wins over --remote-login")
    common.add_argument("--check", action="store_true",
                        help="report supported changes without making them; a limited preview, "
                             "not a full simulation of every step")
    parser = argparse.ArgumentParser(prog="setup.py", description="Manage Remote Login on this Mac.",
                                     allow_abbrev=False)
    actions = parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    for name, summary in ACTIONS.items():
        actions.add_parser(name, parents=[common], help=summary, description=summary, allow_abbrev=False)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse options; ``.flags`` holds the per-run flags this command sets."""
    parser = _parser()
    args = parser.parse_args(argv)
    args.flags = {dest: getattr(args, dest) for dest in ("remote-login", "revoke_remote_login")
                  if getattr(args, dest) is not None}
    if args.flags.get("revoke_remote_login") and args.action == "remote-login-check":
        parser.error("Revocation requires remote-login or remote-login-revoke.")
    if args.action == "remote-login" and args.flags.get("remote-login") is False:
        parser.error("remote-login cannot be combined with an option that turns it off.")
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
        if args.action == "remote-login":
            if not config["steps"]["remote-login"]:
                print("remote-login: explicit command overrides the configured exclusion.")
            config["steps"]["remote-login"] = True
        prefix = config["brew_prefix"]
        os.environ["PATH"] = os.pathsep.join([f"{prefix}/bin", f"{prefix}/sbin", os.environ.get("PATH", "")])
        mode = " (check mode: no changes)" if args.check else ""
        print(f"{args.action}: {config['platform']} / {config['profile']}{mode}")
        security.run(args.action, config, check=args.check)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
