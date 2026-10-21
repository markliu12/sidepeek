"""Test suite for SidePeek (stdlib unittest, no third-party runner).

Every run gets a throwaway log directory: the suite must never append to the
log file of the machine that executes it.
"""

import atexit
import os
import shutil
import tempfile

LOG_DIR = tempfile.mkdtemp(prefix="sidepeek-tests-")
atexit.register(shutil.rmtree, LOG_DIR, True)
os.environ["SIDEPEEK_LOG_DIR"] = LOG_DIR
