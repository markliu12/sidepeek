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

from .diag import log

DEFAULTS: dict = {
    "peek": {
        # Window size in physical pixels. The default leaves a 480x270 (16:9)
        # picture area once padding (6 px) and the caption strip (22 px) are
        # subtracted, so 16:9 games fill the thumbnail without black bars.
        "width": 492,
        "height": 304,
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
        # derive the height from the aspect ratio of the game so the picture
        # fills the frame instead of being letterboxed
        "fit_aspect": True,
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
        # notify when CS2 shows the round-result banner while in background
        "cs2_round_notifications": True,
    }
}


@dataclass
class Settings:
    width: int = 492
    height: int = 304
    backend: str = "auto"
    anchor: str = "bottom-right"
    margin: int = 24
    pos: tuple[int, int] = (0, 0)
    padding: int = 6
    opacity: int = 100
    fit_aspect: bool = True
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
    cs2_round_notifications: bool = True


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
            log(f"config unreadable ({exc}); using defaults")
    else:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(DEFAULTS, fh, indent=2, ensure_ascii=False)
            log(f"wrote default config to {path}")
        except OSError:
            pass

    p = data.get("peek", {})
    settings = Settings(
        width=max(160, int(p.get("width", 492))),
        height=max(90, int(p.get("height", 304))),
        backend=str(p.get("backend", "auto")).lower(),
        anchor=str(p.get("anchor", "bottom-right")).lower(),
        margin=int(p.get("margin", 24)),
        pos=tuple(int(v) for v in (p.get("pos") or (0, 0)))[:2],  # type: ignore[arg-type]
        padding=max(0, int(p.get("padding", 6))),
        opacity=max(10, min(100, int(p.get("opacity", 100)))),
        fit_aspect=bool(p.get("fit_aspect", True)),
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
        cs2_round_notifications=bool(p.get("cs2_round_notifications", True)),
    )
    return settings, path


def save_runtime(
    path: str, settings: Settings, skip: tuple[str, ...] | frozenset[str] = ()
) -> None:
    """Persist the bits the user changes at runtime (size, position, anchor).

    ``skip`` names fields that came from the command line for this run only.
    Persisting those would silently make a one-off ``--width 800`` permanent.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = copy.deepcopy(DEFAULTS)

    peek = data.setdefault("peek", {})
    if "width" not in skip:
        peek["width"] = settings.width
    if "height" not in skip:
        peek["height"] = settings.height
    if "fit_aspect" not in skip:
        peek["fit_aspect"] = settings.fit_aspect
    if "anchor" not in skip:
        peek["anchor"] = settings.anchor
        peek["pos"] = list(settings.pos)
    if "cs2_round_notifications" not in skip:
        peek["cs2_round_notifications"] = settings.cs2_round_notifications
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass
