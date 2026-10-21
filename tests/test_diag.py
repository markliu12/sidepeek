"""The log file: content, rollover and the promise that it never raises."""

import contextlib
import io
import os
import tempfile
import unittest

from sidepeek import diag
from tests import LOG_DIR


class LogTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.path = os.path.join(self.dir, diag.LOG_NAME)
        os.environ["SIDEPEEK_LOG_DIR"] = self.dir
        self.addCleanup(os.environ.__setitem__, "SIDEPEEK_LOG_DIR", LOG_DIR)

    def _quiet_log(self, message):
        with contextlib.redirect_stdout(io.StringIO()):
            diag.log(message)

    def _content(self, path=None):
        with open(path or self.path, encoding="utf-8") as fh:
            return fh.read()

    def test_a_line_carries_a_timestamp_and_a_prefix(self):
        self._quiet_log("watching")
        content = self._content()
        self.assertIn("[sidepeek] watching", content)
        self.assertRegex(content, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")

    def test_lines_accumulate(self):
        self._quiet_log("one")
        self._quiet_log("two")
        content = self._content()
        self.assertLess(content.index("one"), content.index("two"))

    def test_the_directory_is_created_on_demand(self):
        nested = os.path.join(self.dir, "a", "b")
        os.environ["SIDEPEEK_LOG_DIR"] = nested
        self._quiet_log("hello")
        self.assertTrue(os.path.isfile(os.path.join(nested, diag.LOG_NAME)))

    def test_the_message_also_reaches_the_console(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            diag.log("visible")
        self.assertIn("visible", buffer.getvalue())

    def test_rollover_keeps_exactly_one_generation(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("x" * (diag.MAX_BYTES + 10))
        self._quiet_log("after rollover")
        self.assertTrue(os.path.isfile(self.path + ".1"))
        self.assertIn("after rollover", self._content())
        self.assertEqual(len(self._content(self.path + ".1")), diag.MAX_BYTES + 10)

    def test_small_file_is_not_rolled_over(self):
        self._quiet_log("tiny")
        self._quiet_log("again")
        self.assertFalse(os.path.exists(self.path + ".1"))

    def test_an_unusable_directory_does_not_raise(self):
        # point the log at a regular file: creating its "directory" must fail
        # with OSError, which logging has to swallow
        blocker = os.path.join(self.dir, "blocked")
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("x")
        os.environ["SIDEPEEK_LOG_DIR"] = blocker
        self._quiet_log("still fine")

    def test_log_path_follows_local_app_data(self):
        del os.environ["SIDEPEEK_LOG_DIR"]
        self.addCleanup(os.environ.__setitem__, "SIDEPEEK_LOG_DIR", LOG_DIR)
        os.environ["LOCALAPPDATA"] = self.dir
        self.addCleanup(os.environ.pop, "LOCALAPPDATA", None)
        self.assertEqual(
            diag.log_path(), os.path.join(self.dir, "SidePeek", diag.LOG_NAME)
        )


if __name__ == "__main__":
    unittest.main()
