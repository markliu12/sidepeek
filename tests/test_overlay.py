"""Overlay layout and notification-area behaviour that does not need a window."""

import unittest

from sidepeek.config import Settings
from sidepeek.watcher import Target
from sidepeek.overlay import (
    TRAY_MENU_ACTIVATE,
    TRAY_MENU_QUIT,
    TRAY_MENU_TOGGLE,
    MENU_TARGET_AUTO,
    MENU_TARGET_BASE,
    Overlay,
    fitted_height,
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


class FitAspectTest(unittest.TestCase):
    """The height follows the game, so no aspect ratio is favoured."""

    PAD = 6
    CAPTION = 22

    def height_for(self, source):
        return fitted_height(492, source, self.PAD, self.CAPTION)

    def test_16_by_9_keeps_the_default_height(self):
        self.assertEqual(self.height_for((1920, 1080)), 304)

    def test_16_by_10_gets_a_taller_window(self):
        # 480 wide picture at 16:10 is 300 tall, plus padding and caption
        self.assertEqual(self.height_for((2560, 1600)), 334)

    def test_ultrawide_gets_a_shorter_window(self):
        height = self.height_for((2560, 1080))
        inner_h = height - 2 * self.PAD - self.CAPTION
        self.assertAlmostEqual(480 / inner_h, 2560 / 1080, delta=0.02)

    def test_four_by_three(self):
        self.assertEqual(self.height_for((1024, 768)), 394)

    def test_resulting_picture_area_matches_the_source(self):
        for source in ((1920, 1080), (2560, 1600), (2560, 1080), (1024, 768), (1600, 900)):
            height = self.height_for(source)
            inner_w = 492 - 2 * self.PAD
            inner_h = height - 2 * self.PAD - self.CAPTION
            self.assertAlmostEqual(inner_w / inner_h, source[0] / source[1], delta=0.03)

    def test_without_caption_the_height_drops(self):
        with_caption = fitted_height(492, (1920, 1080), 6, 22)
        without = fitted_height(492, (1920, 1080), 6, 0)
        self.assertEqual(with_caption - without, 22)

    def test_unknown_source_leaves_the_size_alone(self):
        self.assertEqual(fitted_height(492, (0, 0), 6, 22), 0)

    def test_minimum_height_is_respected(self):
        # a very wide game at a very small width would otherwise go tiny
        self.assertGreaterEqual(fitted_height(160, (2560, 400), 6, 22), 90)


class TrayTest(unittest.TestCase):
    def test_tooltip_reflects_pause_state(self):
        self.assertIn("监视中", tray_tooltip(False))
        self.assertIn("已暂停", tray_tooltip(True))
        self.assertNotEqual(tray_tooltip(False), tray_tooltip(True))

    def test_menu_commands_reach_the_callbacks(self):
        overlay = make_overlay()
        called = []
        overlay.on_activate = lambda: called.append("activate")
        overlay.on_toggle_pause = lambda: called.append("toggle")
        overlay.on_quit = lambda: called.append("quit")

        for command in (TRAY_MENU_ACTIVATE, TRAY_MENU_TOGGLE, TRAY_MENU_QUIT):
            overlay._on_tray_command(command)

        self.assertEqual(called, ["activate", "toggle", "quit"])

    def test_target_menu_choice_reaches_the_callback(self):
        overlay = make_overlay()
        picked = []
        overlay.on_select_target = picked.append
        target = Target(4242, "Dota 2", "dota2.exe")
        overlay._menu_choices = {MENU_TARGET_AUTO: None, MENU_TARGET_BASE: target}

        overlay._on_tray_command(MENU_TARGET_BASE)
        overlay._on_tray_command(MENU_TARGET_AUTO)

        self.assertEqual(picked, [target, None])

    def test_locked_target_is_reset_when_window_is_gone(self):
        overlay = make_overlay()
        overlay.set_locked(Target(1, "gone", "gone.exe"))
        self.assertIsNotNone(overlay._locked_target)

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
