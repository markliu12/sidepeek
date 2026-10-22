"""The fallback capture path: blank-frame detection and the grab gate.

``WindowCapture`` talks to Win32 through ``sidepeek.win32``, which these tests
mock out. The blank-frame heuristic (:meth:`WindowCapture._looks_blank`) only
reads ``self.bits`` / ``self.width`` / ``self.height``, so it is exercised
directly against a real ``ctypes`` buffer.
"""

import contextlib
import ctypes
import unittest
from unittest import mock

import sidepeek.capture as capture_mod
from sidepeek.capture import WindowCapture


def make_buffer(width: int, height: int, fill=(0, 0, 0)) -> bytes:
    """A BGRA frame where every pixel is ``fill``."""
    b, g, r = fill
    row = bytes((b, g, r, 255)) * width
    return row * height


def blank_capture(width=16, height=16, fill=(0, 0, 0)):
    """A ``WindowCapture`` whose buffer is ``fill`` for every pixel."""
    cap = WindowCapture(0)
    data = make_buffer(width, height, fill)
    buf = ctypes.create_string_buffer(data, len(data))
    cap.bits = ctypes.addressof(buf)
    cap.width = width
    cap.height = height
    return cap, buf


class LooksBlankTest(unittest.TestCase):
    def test_all_black_is_blank(self):
        cap, _buf = blank_capture(fill=(0, 0, 0))
        self.assertTrue(cap._looks_blank())

    def test_near_black_is_blank(self):
        # a couple of channels just above zero still read as blank
        cap, _buf = blank_capture(fill=(4, 4, 4))
        self.assertTrue(cap._looks_blank())

    def test_all_white_is_not_blank(self):
        cap, _buf = blank_capture(fill=(255, 255, 255))
        self.assertFalse(cap._looks_blank())

    def test_few_lit_pixels_is_not_blank(self):
        # the 2% threshold: a handful of bright pixels out of the grid must
        # flip the verdict (16x16 = 256 px, so >5 lit pixels clears the bar)
        cap, _buf = blank_capture(fill=(0, 0, 0))
        data = bytearray(make_buffer(16, 16, (0, 0, 0)))
        for i in range(8):                  # 8 pixels, well above 2%
            data[i * 4], data[i * 4 + 1], data[i * 4 + 2] = 255, 255, 255
        ctypes.memmove(cap.bits, bytes(data), len(data))
        self.assertFalse(cap._looks_blank())

    def test_one_lit_pixel_stays_blank(self):
        # a single stray bright pixel stays under the 2% threshold -> blank
        cap, _buf = blank_capture(fill=(0, 0, 0))
        data = bytearray(make_buffer(16, 16, (0, 0, 0)))
        data[0], data[1], data[2] = 255, 255, 255
        ctypes.memmove(cap.bits, bytes(data), len(data))
        self.assertTrue(cap._looks_blank())

    def test_no_bits_is_blank(self):
        cap = WindowCapture(0)
        cap.width = cap.height = 16
        self.assertTrue(cap._looks_blank())


class GrabTest(unittest.TestCase):
    """``grab`` short-circuits before touching GDI when the window is bad."""

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        w = capture_mod.win32
        self._patch(w, "is_window", lambda h: True)
        self._patch(w, "is_minimized", lambda h: False)
        self._patch(w, "window_rect", lambda h: (0, 0, 100, 100))

    def _patch(self, module, name, side_effect):
        self.stack.enter_context(mock.patch.object(module, name, side_effect=side_effect))

    def test_minimised_window_fails_without_capture(self):
        capture_mod.win32.is_minimized = mock.Mock(return_value=True)
        cap = WindowCapture(123)
        self.assertFalse(cap.grab())
        self.assertFalse(cap.valid)

    def test_vanished_window_fails(self):
        capture_mod.win32.is_window = mock.Mock(return_value=False)
        cap = WindowCapture(123)
        self.assertFalse(cap.grab())
        self.assertFalse(cap.valid)

    def test_tiny_window_fails(self):
        capture_mod.win32.window_rect = mock.Mock(return_value=(0, 0, 4, 4))
        cap = WindowCapture(123)
        self.assertFalse(cap.grab())
        self.assertFalse(cap.valid)


if __name__ == "__main__":
    unittest.main()
