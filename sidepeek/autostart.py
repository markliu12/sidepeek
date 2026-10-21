"""Run-at-login toggle.

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run needs no elevation and
no installer, which keeps the "unzip and run" promise intact. Windows reads it
once per logon, so the switch takes effect next session - there is no need to
restart SidePeek itself.
"""

from __future__ import annotations

import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SidePeek"


def _source_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _windowless_python() -> str:
    """``pythonw.exe`` next to the running interpreter, when it exists.

    Started through ``python.exe`` the console window would otherwise reappear
    at every logon.
    """
    exe = sys.executable or ""
    if exe.lower().endswith("python.exe"):
        candidate = exe[: -len("python.exe")] + "pythonw.exe"
        if os.path.isfile(candidate):
            return candidate
    return exe


def launch_command() -> str:
    """Command line stored in the registry.

    Quoted in both branches: neither path may contain spaces and the frozen
    executable very often does (``Program Files``, a folder on the desktop).
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.join(_source_dir(), "run.py")
    return f'"{_windowless_python()}" "{script}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return bool(value)


def enable() -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
    except OSError:
        return False
    return True


def disable() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return True                              # already off
    except OSError:
        return False
    return True


def toggle() -> bool:
    """Flip the setting and report the state it ended up in."""
    if is_enabled():
        disable()
    else:
        enable()
    return is_enabled()
