"""Log file and crash handler.

The packaged build runs with ``console=False``, so every ``print`` went to a
stream nobody can see. When a user reports "it does not work" there was
nothing at all to look at. This module mirrors the console output into

    %LOCALAPPDATA%\\SidePeek\\sidepeek.log

capped at 512 KB with a single rollover, and routes unhandled exceptions into
the same file plus a message box - a windowed crash is otherwise completely
silent.

Logging never raises: a read-only or missing profile directory must not be
able to take the program down.
"""

from __future__ import annotations

import os
import sys
import time
import traceback

MAX_BYTES = 512 * 1024
LOG_NAME = "sidepeek.log"
PREFIX = "[sidepeek] "


def log_dir() -> str:
    """Directory that holds the log, overridable for diagnostics and tests."""
    override = os.environ.get("SIDEPEEK_LOG_DIR")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "SidePeek")


def log_path() -> str:
    return os.path.join(log_dir(), LOG_NAME)


def _rotate(path: str) -> None:
    """Keep one previous generation once the file grows past the cap."""
    try:
        if os.path.getsize(path) <= MAX_BYTES:
            return
        backup = path + ".1"
        if os.path.exists(backup):
            os.remove(backup)
        os.replace(path, backup)
    except OSError:
        pass


def log(message: str) -> None:
    """Write one timestamped line to the console (if any) and to the log."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {PREFIX}{message}"
    try:
        print(line, flush=True)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _rotate(path)
        with open(path, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(line + "\n")
    except (OSError, ValueError):
        pass


def install_excepthook() -> None:
    """Log an unhandled exception and tell the user, instead of vanishing."""

    def _hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log("unhandled exception:\n" + text.rstrip())
        try:
            from . import win32

            win32.user32.MessageBoxW(
                0,
                text[-1200:],
                "SidePeek 遇到错误，详情已写入\n" + log_path(),
                0x00000010,                      # MB_ICONERROR
            )
        except Exception:                        # noqa: BLE001 - never recurse
            pass

    sys.excepthook = _hook
