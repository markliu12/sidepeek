"""CS2 round-result OCR matching and notification de-duplication."""

import struct
import unittest
from types import SimpleNamespace
from unittest import mock

from sidepeek import win32
from sidepeek.app import App
from sidepeek.cs2_rounds import (
    ABSENT_FRAMES,
    PRESENT_FRAMES,
    RoundResultState,
    classify_round_result,
    classify_banner_color,
    crop_result_region,
)
from sidepeek.config import Settings
from sidepeek.watcher import Target


class ClassificationTest(unittest.TestCase):
    def test_matches_both_round_result_labels(self):
        self.assertEqual(classify_round_result("回合落敗"), "回合落敗")
        self.assertEqual(classify_round_result("回合\n勝利"), "回合勝利")

    def test_non_result_text_is_silent(self):
        self.assertIsNone(classify_round_result("MVP 玩家擊殺"))
        self.assertIsNone(classify_round_result(""))

    def test_crops_center_region_to_bmp(self):
        width, height = 100, 100
        frame = bytes([0, 0, 0, 255]) * width * height
        bmp, crop_w, crop_h = crop_result_region(frame, width, height)
        self.assertEqual((crop_w, crop_h), (30, 14))
        self.assertEqual(bmp[:2], b"BM")
        self.assertEqual(struct.unpack_from("<ii", bmp, 18), (crop_w, crop_h))

    def test_banner_colour_fallback_distinguishes_win_and_loss(self):
        width = height = 100
        frame = bytearray([0, 0, 0, 255] * width * height)
        for y in range(15, 27):
            for x in range(37, 63):
                offset = (y * width + x) * 4
                frame[offset:offset + 4] = bytes((20, 55, 220, 255))
        self.assertEqual(classify_banner_color(frame, width, height), "回合落敗")
        for y in range(15, 27):
            for x in range(37, 63):
                offset = (y * width + x) * 4
                frame[offset:offset + 4] = bytes((20, 190, 240, 255))
        self.assertEqual(classify_banner_color(frame, width, height), "回合勝利")
        self.assertIsNone(classify_banner_color(bytes([0, 0, 0, 255]) * width * height, width, height))


class RoundResultStateTest(unittest.TestCase):
    def test_requires_two_matching_frames_and_notifies_once(self):
        state = RoundResultState()
        self.assertIsNone(state.observe("回合勝利"))
        self.assertEqual(state.observe("回合勝利"), "回合勝利")
        for _ in range(PRESENT_FRAMES + 2):
            self.assertIsNone(state.observe("回合勝利"))

    def test_requires_three_absent_frames_to_rearm(self):
        state = RoundResultState()
        state.observe("回合落敗")
        self.assertEqual(state.observe("回合落敗"), "回合落敗")
        for _ in range(ABSENT_FRAMES - 1):
            state.observe(None)
            self.assertIsNone(state.observe("回合落敗"))
            # A positive while latched cancels the absence sequence.
        for _ in range(ABSENT_FRAMES):
            state.observe(None)
        self.assertIsNone(state.observe("回合落敗"))
        self.assertEqual(state.observe("回合落敗"), "回合落敗")

    def test_changed_result_requires_two_frames(self):
        state = RoundResultState()
        state.observe("回合勝利")
        state.observe("回合勝利")
        self.assertIsNone(state.observe("回合落敗"))
        self.assertIsNone(state.observe("回合落敗"))  # still latched


class TargetGateTest(unittest.TestCase):
    def setUp(self):
        self.app = App.__new__(App)
        self.app.settings = Settings(cs2_round_notifications=True)
        self.app.watcher = SimpleNamespace(
            paused=False, last_game=Target(42, "CS2", "cs2.exe")
        )

    @mock.patch.object(win32, "foreground", return_value=99)
    @mock.patch.object(win32, "is_minimized", return_value=False)
    @mock.patch.object(win32, "is_visible", return_value=True)
    @mock.patch.object(win32, "is_window", return_value=True)
    def test_only_background_cs2_is_monitored(self, *_mocks):
        self.assertEqual(self.app._cs2_round_target(), 42)

    @mock.patch.object(win32, "foreground", return_value=42)
    @mock.patch.object(win32, "is_minimized", return_value=False)
    @mock.patch.object(win32, "is_visible", return_value=True)
    @mock.patch.object(win32, "is_window", return_value=True)
    def test_foreground_cs2_is_silent(self, *_mocks):
        self.assertEqual(self.app._cs2_round_target(), 0)

    def test_paused_or_disabled_monitor_is_silent(self):
        self.app.watcher.paused = True
        self.assertEqual(self.app._cs2_round_target(), 0)
        self.app.watcher.paused = False
        self.app.settings.cs2_round_notifications = False
        self.assertEqual(self.app._cs2_round_target(), 0)

    @mock.patch("sidepeek.app.WindowsToast.show", side_effect=OSError("toast unavailable"))
    def test_notification_falls_back_to_tray_balloon(self, _toast):
        self.app.overlay = SimpleNamespace(notify=mock.Mock(return_value=True))
        self.app._notify_cs2_round("CS2 回合勝利", "CS2 回合已结束。")
        self.app.overlay.notify.assert_called_once_with("CS2 回合勝利", "CS2 回合已结束。")


if __name__ == "__main__":
    unittest.main()
