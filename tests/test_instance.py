"""The single-instance lock and the ping that follows a refused start."""

import unittest
from unittest import mock

from sidepeek import instance, win32


class AcquireTest(unittest.TestCase):
    def setUp(self):
        instance._handle = None
        self.addCleanup(setattr, instance, "_handle", None)

    def _mutex(self, handle, last_error, close=True):
        """Pretend CreateMutexW returned ``handle`` and set ``last_error``."""
        patches = [
            mock.patch.object(win32.kernel32, "CreateMutexW", return_value=handle),
            mock.patch.object(instance.ctypes, "get_last_error", return_value=last_error),
        ]
        if close:
            patches.append(
                mock.patch.object(win32.kernel32, "CloseHandle", return_value=True)
            )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_first_instance_takes_the_lock(self):
        self._mutex(111, 0)
        self.assertTrue(instance.acquire())
        self.assertEqual(instance._handle, 111)

    def test_second_instance_is_refused(self):
        self._mutex(222, win32.ERROR_ALREADY_EXISTS)
        self.assertFalse(instance.acquire())
        self.assertIsNone(instance._handle)

    def test_unusable_mutex_falls_back_to_running(self):
        # refusing to start because a lock could not be created would be worse
        # than running without the guard
        self._mutex(None, 0)
        self.assertTrue(instance.acquire())

    def test_release_drops_the_handle(self):
        self._mutex(333, 0)
        instance.acquire()
        instance.release()
        self.assertIsNone(instance._handle)


class PingTest(unittest.TestCase):
    def test_no_window_means_no_ping(self):
        with mock.patch.object(win32.user32, "FindWindowW", return_value=None):
            self.assertFalse(instance.ping_running_instance("SidePeekOverlay"))

    def test_the_running_instance_gets_the_message(self):
        with mock.patch.object(win32.user32, "FindWindowW", return_value=4242):
            with mock.patch.object(
                win32.user32, "PostMessageW", return_value=1
            ) as post:
                self.assertTrue(instance.ping_running_instance("SidePeekOverlay"))
        self.assertEqual(post.call_args[0][1], instance.PING_MESSAGE)

    def test_ping_does_not_collide_with_the_other_private_messages(self):
        self.assertNotIn(
            instance.PING_MESSAGE,
            (win32.WM_APP + 1, win32.WM_APP + 2),
        )


if __name__ == "__main__":
    unittest.main()
