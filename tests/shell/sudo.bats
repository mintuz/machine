#!/usr/bin/env bats

load helpers

setup() {
  setup_sandbox
  export SUDO_KEEPALIVE_INTERVAL=0.05
  stub_command child <<'SH'
#!/bin/sh
touch "$TEST_ROOT/child-ran"
exit 23
SH
}

# A redirected stdin is not sufficient: /dev/tty can still be available to Bats.
run_headless() {
  "$TEST_PYTHON" - "$@" <<'PY'
import subprocess
import sys

result = subprocess.run(sys.argv[1:], start_new_session=True, timeout=10)
sys.exit(result.returncode)
PY
}

@test "no command fails usage without authorising sudo" {
  run run_headless bash "$TEST_REPO/scripts/with-sudo-askpass.sh"
  [ "$status" -eq 64 ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/child-ran" ]
}

@test "public check runs without requesting sudo or creating backups" {
  run run_headless bash "$TEST_REPO/scripts/with-sudo-askpass.sh" \
    "$TEST_PYTHON" "$TEST_REPO/scripts/setup.py" cli --check --mise /opt/fake/bin/mise
  [ "$status" -eq 0 ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$HOME/.dev-setup-backups" ]
}

@test "check bypass preserves the command failure" {
  run run_headless bash "$TEST_REPO/scripts/with-sudo-askpass.sh" child --check
  [ "$status" -eq 23 ]
  [ -e "$TEST_ROOT/child-ran" ]
  [ ! -e "$TEST_ROOT/sudo-attempted" ]
}

@test "headless unavailable authorisation refuses to execute the child" {
  run run_headless bash "$TEST_REPO/scripts/with-sudo-askpass.sh" child
  [ "$status" -eq 1 ]
  [ -e "$TEST_ROOT/sudo-attempted" ]
  [ ! -e "$TEST_ROOT/child-ran" ]
  [ -z "$(find "$TMPDIR" -mindepth 1 -print)" ]
}

@test "existing authorisation executes the child and preserves its failure" {
  stub_command sudo <<'SH'
#!/bin/sh
exit 0
SH
  run run_headless bash "$TEST_REPO/scripts/with-sudo-askpass.sh" child
  [ "$status" -eq 23 ]
  [ -e "$TEST_ROOT/child-ran" ]
  [ -z "$(find "$TMPDIR" -mindepth 1 -print)" ]
}

@test "NOPASSWD executes the child even when credential validation is denied" {
  stub_command sudo <<'SH'
#!/bin/sh
# Model verifypw denying validation while the harmless command is permitted.
for argument do
  case "$argument" in
    -v) exit 1 ;;
    true) exit 0 ;;
  esac
done
exit 1
SH
  run run_headless bash "$TEST_REPO/scripts/with-sudo-askpass.sh" child
  [ "$status" -eq 23 ]
  [ -e "$TEST_ROOT/child-ran" ]
  [ -z "$(find "$TMPDIR" -mindepth 1 -print)" ]
}

@test "rejected interactive credentials are private and removed without running the child" {
  stub_command sudo <<'SH'
#!/bin/sh
[ -n "${SUDO_ASKPASS:-}" ] || exit 1
"$TEST_PYTHON" - <<'PY'
import os
from pathlib import Path
import stat
import subprocess

askpass = Path(os.environ["SUDO_ASKPASS"])
secret_dir = askpass.parent
assert secret_dir.is_relative_to(Path(os.environ["TMPDIR"]))
assert stat.S_IMODE(secret_dir.stat().st_mode) & 0o077 == 0
for path in secret_dir.rglob("*"):
    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
assert subprocess.check_output([str(askpass)]) == b"sandbox-password\n"
Path(os.environ["TEST_ROOT"], "private-credentials-observed").touch()
PY
[ "$?" -eq 0 ] || exit 98
exit 42
SH

  run "$TEST_PYTHON" - "$TEST_REPO/scripts/with-sudo-askpass.sh" <<'PY'
import errno
import os
import pty
import select
import signal
import sys
import time

pid, terminal = pty.fork()
if pid == 0:
    os.execvp("bash", ["bash", sys.argv[1], "child"])

# Supply only a dummy password, after the terminal becomes readable; no prompt
# wording is part of the contract. Bound the session and clean up on failure.
deadline = time.monotonic() + 10
sent = False
try:
    while time.monotonic() < deadline:
        ready, _, _ = select.select([terminal], [], [], 0.05)
        if ready:
            try:
                data = os.read(terminal, 4096)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                data = b""
            if data and not sent:
                os.write(terminal, b"sandbox-password\n")
                sent = True
        finished, status = os.waitpid(pid, os.WNOHANG)
        if finished:
            sys.exit(os.waitstatus_to_exitcode(status))
    raise TimeoutError("interactive sudo session did not terminate")
finally:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    os.close(terminal)
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
PY
  [ "$status" -eq 42 ]
  [ -e "$TEST_ROOT/private-credentials-observed" ]
  [ ! -e "$TEST_ROOT/child-ran" ]
  [ -z "$(find "$TMPDIR" -mindepth 1 -print)" ]
}
