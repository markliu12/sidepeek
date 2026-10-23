"""CS2 round-result OCR matching and notification de-duplication."""

import struct
import unittest
from types import SimpleNamespace
from unittest import mock

from sidepeek import win32
from sidepeek.app import App
from sidepeek.cs2_rounds import (
    ABSENT_FRAMES,
    MIN_NOTIFY_INTERVAL,
    PRESENT_FRAMES,
    RoundResultState,
    classify_round_result,
    classify_banner_color,
    colour_probe_allowed,
    crop_result_region,
)
from sidepeek.config import Settings
from sidepeek.notices import (
    LANGUAGES,
    ROUND_NOTICES,
    coerce,
    detect_language,
    round_notice,
)
from sidepeek.watcher import Target


class FakeClock:
    """Monotonic clock the tests can advance by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ClassificationTest(unittest.TestCase):
    def test_matches_both_round_result_labels(self):
        self.assertEqual(classify_round_result("回合落敗"), "loss")
        self.assertEqual(classify_round_result("回合\n勝利"), "win")

    def test_matches_simplified_and_traditional_variants(self):
        # the client localises the banner, the OCR engine does not necessarily
        # agree with it, so every variant has to land on the same result
        for text in ("回合失败", "回合失敗", "回合落敗"):
            self.assertEqual(classify_round_result(text), "loss", text)
        for text in ("回合胜利", "回合勝利", "回合獲勝"):
            self.assertEqual(classify_round_result(text), "win", text)

    def test_non_result_text_is_silent(self):
        self.assertIsNone(classify_round_result("MVP 玩家擊殺"))
        self.assertIsNone(classify_round_result(""))

    def test_one_mangled_glyph_still_classifies(self):
        # Windows OCR misreads a single stroke of the stylised label more often
        # than it misses the whole line, so 回合 + one result character is enough
        self.assertEqual(classify_round_result("回合失畋"), "loss")
        self.assertEqual(classify_round_result("回合滕利"), "win")
        self.assertEqual(classify_round_result("回合\n胜利"), "win")

    def test_team_line_and_neutral_text_stay_silent(self):
        # "反恐精英胜利" announces the team, not your own round result
        self.assertIsNone(classify_round_result("反恐精英胜利"))
        self.assertIsNone(classify_round_result("恐怖分子獲勝"))
        self.assertIsNone(classify_round_result("回合计时 1:30"))
        self.assertIsNone(classify_round_result("回合"))

    def test_english_labels(self):
        # the English client shows the same panel as ROUND WIN / ROUND LOSS and
        # Windows' Chinese OCR engine reads Latin text, so one engine suffices
        self.assertEqual(classify_round_result("ROUND WIN"), "win")
        self.assertEqual(classify_round_result("Round\nLoss"), "loss")
        self.assertEqual(classify_round_result("round won"), "win")
        self.assertEqual(classify_round_result("ROUND LOST"), "loss")

    def test_english_stats_columns_stay_silent(self):
        # "ROUND LOSSES" is a scoreboard column, not a round end
        self.assertIsNone(classify_round_result("ROUND LOSSES"))
        self.assertIsNone(classify_round_result("Round Wins"))
        self.assertIsNone(classify_round_result("ROUND WINDOW"))

    def test_crops_center_region_to_bmp(self):
        width, height = 100, 100
        frame = bytes([0, 0, 0, 255]) * width * height
        bmp, crop_w, crop_h = crop_result_region(frame, width, height)
        self.assertEqual((crop_w, crop_h), (36, 24))
        self.assertEqual(bmp[:2], b"BM")
        self.assertEqual(struct.unpack_from("<ii", bmp, 18), (crop_w, crop_h))

    def test_banner_colour_fallback_distinguishes_win_and_loss(self):
        width = height = 100
        frame = bytearray([0, 0, 0, 255] * width * height)
        for y in range(15, 27):
            for x in range(37, 63):
                offset = (y * width + x) * 4
                frame[offset:offset + 4] = bytes((20, 55, 220, 255))
        self.assertEqual(classify_banner_color(frame, width, height), "loss")
        for y in range(15, 27):
            for x in range(37, 63):
                offset = (y * width + x) * 4
                frame[offset:offset + 4] = bytes((20, 190, 240, 255))
        self.assertEqual(classify_banner_color(frame, width, height), "win")
        self.assertIsNone(classify_banner_color(bytes([0, 0, 0, 255]) * width * height, width, height))

    def test_scattered_red_is_not_a_banner(self):
        # blood, red props and kill-feed icons used to clear the old 2% bar
        width = height = 100
        frame = bytearray([0, 0, 0, 255] * width * height)
        for y in range(15, 27, 3):
            for x in range(37, 63, 9):
                offset = (y * width + x) * 4
                frame[offset:offset + 4] = bytes((20, 55, 220, 255))
        self.assertIsNone(classify_banner_color(frame, width, height))


class ColourProbeGateTest(unittest.TestCase):
    """A red crop is not a round end: OCR gets the final say."""

    def test_warm_map_texture_cannot_override_ocr(self):
        # an orange Inferno wall read as "round lost" mid-round; OCR saw the
        # frame and found no result, and that verdict must stand
        self.assertFalse(colour_probe_allowed(True, ""))
        self.assertFalse(colour_probe_allowed(True, "  \n\t "))
        self.assertFalse(colour_probe_allowed(True, "包点 A"))
        self.assertFalse(colour_probe_allowed(True, "回合失败"))

    def test_crop_word_is_not_required_when_ocr_is_missing(self):
        # without a Chinese OCR engine, colour is the only channel there is
        self.assertTrue(colour_probe_allowed(False, None))
        self.assertTrue(colour_probe_allowed(False, ""))

    def test_ocr_failure_keeps_the_fallback_alive(self):
        self.assertTrue(colour_probe_allowed(True, None))


class RoundResultStateTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.state = RoundResultState(clock=self.clock)

    def test_requires_two_matching_frames_and_notifies_once(self):
        self.assertIsNone(self.state.observe("win"))
        self.assertEqual(self.state.observe("win"), "win")
        for _ in range(PRESENT_FRAMES + 2):
            self.assertIsNone(self.state.observe("win"))

    def test_requires_absent_frames_to_rearm(self):
        self.state.observe("loss")
        self.assertEqual(self.state.observe("loss"), "loss")
        for _ in range(ABSENT_FRAMES - 1):
            self.state.observe(None)
            self.assertIsNone(self.state.observe("loss"))
            # A positive while latched cancels the absence sequence.
        for _ in range(ABSENT_FRAMES):
            self.state.observe(None)
        self.assertIsNone(self.state.observe("loss"))
        self.clock.advance(MIN_NOTIFY_INTERVAL)
        self.assertEqual(self.state.observe("loss"), "loss")

    def test_changed_result_requires_two_frames(self):
        self.state.observe("win")
        self.state.observe("win")
        self.assertIsNone(self.state.observe("loss"))
        self.assertIsNone(self.state.observe("loss"))  # still latched

    def test_flicker_inside_the_cooldown_stays_silent(self):
        # the banner fades out, the latch re-arms, and the same round must not
        # produce a second toast four seconds later
        self.state.observe("win")
        self.assertEqual(self.state.observe("win"), "win")
        for _ in range(ABSENT_FRAMES):
            self.state.observe(None)
        self.clock.advance(4.0)
        self.state.observe("win")
        self.assertIsNone(self.state.observe("win"))
        self.clock.advance(MIN_NOTIFY_INTERVAL)
        for _ in range(ABSENT_FRAMES):
            self.state.observe(None)
        self.state.observe("loss")
        self.assertEqual(self.state.observe("loss"), "loss")

    def test_variant_flip_does_not_renotify(self):
        # OCR can hand back simplified on one frame and traditional on the next
        first = classify_round_result("回合胜利")
        second = classify_round_result("回合勝利")
        self.state.observe(first)
        self.assertEqual(self.state.observe(first), "win")
        for _ in range(ABSENT_FRAMES):
            self.state.observe(None)
        self.state.observe(second)
        self.assertIsNone(self.state.observe(second))


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


class NoticeLanguageTest(unittest.TestCase):
    """The toast/push copy follows the banner the player actually saw."""

    def test_detects_script_from_the_banner_reading(self):
        self.assertEqual(detect_language("回合失败"), "zh-CN")
        self.assertEqual(detect_language("回合失敗"), "zh-TW")
        self.assertEqual(detect_language("回合獲勝"), "zh-TW")
        self.assertEqual(detect_language("ROUND WIN"), "en")
        self.assertEqual(detect_language("Round\nLost"), "en")

    def test_no_reading_means_no_guess(self):
        self.assertIsNone(detect_language(None))
        self.assertIsNone(detect_language(""))
        self.assertIsNone(detect_language("1:30"))

    def test_auto_follows_the_banner(self):
        self.assertEqual(round_notice("win", "auto", "en")[0], "CS2 round won")
        self.assertEqual(round_notice("loss", "auto", "en")[0], "CS2 round lost")
        self.assertEqual(round_notice("win", "auto", "zh-TW")[0], "CS2 回合勝利")
        self.assertEqual(round_notice("loss", "auto", "zh-CN")[0], "CS2 回合失败")

    def test_auto_without_a_reading_uses_the_fallback(self):
        # colour-probe verdicts carry no text at all
        self.assertEqual(round_notice("win", "auto", None)[0], "CS2 回合胜利")
        self.assertEqual(round_notice("win", "auto", None, "en")[0], "CS2 round won")
        self.assertEqual(round_notice("loss", "auto", None, "en")[0], "CS2 round lost")

    def test_explicit_language_ignores_detection(self):
        self.assertEqual(round_notice("win", "en", "zh-TW")[0], "CS2 round won")
        self.assertEqual(round_notice("loss", "zh-CN", "en")[0], "CS2 回合失败")
        self.assertEqual(round_notice("win", "zh-TW", "zh-CN")[0], "CS2 回合勝利")

    def test_config_spellings_are_tolerated(self):
        self.assertEqual(coerce("AUTO"), "auto")
        self.assertEqual(coerce("en-US"), "en")
        self.assertEqual(coerce("zh-Hant"), "zh-TW")
        self.assertEqual(coerce("zh-hans-cn"), "zh-CN")
        self.assertEqual(coerce("klingon"), "auto")
        self.assertEqual(coerce(None), "auto")

    def test_every_language_covers_both_results(self):
        for language in LANGUAGES:
            if language == "auto":
                continue
            for result in ("win", "loss"):
                title, message = ROUND_NOTICES[language][result]
                self.assertTrue(title and message, (language, result))


if __name__ == "__main__":
    unittest.main()
