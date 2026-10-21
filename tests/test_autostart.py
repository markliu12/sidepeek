"""Run-at-login: the stored command line and the registry round trip.

Every registry call is mocked - a test run must not add an autostart entry to
the machine that executes it.
"""

import unittest
from unittest import mock

from sidepeek import autostart


class LaunchCommandTest(unittest.TestCase):
    def test_frozen_build_points_at_the_executable(self):
        with mock.patch.object(autostart.sys, "frozen", True, create=True), \
                mock.patch.object(autostart.sys, "executable", r"C:\Games\SidePeek.exe"):
            self.assertEqual(autostart.launch_command(), r'"C:\Games\SidePeek.exe"')

    def test_source_run_prefers_pythonw(self):
        with mock.patch.object(autostart.sys, "executable", r"C:\Py\python.exe"), \
                mock.patch.object(autostart.os.path, "isfile", return_value=True), \
                mock.patch.object(autostart, "_source_dir", return_value=r"C:\src"):
            command = autostart.launch_command()
        self.assertIn("pythonw.exe", command)
        self.assertIn("run.py", command)
        self.assertFalse(command.startswith("python"), "the path must be quoted")

    def test_pythonw_is_skipped_when_it_is_missing(self):
        with mock.patch.object(autostart.sys, "executable", r"C:\Py\python.exe"), \
                mock.patch.object(autostart.os.path, "isfile", return_value=False):
            self.assertEqual(autostart._windowless_python(), r"C:\Py\python.exe")

    def test_both_halves_of_the_command_are_quoted(self):
        with mock.patch.object(autostart.sys, "executable", r"C:\Py python\python.exe"), \
                mock.patch.object(autostart.os.path, "isfile", return_value=False), \
                mock.patch.object(autostart, "_source_dir", return_value=r"C:\my src"):
            command = autostart.launch_command()
        self.assertTrue(command.count('"') == 4, command)


class RegistryTest(unittest.TestCase):
    def test_is_enabled_true_when_the_value_exists(self):
        key = mock.MagicMock()
        with mock.patch.object(autostart.winreg, "OpenKey", return_value=key), \
                mock.patch.object(autostart.winreg, "QueryValueEx",
                                  return_value=('"C:\\x.exe"', 1)):
            self.assertTrue(autostart.is_enabled())

    def test_missing_key_means_disabled(self):
        with mock.patch.object(autostart.winreg, "OpenKey",
                               side_effect=FileNotFoundError):
            self.assertFalse(autostart.is_enabled())

    def test_enable_writes_the_launch_command(self):
        key = mock.MagicMock()
        with mock.patch.object(autostart.winreg, "CreateKey", return_value=key), \
                mock.patch.object(autostart.winreg, "SetValueEx") as set_value, \
                mock.patch.object(autostart, "launch_command", return_value='"C:\\x.exe"'):
            self.assertTrue(autostart.enable())
        set_value.assert_called_once()
        args = set_value.call_args[0]
        self.assertEqual(args[1], autostart.VALUE_NAME)
        self.assertEqual(args[3], autostart.winreg.REG_SZ)
        self.assertEqual(args[4], '"C:\\x.exe"')

    def test_enable_reports_a_refused_write(self):
        with mock.patch.object(autostart.winreg, "CreateKey",
                               side_effect=PermissionError):
            self.assertFalse(autostart.enable())

    def test_disable_removes_the_value(self):
        key = mock.MagicMock()
        with mock.patch.object(autostart.winreg, "OpenKey", return_value=key), \
                mock.patch.object(autostart.winreg, "DeleteValue") as delete:
            self.assertTrue(autostart.disable())
        delete.assert_called_once()

    def test_disable_is_idempotent(self):
        with mock.patch.object(autostart.winreg, "OpenKey",
                               side_effect=FileNotFoundError):
            self.assertTrue(autostart.disable())

    def test_toggle_turns_it_on(self):
        with mock.patch.object(autostart, "is_enabled", side_effect=[False, True]), \
                mock.patch.object(autostart, "enable", return_value=True) as enable:
            self.assertTrue(autostart.toggle())
        enable.assert_called_once()

    def test_toggle_turns_it_off(self):
        with mock.patch.object(autostart, "is_enabled", side_effect=[True, False]), \
                mock.patch.object(autostart, "disable", return_value=True) as disable:
            self.assertFalse(autostart.toggle())
        disable.assert_called_once()


if __name__ == "__main__":
    unittest.main()
