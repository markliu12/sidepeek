#!/usr/bin/env python3
"""Launcher so the project can be started with ``python run.py`` from the repo
root without installing anything. Use ``pythonw run.py`` for a console-less run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sidepeek.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
