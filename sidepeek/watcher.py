"""Decides *when* to peek and *which* window to peek at.

The state machine is deliberately tiny:

* While a game owns the foreground, remember it as ``last_game``.
* As soon as the foreground moves to anything else, that remembered window
  becomes the peek target.
* When the game gets the foreground back, the decision flips to ``hide``.

Remembering the *previously* focused fullscreen window instead of guessing from
a process list is what makes the tool usable with zero configuration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import win32
from .config import Settings


@dataclass(frozen=True)
class Target:
    hwnd: int
    title: str
    exe: str

    @property
    def display_name(self) -> str:
        return self.title or self.exe or "Game"


@dataclass(frozen=True)
class Decision:
    show: bool
    target: Target | None = None
    reason: str = ""


def describe(hwnd: int) -> Target:
    return Target(hwnd, win32.window_title(hwnd), win32.process_name(hwnd))


def covers_monitor_rect(
    rect: tuple[int, int, int, int] | None,
    monitor: tuple[int, int, int, int] | None,
    maximized: bool = False,
    threshold: float = 0.98,
    loose: float = 0.90,
) -> bool:
    """Decide whether a window rectangle looks like a fullscreen game.

    Two rules, both comparing against the *monitor* rect rather than the work
    area:

    * covering >= 98% of the monitor - a real fullscreen / borderless window,
      which also hides the taskbar;
    * covering >= 90% and **not maximised** - e.g. a 2560x1440 game on a
      2560x1600 panel. A maximised window is excluded here, because a
      maximised window only fills the work area (~96%) and is exactly the
      case we want to ignore (browsers, editors, ...).
    """
    if not rect or not monitor:
        return False
    left, top, right, bottom = rect
    ml, mt, mr, mb = monitor
    mon_w, mon_h = mr - ml, mb - mt
    if mon_w <= 0 or mon_h <= 0:
        return False
    ratio_w = (right - left) / mon_w
    ratio_h = (bottom - top) / mon_h
    if ratio_w >= threshold and ratio_h >= threshold:
        return True
    return (not maximized) and ratio_w >= loose and ratio_h >= loose


def covers_monitor(hwnd: int, threshold: float = 0.98, loose: float = 0.90) -> bool:
    rect = win32.frame_bounds(hwnd) or win32.window_rect(hwnd)
    return covers_monitor_rect(
        rect, win32.monitor_rect(hwnd), win32.is_maximized(hwnd), threshold, loose
    )


class Watcher:
    #: how often a scan for an already-running game is allowed (seconds)
    ADOPT_INTERVAL = 2.0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.paused = False
        self.locked: Target | None = None
        self.last_game: Target | None = None
        self._foreground = 0
        self._last_adopt = 0.0

    # -- public api --------------------------------------------------------
    def lock_foreground(self) -> Target | None:
        """Pin whatever is in the foreground right now as the peek target."""
        hwnd = win32.foreground()
        if not win32.is_window(hwnd):
            return None
        self.locked = describe(hwnd)
        self.last_game = self.locked
        return self.locked

    def candidates(self, limit: int = 8) -> list[Target]:
        """Windows the user could pin as the peek target.

        Follows the same rule as target resolution: with an allowlist only
        matching processes qualify, otherwise anything that fills a monitor
        and is not on the ignore list. Duplicates (same process and title) are
        collapsed to the largest window.
        """
        s = self.settings
        found: dict[tuple[str, str], tuple[int, Target]] = {}
        for hwnd in win32.enum_windows():
            if not win32.is_visible(hwnd) or win32.is_minimized(hwnd):
                continue
            exe = win32.process_name(hwnd).lower()
            if not exe:
                continue
            if s.targets:
                if exe not in s.targets:
                    continue
            else:
                if exe in s.ignore or not s.auto_detect_fullscreen:
                    continue
                if not covers_monitor(hwnd):
                    continue
            rect = win32.window_rect(hwnd)
            if not rect:
                continue
            area = (rect[2] - rect[0]) * (rect[3] - rect[1])
            key = (exe, win32.window_title(hwnd))
            if key not in found or area > found[key][0]:
                found[key] = (area, describe(hwnd))
        ordered = sorted(found.values(), key=lambda item: -item[0])
        return [target for _, target in ordered][:limit]

    def evaluate(self, overlay_hwnd: int = 0) -> Decision:
        s = self.settings
        if self.paused:
            return Decision(False, None, "paused")

        fg = win32.foreground()
        if fg and fg != overlay_hwnd:
            self._foreground = fg

        target = self._resolve_target(self._foreground)
        if target is None:
            return Decision(False, None, "no target")

        if self._foreground == target.hwnd:
            return Decision(False, target, "target in foreground")
        if not win32.is_window(target.hwnd):
            self.last_game = None
            self.locked = None
            return Decision(False, None, "target closed")
        if not win32.is_visible(target.hwnd):
            self.last_game = None
            return Decision(False, None, "target hidden")
        if s.hide_when_minimized and win32.is_minimized(target.hwnd):
            return Decision(False, target, "target minimised")
        if s.hide_when_hovered and overlay_hwnd and self._cursor_over(overlay_hwnd):
            return Decision(False, target, "cursor over overlay")

        return Decision(True, target, "target in background")

    # -- internals ---------------------------------------------------------
    def _resolve_target(self, fg: int) -> Target | None:
        s = self.settings

        # Drop state that points at a window which no longer exists. Games
        # recreate their window on a resolution change, so a stale handle is
        # not as unlikely as it sounds.
        if self.last_game is not None and not win32.is_window(self.last_game.hwnd):
            self.last_game = None
        if self.locked is not None and not win32.is_window(self.locked.hwnd):
            self.locked = None

        if self.locked:
            return self.locked

        if s.targets:
            return self._resolve_allowlist(fg)

        if not s.auto_detect_fullscreen:
            return self.last_game

        candidate = self._maybe_remember(fg)
        return candidate or self.last_game or self._adopt_largest_fullscreen()

    def _adopt_largest_fullscreen(self) -> Target | None:
        """Find a game that was already running when SidePeek started.

        Without this, launching the tool *after* tabbing out of the game does
        nothing at all: nothing was ever focused to be remembered.
        """
        now = time.monotonic()
        if now - self._last_adopt < self.ADOPT_INTERVAL:
            return self.last_game
        self._last_adopt = now
        if not self.settings.auto_detect_fullscreen:
            return None

        best: Target | None = None
        best_area = 0
        for hwnd in win32.enum_windows():
            if not win32.is_visible(hwnd):
                continue
            exe = win32.process_name(hwnd).lower()
            if not exe or exe in self.settings.ignore:
                continue
            if not covers_monitor(hwnd):
                continue
            rect = win32.window_rect(hwnd)
            if not rect:
                continue
            area = (rect[2] - rect[0]) * (rect[3] - rect[1])
            if area > best_area:
                best_area = area
                best = describe(hwnd)
        if best:
            self.last_game = best
        return best

    def _maybe_remember(self, hwnd: int) -> Target | None:
        """Remember ``hwnd`` as the game when it looks like one."""
        if not hwnd or not win32.is_window(hwnd) or not win32.is_visible(hwnd):
            return None
        s = self.settings
        exe = win32.process_name(hwnd).lower()
        if not exe or exe in s.ignore:
            return None
        if not covers_monitor(hwnd):
            return None
        target = describe(hwnd)
        self.last_game = target
        return target

    def _resolve_allowlist(self, fg: int) -> Target | None:
        s = self.settings
        known = {t.lower() for t in s.targets}

        if fg and win32.is_window(fg):
            exe = win32.process_name(fg).lower()
            if exe in known:
                self.last_game = describe(fg)
                return self.last_game

        if self.last_game and win32.is_window(self.last_game.hwnd):
            if self.last_game.exe.lower() in known:
                return self.last_game

        best: Target | None = None
        best_area = 0
        for hwnd in win32.enum_windows():
            if not win32.is_visible(hwnd) or win32.is_minimized(hwnd):
                continue
            exe = win32.process_name(hwnd).lower()
            if exe not in known:
                continue
            rect = win32.window_rect(hwnd)
            if not rect:
                continue
            area = (rect[2] - rect[0]) * (rect[3] - rect[1])
            if area > best_area:
                best_area = area
                best = describe(hwnd)
        if best:
            self.last_game = best
        return best

    def _cursor_over(self, hwnd: int) -> bool:
        pt = win32.wt.POINT()
        if not win32.user32.GetCursorPos(win32.ctypes.byref(pt)):
            return False
        rect = win32.window_rect(hwnd)
        if not rect:
            return False
        return rect[0] <= pt.x < rect[2] and rect[1] <= pt.y < rect[3]