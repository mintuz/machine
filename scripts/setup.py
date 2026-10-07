#!/usr/bin/env python3
"""Direct entry point for every setup action: python scripts/setup.py ACTION [options]."""
import os
import sys

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is required. Run ./install.sh --bootstrap-only, "
             "then use `mise run <task>` or `mise exec -- python scripts/setup.py`.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devsetup.cli import main  # noqa: E402

sys.exit(main())
