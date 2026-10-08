#!/usr/bin/env python3
"""Check provisioning without installing tools or changing machine settings."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tomllib


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    failures: list[str] = []
    bats = shutil.which("bats")
    if bats is None:
        print("Shell checks require bats-core. Install it with: brew install bats-core", file=sys.stderr)
        return 1
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "DEVSETUP_TEST_PYTHON": sys.executable}
    manifests = sorted(root.glob("*.toml")) + sorted((root / "mise").rglob("*.toml"))
    for path in manifests:
        try:
            with path.open("rb") as source:
                tomllib.load(source)
        except (OSError, tomllib.TOMLDecodeError) as error:
            failures.append(f"{path.relative_to(root)}: {error}")

    scripts = sorted(root.glob("*.sh")) + sorted((root / "scripts").rglob("*.sh"))
    commands = [(str(path.relative_to(root)), ["/bin/bash", "-n", str(path)]) for path in scripts]
    commands.append(("shell behaviours", [bats, str(root / "tests/shell")]))
    commands.extend(
        (name, [sys.executable, "-B", str(root / "scripts" / name)])
        for name in ("check-platforms.py", "check-software.py", "check-security.py")
    )
    for name, command in commands:
        print(f"\nChecking {name}", flush=True)
        try:
            result = subprocess.run(command, cwd=root, env=env, check=False)
            if result.returncode:
                failures.append(f"{name}: exit {result.returncode}")
        except OSError as error:
            failures.append(f"{name}: {error}")

    if failures:
        print("\nValidation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("\nAll provisioning checks passed. No packages or machine settings were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
