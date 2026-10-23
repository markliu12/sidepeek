"""Config loading, merging and the runtime write-back rules."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from sidepeek.config import Settings, load, save_runtime


def _quiet_load(path):
    with contextlib.redirect_stdout(io.StringIO()):
        return load(path)


class LoadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "config.json")

    def _write(self, payload):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def _read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_missing_file_is_created_with_defaults(self):
        settings, path = _quiet_load(self.path)
        self.assertEqual(path, self.path)
        self.assertTrue(os.path.isfile(self.path))
        self.assertEqual((settings.width, settings.height), (492, 304))
        self.assertTrue(self._read()["peek"]["caption"])

    def test_partial_file_keeps_other_defaults(self):
        self._write({"peek": {"width": 600}})
        settings, _ = _quiet_load(self.path)
        self.assertEqual(settings.width, 600)
        self.assertEqual(settings.height, 304)          # untouched default
        self.assertEqual(settings.backend, "auto")
        self.assertTrue(settings.cs2_round_notifications)

    def test_unknown_keys_are_ignored(self):
        self._write({"peek": {"width": 320, "totally_new_option": True}, "extra": 1})
        settings, _ = _quiet_load(self.path)
        self.assertEqual(settings.width, 320)

    def test_values_are_clamped(self):
        self._write({"peek": {"width": 10, "height": 5, "fps": 999,
                              "opacity": 1, "poll_ms": 5}})
        settings, _ = _quiet_load(self.path)
        self.assertEqual((settings.width, settings.height), (160, 90))
        self.assertEqual(settings.fps, 60)
        self.assertEqual(settings.opacity, 10)
        self.assertEqual(settings.poll_ms, 80)

    def test_targets_and_ignore_are_lowercased(self):
        self._write({"peek": {"targets": ["CS2.EXE"], "ignore": ["Chrome.exe"]}})
        settings, _ = _quiet_load(self.path)
        self.assertEqual(settings.targets, ("cs2.exe",))
        self.assertEqual(settings.ignore, ("chrome.exe",))

    def test_broken_json_falls_back_to_defaults(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        with contextlib.redirect_stdout(io.StringIO()):
            settings, _ = load(self.path)
        self.assertEqual(settings.width, 492)


class SaveRuntimeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "config.json")
        _quiet_load(self.path)

    def test_cs2_round_notification_toggle_persists(self):
        settings, _ = _quiet_load(self.path)
        settings.cs2_round_notifications = False
        save_runtime(self.path, settings)
        with open(self.path, encoding="utf-8") as fh:
            self.assertFalse(json.load(fh)["peek"]["cs2_round_notifications"])

    def _read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_layout_is_persisted(self):
        save_runtime(self.path, Settings(width=700, height=400,
                                         anchor="custom", pos=(11, 22)))
        peek = self._read()["peek"]
        self.assertEqual((peek["width"], peek["height"]), (700, 400))
        self.assertEqual(peek["anchor"], "custom")
        self.assertEqual(peek["pos"], [11, 22])

    def test_fit_aspect_is_persisted(self):
        # dragging the resize handle turns it off; that has to survive a restart
        save_runtime(self.path, Settings(fit_aspect=False))
        self.assertFalse(self._read()["peek"]["fit_aspect"])

    def test_skipped_fields_are_left_untouched(self):
        # a one-off `--width 700` must not become the saved width
        save_runtime(self.path, Settings(width=700, height=400), skip=("width",))
        peek = self._read()["peek"]
        self.assertEqual(peek["width"], 492)
        self.assertEqual(peek["height"], 400)

    def test_unrelated_keys_survive(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"peek": {"width": 480}, "my_notes": {"a": 1}}, fh)
        save_runtime(self.path, Settings(width=500, height=300))
        data = self._read()
        self.assertEqual(data["my_notes"], {"a": 1})
        self.assertEqual(data["peek"]["width"], 500)


class NotificationLanguageTest(unittest.TestCase):
    """``notification_language`` accepts locale spellings but stores one value."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "config.json")

    def _load_with(self, value):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"peek": {"notification_language": value}}, fh)
        return _quiet_load(self.path)[0]

    def test_defaults_to_auto(self):
        settings, _ = _quiet_load(self.path)
        self.assertEqual(settings.notification_language, "auto")

    def test_accepts_supported_values(self):
        for value in ("auto", "en", "zh-CN", "zh-TW"):
            self.assertEqual(self._load_with(value).notification_language, value, value)

    def test_locale_spellings_are_normalised(self):
        self.assertEqual(self._load_with("en-US").notification_language, "en")
        self.assertEqual(self._load_with("zh-Hant").notification_language, "zh-TW")
        self.assertEqual(self._load_with("zh-Hans-CN").notification_language, "zh-CN")

    def test_unknown_value_falls_back_to_auto(self):
        self.assertEqual(self._load_with("esperanto").notification_language, "auto")
        self.assertEqual(self._load_with(42).notification_language, "auto")

    def test_persisted_at_runtime(self):
        save_runtime(self.path, Settings(notification_language="en"))
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["peek"]["notification_language"], "en")


if __name__ == "__main__":
    unittest.main()
