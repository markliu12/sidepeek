"""Frame grabbing for the fallback backend.

``PrintWindow`` asks a window to render itself into a device context. With
``PW_RENDERFULLCONTENT`` it goes through the DWM redirection surface, which is
what makes borderless-windowed games capturable even while they are in the
background.

For a handful of titles ``PrintWindow`` returns success but paints nothing.
:meth:`WindowCapture.grab` therefore validates the result (is it all black?)
and falls back to a plain ``BitBlt`` from the window DC before giving up.
"""

from __future__ import annotations

import ctypes

from . import win32
from .win32 import gdi32, user32

PUBLIC_FLAGS = (
    win32.PW_RENDERFULLCONTENT,
    0,
)
PUBLIC_METHODS = ("printwindow-full", "printwindow", "bitblt")


class WindowCapture:
    """Grabs frames of a single window into a reusable DIB section."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self.hdc: int | None = None
        self.bitmap: int | None = None
        self.old_bitmap: int | None = None
        self.bits: int | None = None
        self.width = 0
        self.height = 0
        self.valid = False
        self.method = ""

    # -- resources ---------------------------------------------------------
    def _ensure_buffers(self, width: int, height: int) -> None:
        if self.hdc and width == self.width and height == self.height:
            return
        self.release()

        screen_dc = user32.GetDC(0)
        try:
            self.hdc = gdi32.CreateCompatibleDC(screen_dc)
        finally:
            user32.ReleaseDC(0, screen_dc)

        bmi = win32.BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(win32.BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height          # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0           # BI_RGB

        bits = ctypes.c_void_p()
        self.bitmap = gdi32.CreateDIBSection(
            self.hdc, ctypes.byref(bmi), win32.DIB_RGB_COLORS,
            ctypes.byref(bits), None, 0,
        )
        if not self.bitmap:
            self.release()
            return
        self.bits = bits.value
        self.old_bitmap = gdi32.SelectObject(self.hdc, self.bitmap)
        self.width = width
        self.height = height

    def release(self) -> None:
        if self.hdc and self.old_bitmap:
            gdi32.SelectObject(self.hdc, self.old_bitmap)
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
        if self.hdc:
            gdi32.DeleteDC(self.hdc)
        self.hdc = self.bitmap = self.old_bitmap = self.bits = None
        self.width = self.height = 0
        self.valid = False

    # -- capture -----------------------------------------------------------
    def grab(self) -> bool:
        """Capture one frame. Returns ``True`` when the buffer holds an image."""
        if not win32.is_window(self.hwnd) or win32.is_minimized(self.hwnd):
            self.valid = False
            return False

        rect = win32.window_rect(self.hwnd)
        if not rect:
            self.valid = False
            return False
        left, top, right, bottom = rect
        width, height = right - left, bottom - top
        if width < 8 or height < 8:
            self.valid = False
            return False

        self._ensure_buffers(width, height)
        if not self.hdc:
            self.valid = False
            return False

        for flag, name in zip(PUBLIC_FLAGS, PUBLIC_METHODS):
            if user32.PrintWindow(self.hwnd, self.hdc, flag):
                if not self._looks_blank():
                    self.method = name
                    self.valid = True
                    return True

        self._blit_from_window_dc(width, height)
        if not self._looks_blank():
            self.method = "bitblt"
            self.valid = True
            return True

        self.valid = False
        return False

    def _blit_from_window_dc(self, width: int, height: int) -> None:
        src = user32.GetWindowDC(self.hwnd)
        if not src:
            return
        try:
            gdi32.BitBlt(self.hdc, 0, 0, width, height, src, 0, 0, win32.SRCCOPY)
        finally:
            user32.ReleaseDC(self.hwnd, src)

    def _looks_blank(self) -> bool:
        """Cheap sanity check: sample a grid of pixels and look for light."""
        if not self.bits:
            return True
        try:
            data = ctypes.string_at(self.bits, self.width * self.height * 4)
        except (ValueError, OSError):
            return True

        px = self.width * self.height
        step = max(1, px // 1024)
        lit = 0
        seen = 0
        for i in range(0, px, step):
            off = i * 4
            b, g, r = data[off], data[off + 1], data[off + 2]
            seen += 1
            if r + g + b > 18:
                lit += 1
        return seen == 0 or (lit / seen) < 0.02

    # -- debugging ---------------------------------------------------------
    def pixel_bytes(self) -> bytes:
        if not self.bits:
            return b""
        return ctypes.string_at(self.bits, self.width * self.height * 4)
