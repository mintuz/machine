"""The Remote Login command line: python scripts/devsetup/cli.py ACTION [options].

``run(action, config, *, check=False)`` in security.py is the module
interface. With ``--check`` the action reports instead of changing; it is a
limited preview, not a full simulation.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is required. Run ./install.sh --bootstrap-only, then use `mise run <task>`.")

import argparse  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402

# Run as a file, the package lives next to this module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devsetup import config as config_module  # noqa: E402
from devsetup import security  # noqa: E402

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
    common.add_argument("--revoke-remote-login", action="store_true",
                        help="revoke Remote Login instead of enabling it")
    common.add_argument("--check", action="store_true",
                        help="report supported changes without making them; a limited preview, "
                             "not a full simulation of every step")
    parser = argparse.ArgumentParser(prog="cli.py", description="Manage Remote Login on this Mac.",
                                     allow_abbrev=False)
    actions = parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    for name, summary in ACTIONS.items():
        actions.add_parser(name, parents=[common], help=summary, description=summary, allow_abbrev=False)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.revoke_remote_login and args.action == "remote-login-check":
        parser.error("Revocation requires remote-login or remote-login-revoke.")
    if args.action == "remote-login-revoke":
        args.revoke_remote_login = True
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = config_module.load(repo_dir=REPO_DIR, profile=args.profile, revoke=args.revoke_remote_login)
        mode = " (check mode: no changes)" if args.check else ""
        print(f"{args.action}: {config['platform']} / {config['profile']}{mode}")
        security.run(args.action, config, check=args.check)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
