"""Configuration handling.

The config is plain JSON so it can be edited with Notepad and lives next to the
source (or next to the .exe once frozen). Unknown keys are ignored and missing
keys fall back to :data:`DEFAULTS`, so upgrading never breaks an old file.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import dataclass

DEFAULTS: dict = {
    "peek": {
        # size of the floating window, in physical pixels
        "width": 480,
        "height": 270,
        # "auto" | "dwm" | "capture"
        "backend": "auto",
        # "top-left" | "top-right" | "bottom-left" | "bottom-right" | "custom"
        "anchor": "bottom-right",
        "margin": 24,
        # used when anchor == "custom" (top-left corner of the overlay)
        "pos": [0, 0],
        # inner padding between the border and the video
        "padding": 6,
        # 0-100, applied to the DWM thumbnail
        "opacity": 100,
        # show the caption strip with the process name and elapsed time
        "caption": True,
        # click the thumbnail to jump back into the game
        "click_to_focus": True,
        # hide while the game is minimised (a minimised window stops rendering)
        "hide_when_minimized": True,
        # only peek while the mouse is NOT over the overlay
        "hide_when_hovered": False,
        # capture backend frame rate
        "fps": 20,
        # process names (lower-case) that should be treated as games.
        # empty list -> auto-detect fullscreen windows
        "targets": [],
        "auto_detect_fullscreen": True,
        # process names that must never be treated as a game
        "ignore": [
            "explorer.exe",
            "python.exe",
            "pythonw.exe",
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "code.exe",
            "devenv.exe",
            "windowsterminal.exe",
            "powershell.exe",
            "cmd.exe",
            # Windows shell surfaces that also happen to be fullscreen
            "textinputhost.exe",
            "applicationframehost.exe",
            "systemsettings.exe",
            "searchhost.exe",
            "shellexperiencehost.exe",
            "startmenuexperiencehost.exe",
        ],
        "poll_ms": 300,
        "hotkey_toggle": "ctrl+alt+g",
        "hotkey_lock": "ctrl+alt+l",
        "hotkey_quit": "ctrl+alt+q",
        "show_in_taskbar": False,
    }
}


@dataclass
class Settings:
    width: int = 480
    height: int = 270
    backend: str = "auto"
    anchor: str = "bottom-right"
    margin: int = 24
    pos: tuple[int, int] = (0, 0)
    padding: int = 6
    opacity: int = 100
    caption: bool = True
    click_to_focus: bool = True
    hide_when_minimized: bool = True
    hide_when_hovered: bool = False
    fps: int = 20
    targets: tuple[str, ...] = ()
    auto_detect_fullscreen: bool = True
    ignore: tuple[str, ...] = ()
    poll_ms: int = 300
    hotkey_toggle: str = "ctrl+alt+g"
    hotkey_lock: str = "ctrl+alt+l"
    hotkey_quit: str = "ctrl+alt+q"
    show_in_taskbar: bool = False


def app_dir() -> str:
    """Directory that holds ``config.json`` (source dir or frozen exe dir)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_path() -> str:
    return os.path.join(app_dir(), "config.json")


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: str | None = None) -> tuple[Settings, str]:
    """Load settings, creating the file with defaults when it is missing."""
    path = path or default_path()
    data = DEFAULTS
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = _merge(DEFAULTS, json.load(fh))
        except (OSError, ValueError) as exc:
            print(f"[sidepeek] config unreadable ({exc}); using defaults")
    else:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(DEFAULTS, fh, indent=2, ensure_ascii=False)
            print(f"[sidepeek] wrote default config to {path}")
        except OSError:
            pass

    p = data.get("peek", {})
    settings = Settings(
        width=max(120, int(p.get("width", 480))),
        height=max(70, int(p.get("height", 270))),
        backend=str(p.get("backend", "auto")).lower(),
        anchor=str(p.get("anchor", "bottom-right")).lower(),
        margin=int(p.get("margin", 24)),
        pos=tuple(int(v) for v in (p.get("pos") or (0, 0)))[:2],  # type: ignore[arg-type]
        padding=max(0, int(p.get("padding", 6))),
        opacity=max(10, min(100, int(p.get("opacity", 100)))),
        caption=bool(p.get("caption", True)),
        click_to_focus=bool(p.get("click_to_focus", True)),
        hide_when_minimized=bool(p.get("hide_when_minimized", True)),
        hide_when_hovered=bool(p.get("hide_when_hovered", False)),
        fps=max(1, min(60, int(p.get("fps", 20)))),
        targets=tuple(str(t).lower() for t in p.get("targets", [])),
        auto_detect_fullscreen=bool(p.get("auto_detect_fullscreen", True)),
        ignore=tuple(str(t).lower() for t in p.get("ignore", [])),
        poll_ms=max(80, int(p.get("poll_ms", 300))),
        hotkey_toggle=str(p.get("hotkey_toggle", "ctrl+alt+g")),
        hotkey_lock=str(p.get("hotkey_lock", "ctrl+alt+l")),
        hotkey_quit=str(p.get("hotkey_quit", "ctrl+alt+q")),
        show_in_taskbar=bool(p.get("show_in_taskbar", False)),
    )
    return settings, path


def save_runtime(path: str, settings: Settings) -> None:
    """Persist the bits the user changes at runtime (size, position, anchor)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = copy.deepcopy(DEFAULTS)

    peek = data.setdefault("peek", {})
    peek["width"] = settings.width
    peek["height"] = settings.height
    peek["anchor"] = settings.anchor
    peek["pos"] = list(settings.pos)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass
