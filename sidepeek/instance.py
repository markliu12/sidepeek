"""Single-instance guard.

Two copies of SidePeek are actively harmful: they compete for the same global
hotkeys (the loser registers nothing, silently) and leave two notification
area icons behind. The second copy therefore exits, after poking the first one
so the user gets an explanation instead of a window that simply does not open.

The lock is a named mutex in the ``Local`` namespace, which is scoped to the
logon session - two users on the same machine each get their own instance, and
so does each separate RDP session.
"""

from __future__ import annotations

import ctypes

from . import win32

MUTEX_NAME = "Local\\SidePeek.SingleInstance"

#: posted to the running instance when a second copy is started
PING_MESSAGE = win32.WM_APP + 3

#: kept alive for the lifetime of the process; closing it would drop the lock
_handle = None


def acquire() -> bool:
    """Take the instance lock. ``False`` when another copy already holds it.

    On the rare failure of ``CreateMutexW`` itself we report success: refusing
    to start because a lock could not be created would be worse than running
    without the guard.
    """
    global _handle
    ctypes.set_last_error(0)
    handle = win32.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    if ctypes.get_last_error() == win32.ERROR_ALREADY_EXISTS:
        win32.kernel32.CloseHandle(handle)
        return False
    _handle = handle
    return True


def release() -> None:
    global _handle
    if _handle:
        win32.kernel32.CloseHandle(_handle)
        _handle = None


def ping_running_instance(class_name: str) -> bool:
    """Ask the copy that owns the lock to announce itself.

    The overlay window exists for as long as the process runs, but it is hidden
    whenever the thumbnail is not on screen - ``FindWindowW`` finds hidden
    windows too, so this works in both states.
    """
    hwnd = win32.user32.FindWindowW(class_name, None)
    if not hwnd:
        return False
    return bool(win32.user32.PostMessageW(hwnd, PING_MESSAGE, 0, 0))
