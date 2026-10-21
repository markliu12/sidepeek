"""Overlay layout and notification-area behaviour that does not need a window."""

import unittest

from sidepeek.config import Settings
from sidepeek.overlay import (
    TRAY_MENU_ACTIVATE,
    TRAY_MENU_CLEAR_TARGET,
    TRAY_MENU_QUIT,
    TRAY_MENU_TOGGLE,
    Overlay,
    tray_tooltip,
)


def make_overlay(**overrides):
    """An Overlay that never creates a Win32 window."""
    settings = Settings(**overrides)
    return Overlay(settings, "unused.json")


class ContentBoxTest(unittest.TestCase):
    def test_default_window_leaves_a_16_by_9_picture_area(self):
        overlay = make_overlay()
        left, top, right, bottom = overlay._content_box()
        width, height = right - left, bottom - top
        self.assertEqual((width, height), (480, 270))
        self.assertAlmostEqual(width / height, 16 / 9, delta=0.01)

    def test_caption_strip_is_taken_out_of_the_picture_area(self):
        with_caption = make_overlay(caption=True)._content_box()
        without = make_overlay(caption=False)._content_box()
        self.assertEqual(without[3] - with_caption[3], 22)

    def test_padding_separates_the_picture_from_the_border(self):
        left, top, right, bottom = make_overlay(padding=10, width=500, height=300)._content_box()
        self.assertEqual((left, top), (10, 10))
        self.assertEqual((right, bottom), (490, 300 - 10 - 22))

    def test_caption_rect_sits_inside_the_window(self):
        overlay = make_overlay()
        left, top, right, bottom = overlay._caption_rect()
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(bottom, overlay._height)
        self.assertLessEqual(right, overlay._width)
        self.assertGreater(bottom - top, 0)


class TrayTest(unittest.TestCase):
    def test_tooltip_reflects_pause_state(self):
        self.assertIn("监视中", tray_tooltip(False))
        self.assertIn("已暂停", tray_tooltip(True))
        self.assertNotEqual(tray_tooltip(False), tray_tooltip(True))

    def test_menu_commands_reach_the_callbacks(self):
        overlay = make_overlay()
        called = []
        overlay.on_activate = lambda: called.append("activate")
        overlay.on_clear_target = lambda: called.append("clear")
        overlay.on_toggle_pause = lambda: called.append("toggle")
        overlay.on_quit = lambda: called.append("quit")

        for command in (TRAY_MENU_ACTIVATE, TRAY_MENU_CLEAR_TARGET,
                        TRAY_MENU_TOGGLE, TRAY_MENU_QUIT):
            overlay._on_tray_command(command)

        self.assertEqual(called, ["activate", "clear", "toggle", "quit"])

    def test_unknown_command_is_ignored(self):
        overlay = make_overlay()
        called = []
        overlay.on_quit = lambda: called.append("quit")
        overlay._on_tray_command(9999)
        self.assertEqual(called, [])

    def test_set_paused_updates_state_without_a_window(self):
        overlay = make_overlay()
        overlay.set_paused(True)
        self.assertTrue(overlay._paused)
        self.assertFalse(overlay.tray_added)


if __name__ == "__main__":
    unittest.main()
