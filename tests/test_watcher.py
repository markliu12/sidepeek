"""The watch/show decision, with the Win32 layer mocked out."""

import contextlib
import unittest
from unittest import mock

import sidepeek.watcher as watcher_mod
from sidepeek.config import Settings
from sidepeek.watcher import Watcher, covers_monitor_rect

MONITOR = (0, 0, 1920, 1080)


class CoversMonitorRectTest(unittest.TestCase):
    def test_exact_monitor_size_is_fullscreen(self):
        self.assertTrue(covers_monitor_rect(MONITOR, MONITOR))

    def test_maximised_window_is_not_fullscreen(self):
        # a maximised window only fills the work area (~96%) - not a game
        self.assertFalse(covers_monitor_rect((0, 0, 1920, 1040), MONITOR, maximized=True))

    def test_large_unmaximised_window_is_fullscreen(self):
        # e.g. a 2560x1440 game on a 2560x1600 panel
        self.assertTrue(covers_monitor_rect((0, 0, 2560, 1440), (0, 0, 2560, 1600)))

    def test_normal_window_is_not_fullscreen(self):
        self.assertFalse(covers_monitor_rect((100, 100, 1100, 700), MONITOR))

    def test_degenerate_inputs(self):
        self.assertFalse(covers_monitor_rect(None, MONITOR))
        self.assertFalse(covers_monitor_rect(MONITOR, None))
        self.assertFalse(covers_monitor_rect(MONITOR, (0, 0, 0, 0)))


class WatcherHarness(unittest.TestCase):
    """Wires the watcher's Win32 calls to mutable fake state."""

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

        self.fg = 0
        self.exes: dict[int, str] = {}
        self.titles: dict[int, str] = {}
        self.rects: dict[int, tuple] = {}
        self.minimized: set[int] = set()
        self.visible: set[int] = set()
        self.windows: list[int] = []

        w = watcher_mod.win32
        self._patch(w, "foreground", lambda: self.fg)
        self._patch(w, "is_window", lambda h: h in self.exes)
        self._patch(w, "is_visible", lambda h: h in self.visible)
        self._patch(w, "is_minimized", lambda h: h in self.minimized)
        self._patch(w, "is_maximized", lambda h: False)
        self._patch(w, "process_name", lambda h: self.exes.get(h, ""))
        self._patch(w, "window_title", lambda h: self.titles.get(h, f"win{h}"))
        self._patch(w, "window_rect", lambda h: self.rects.get(h, MONITOR))
        self._patch(w, "frame_bounds", lambda h: self.rects.get(h, MONITOR))
        self._patch(w, "monitor_rect", lambda h: MONITOR)
        self._patch(w, "enum_windows", lambda: list(self.windows))

    def _patch(self, module, name, side_effect):
        self.stack.enter_context(mock.patch.object(module, name, side_effect=side_effect))

    def add_window(self, hwnd, exe, rect=MONITOR, minimized=False):
        self.exes[hwnd] = exe
        self.rects[hwnd] = rect
        self.visible.add(hwnd)
        if minimized:
            self.minimized.add(hwnd)
        self.windows.append(hwnd)


class DecisionTest(WatcherHarness):
    def test_allowlist_shows_when_target_is_in_background(self):
        self.add_window(777, "cs2.exe")
        self.add_window(111, "browser.exe")
        self.fg = 111
        decision = Watcher(Settings(targets=("cs2.exe",))).evaluate()
        self.assertTrue(decision.show)
        self.assertEqual(decision.target.hwnd, 777)

    def test_hides_when_target_has_focus(self):
        self.add_window(777, "cs2.exe")
        self.fg = 777
        decision = Watcher(Settings(targets=("cs2.exe",))).evaluate()
        self.assertFalse(decision.show)
        self.assertEqual(decision.reason, "target in foreground")

    def test_pause_always_hides(self):
        self.add_window(777, "cs2.exe")
        self.add_window(111, "browser.exe")
        self.fg = 111
        watcher = Watcher(Settings(targets=("cs2.exe",)))
        watcher.paused = True
        self.assertFalse(watcher.evaluate().show)

    def test_locked_target_hides_while_minimised(self):
        self.add_window(777, "cs2.exe")
        self.fg = 777
        watcher = Watcher(Settings())
        self.assertIsNotNone(watcher.lock_foreground())

        self.add_window(111, "browser.exe")
        self.fg = 111
        self.minimized.add(777)
        decision = watcher.evaluate()
        self.assertFalse(decision.show)
        self.assertEqual(decision.reason, "target minimised")

    def test_auto_mode_remembers_then_shows(self):
        self.add_window(777, "cs2.exe")
        self.fg = 777
        watcher = Watcher(Settings(targets=(), ignore=()))

        first = watcher.evaluate()          # game focused -> remembered, hidden
        self.assertFalse(first.show)
        self.assertEqual(watcher.last_game.hwnd, 777)

        self.add_window(111, "chrome.exe", rect=(100, 100, 1100, 700))
        self.fg = 111
        second = watcher.evaluate()         # tabbed out -> show
        self.assertTrue(second.show)
        self.assertEqual(second.target.hwnd, 777)

    def test_ignored_fullscreen_window_is_never_a_game(self):
        # a fullscreen browser must not be adopted as the target
        self.add_window(111, "chrome.exe")
        self.fg = 111
        watcher = Watcher(Settings(targets=(), ignore=("chrome.exe",)))
        decision = watcher.evaluate()
        self.assertFalse(decision.show)
        self.assertIsNone(watcher.last_game)

    def test_gone_target_clears_state(self):
        self.add_window(777, "cs2.exe")
        self.fg = 777
        watcher = Watcher(Settings(targets=("cs2.exe",)))
        self.assertFalse(watcher.evaluate().show)

        self.exes.pop(777)                  # game exited
        self.visible.discard(777)
        self.fg = 111
        decision = watcher.evaluate()
        self.assertFalse(decision.show)
        self.assertIsNone(watcher.last_game)


if __name__ == "__main__":
    unittest.main()
