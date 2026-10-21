"""The always-on-top peek window.

One window class hosts two interchangeable renderers:

``dwm``
    The window becomes a *live thumbnail host* via ``DwmRegisterThumbnail``.
    The desktop compositor draws the game into our client area, which costs
    essentially nothing and stays perfectly smooth even at 144 fps.

``capture``
    A timer grabs frames with ``PrintWindow`` and blits them every frame.
    Slower and CPU-hungry, but it still works for the handful of windows that
    refuse a DWM thumbnail.

The chrome (border, caption strip, drag, resize, click-to-focus, context menu)
is identical in both modes.
"""

from __future__ import annotations

import ctypes
import sys
import time
import traceback

from . import win32
from .capture import WindowCapture
from .config import Settings
from .watcher import Target
from .win32 import H, gdi32, user32

CLASS_NAME = "SidePeekOverlay"
TIMER_FRAME = 1
TIMER_POLL = 2

COLOR_ACCENT = win32.rgb(0x4C, 0x8D, 0xFF)
COLOR_BG = win32.rgb(0x0E, 0x11, 0x16)
COLOR_BAR = win32.rgb(0x16, 0x1A, 0x22)
COLOR_TEXT = win32.rgb(0xD7, 0xDE, 0xE9)
COLOR_SHADOW = win32.rgb(0x00, 0x00, 0x00)

MENU_ACTIVATE = 1001
MENU_CLEAR_TARGET = 1002
MENU_TOGGLE = 1003
MENU_QUIT = 1004


def _signed_short(value: int) -> int:
    return ctypes.c_short(value & 0xFFFF).value


def fit_rect(box: tuple[int, int, int, int], src_w: int, src_h: int) -> tuple[int, int, int, int]:
    """Letterbox ``src`` inside ``box``, preserving aspect ratio."""
    left, top, right, bottom = box
    box_w, box_h = max(1, right - left), max(1, bottom - top)
    if src_w <= 0 or src_h <= 0:
        return left, top, right, bottom
    scale = min(box_w / src_w, box_h / src_h)
    width, height = int(src_w * scale), int(src_h * scale)
    x = left + (box_w - width) // 2
    y = top + (box_h - height) // 2
    return x, y, x + width, y + height


class Overlay:
    """Frameless topmost window that mirrors another window's content."""

    _class_registered = False
    _instances: dict[int, "Overlay"] = {}
    _wndproc_ref = None

    def __init__(self, settings: Settings, config_path: str) -> None:
        self.settings = settings
        self.config_path = config_path

        self.hwnd = 0
        self.visible = False
        self.mode = ""
        self.target: Target | None = None
        self.source_size = (0, 0)
        self.thumb = None
        self.capture: WindowCapture | None = None
        self.fallback_reason = ""

        self.on_check = lambda: None
        self.on_quit = lambda: None
        self.on_activate = lambda: None
        self.on_toggle_pause = lambda: None
        self.on_clear_target = lambda: None
        self.on_lock = lambda: None

        self._width = settings.width
        self._height = settings.height
        self._drag_active = False
        self._drag_origin = (0, 0)
        self._drag_start = (0, 0)
        self._drag_moved = False
        self._shown_at = 0.0

        self._brush_accent = 0
        self._brush_bg = 0
        self._brush_bar = 0
        self._font = 0
        self._cursor_arrow = 0
        self._cursor_size = 0

    # ------------------------------------------------------------------
    # window lifecycle
    # ------------------------------------------------------------------
    def create(self) -> int:
        win32.dpi_aware()
        self._register_class()

        style = win32.WS_POPUP
        exstyle = win32.WS_EX_TOPMOST | win32.WS_EX_NOACTIVATE
        exstyle |= (
            win32.WS_EX_APPWINDOW if self.settings.show_in_taskbar
            else win32.WS_EX_TOOLWINDOW
        )

        hwnd = user32.CreateWindowExW(
            exstyle, CLASS_NAME, "SidePeek", style,
            100, 100, self._width, self._height,
            0, 0, self._hinstance(), None,
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        self.hwnd = hwnd
        Overlay._instances[hwnd] = self

        self._brush_accent = gdi32.CreateSolidBrush(COLOR_ACCENT)
        self._brush_bg = gdi32.CreateSolidBrush(COLOR_BG)
        self._brush_bar = gdi32.CreateSolidBrush(COLOR_BAR)
        self._font = gdi32.CreateFontW(
            -13, 0, 0, 0, win32.FW_SEMIBOLD, 0, 0, 0,
            win32.DEFAULT_CHARSET, 0, 0, win32.CLEARTYPE_QUALITY, 0, "Segoe UI",
        )
        self._cursor_arrow = user32.LoadCursorW(0, H(win32.IDC_ARROW))
        self._cursor_size = user32.LoadCursorW(0, H(win32.IDC_SIZENWSE))

        self._apply_round_corners()
        return hwnd

    def _hinstance(self) -> int:
        return win32.kernel32.GetModuleHandleW(None)

    def _register_class(self) -> None:
        if Overlay._class_registered:
            return
        if Overlay._wndproc_ref is None:
            Overlay._wndproc_ref = win32.WNDPROC(Overlay._dispatch)
        wc = win32.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(win32.WNDCLASSEXW)
        wc.style = win32.CS_HREDRAW | win32.CS_VREDRAW | win32.CS_DROPSHADOW
        wc.lpfnWndProc = Overlay._wndproc_ref
        wc.hInstance = self._hinstance()
        wc.hCursor = user32.LoadCursorW(0, H(win32.IDC_ARROW))
        wc.lpszClassName = CLASS_NAME
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err not in (0, 1410):        # 1410 = class already exists
                raise ctypes.WinError(err)
        Overlay._class_registered = True

    @staticmethod
    def _dispatch(hwnd, msg, wparam, lparam) -> int:
        inst = Overlay._instances.get(hwnd)
        if inst is None:
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        try:
            return inst._wndproc(hwnd, msg, wparam, lparam)
        except Exception:                    # never kill the message loop
            traceback.print_exc()
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ------------------------------------------------------------------
    # public api
    # ------------------------------------------------------------------
    def show_target(self, target: Target) -> None:
        if self.target and self.target.hwnd == target.hwnd and self.visible:
            return
        self._detach()
        self.target = target
        self._attach(target)

        if not self.visible:
            self._place()
            user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)
            user32.SetWindowPos(
                self.hwnd, win32.HWND_TOPMOST, 0, 0, 0, 0,
                win32.SWP_NOMOVE | win32.SWP_NOSIZE | win32.SWP_NOACTIVATE,
            )
            self.visible = True
            self._shown_at = time.time()
            if self.mode == "capture":
                self._start_frame_timer()

        self._apply_layout()
        user32.InvalidateRect(self.hwnd, None, False)

    def hide(self) -> None:
        if not self.visible:
            return
        self._stop_frame_timer()
        self._detach()
        user32.ShowWindow(self.hwnd, 0)
        self.visible = False
        self.target = None

    def destroy(self) -> None:
        if self.hwnd:
            user32.KillTimer(self.hwnd, TIMER_FRAME)
            user32.DestroyWindow(self.hwnd)
            self.hwnd = 0
            self.visible = False

    def refresh(self) -> None:
        """Re-read settings after the config file changed."""
        if not self.hwnd:
            return
        self._width = self.settings.width
        self._height = self.settings.height
        self._apply_round_corners()
        self._place()
        self._apply_layout()
        user32.InvalidateRect(self.hwnd, None, False)

    def toggle_pause(self) -> bool:
        self.on_toggle_pause()
        return True

    # ------------------------------------------------------------------
    # renderer selection
    # ------------------------------------------------------------------
    def _attach(self, target: Target) -> None:
        backend = self.settings.backend
        if backend in ("auto", "dwm") and self._attach_dwm(target):
            return
        self._attach_capture(target)

    def _attach_dwm(self, target: Target) -> bool:
        if win32.dwmapi is None or not win32.composition_enabled():
            self.fallback_reason = "DWM composition unavailable"
            return False
        thumb = H()
        hr = win32.dwmapi.DwmRegisterThumbnail(
            self.hwnd, target.hwnd, ctypes.byref(thumb)
        )
        if hr != 0 or not thumb:
            self.fallback_reason = f"DwmRegisterThumbnail failed (hr=0x{hr & 0xFFFFFFFF:08X})"
            return False

        size = win32.SIZE()
        if win32.dwmapi.DwmQueryThumbnailSourceSize(thumb, ctypes.byref(size)):
            size.cx, size.cy = 0, 0
        if size.cx <= 0 or size.cy <= 0:
            win32.dwmapi.DwmUnregisterThumbnail(thumb)
            self.fallback_reason = "thumbnail source size unknown"
            return False

        self.thumb = thumb
        self.source_size = (size.cx, size.cy)
        self.mode = "dwm"
        return True

    def _attach_capture(self, target: Target) -> None:
        self.capture = WindowCapture(target.hwnd)
        if self.capture.grab():
            self.source_size = (self.capture.width, self.capture.height)
        else:
            self.source_size = (0, 0)
        self.mode = "capture"

    def _detach(self) -> None:
        self._stop_frame_timer()
        if self.thumb is not None and win32.dwmapi is not None:
            win32.dwmapi.DwmUnregisterThumbnail(self.thumb)
        self.thumb = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.mode = ""

    # ------------------------------------------------------------------
    # geometry
    # ------------------------------------------------------------------
    def _place(self) -> None:
        s = self.settings
        left, top, right, bottom = win32.monitor_work_area(
            self.target.hwnd if self.target else 0
        )
        avail_w, avail_h = right - left, bottom - top

        if s.anchor == "custom":
            x, y = s.pos
        else:
            x = left + s.margin if "left" in s.anchor else right - self._width - s.margin
            if "top" in s.anchor:
                y = top + s.margin
            elif "bottom" in s.anchor:
                y = bottom - self._height - s.margin
            else:
                y = top + (avail_h - self._height) // 2

        x = max(left, min(x, right - self._width))
        y = max(top, min(y, bottom - self._height))
        user32.SetWindowPos(
            self.hwnd, win32.HWND_TOPMOST, x, y, self._width, self._height,
            win32.SWP_NOACTIVATE | win32.SWP_NOZORDER,
        )

    def _content_box(self) -> tuple[int, int, int, int]:
        pad = self.settings.padding
        cap = self._caption_height()
        return (pad, pad, self._width - pad, self._height - pad - cap)

    def _caption_height(self) -> int:
        return 22 if self.settings.caption else 0

    def _apply_layout(self) -> None:
        if self.mode == "dwm" and self.thumb is not None:
            self._update_dwm()

    def _update_dwm(self) -> None:
        if self.thumb is None or win32.dwmapi is None:
            return
        # the game may have been resized (or switched resolution) meanwhile
        size = win32.SIZE()
        if win32.dwmapi.DwmQueryThumbnailSourceSize(self.thumb, ctypes.byref(size)) == 0:
            if size.cx > 0 and size.cy > 0:
                self.source_size = (size.cx, size.cy)
        dest = fit_rect(self._content_box(), *self.source_size)
        props = win32.DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = (
            win32.DWM_TNP_RECTDESTINATION
            | win32.DWM_TNP_VISIBLE
            | win32.DWM_TNP_OPACITY
            | win32.DWM_TNP_SOURCECLIENTAREAONLY
        )
        props.rcDestination.left = dest[0]
        props.rcDestination.top = dest[1]
        props.rcDestination.right = dest[2]
        props.rcDestination.bottom = dest[3]
        props.opacity = int(self.settings.opacity * 255 / 100)
        props.fVisible = True
        props.fSourceClientAreaOnly = True
        win32.dwmapi.DwmUpdateThumbnailProperties(self.thumb, ctypes.byref(props))

    def _apply_round_corners(self) -> None:
        """Prefer DWM's own rounded corners; fall back to a window region."""
        build = sys.getwindowsversion() if hasattr(sys, "getwindowsversion") else None
        if win32.dwmapi is not None and build and build.build >= 22000:
            pref = ctypes.c_int(win32.DWMWCP_ROUND)
            if win32.dwmapi.DwmSetWindowAttribute(
                self.hwnd, win32.DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(pref), ctypes.sizeof(pref),
            ) == 0:
                return
        rgn = gdi32.CreateRoundRectRgn(
            0, 0, self._width + 1, self._height + 1, 12, 12
        )
        if rgn:
            user32.SetWindowRgn(self.hwnd, rgn, True)

    # ------------------------------------------------------------------
    # painting
    # ------------------------------------------------------------------
    def _fill(self, hdc, rect, brush) -> None:
        rc = win32.wt.RECT(*rect)
        user32.FillRect(hdc, ctypes.byref(rc), brush)

    def _paint(self) -> None:
        hdc, ps = self._begin_paint()
        if not hdc:
            return
        try:
            if self.mode == "capture":
                self._paint_capture(hdc)
            else:
                self._paint_plain(hdc)
        finally:
            user32.EndPaint(self.hwnd, ctypes.byref(ps))

    def _begin_paint(self):
        ps = win32.PAINTSTRUCT()
        hdc = user32.BeginPaint(self.hwnd, ctypes.byref(ps))
        return hdc, ps

    def _paint_plain(self, hdc) -> None:
        w, h = self._width, self._height
        self._fill(hdc, (0, 0, w, h), self._brush_accent)
        self._fill(hdc, (1, 1, w - 1, h - 1), self._brush_bg)
        self._paint_caption(hdc)

    def _paint_capture(self, hdc) -> None:
        w, h = self._width, self._height
        mem_dc = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
        old = gdi32.SelectObject(mem_dc, bitmap)
        try:
            self._fill(mem_dc, (0, 0, w, h), self._brush_accent)
            self._fill(mem_dc, (1, 1, w - 1, h - 1), self._brush_bg)

            dest = fit_rect(self._content_box(), *self.source_size)
            if self.capture and self.capture.valid:
                gdi32.SetStretchBltMode(mem_dc, win32.HALFTONE)
                gdi32.SetBrushOrgEx(mem_dc, 0, 0, None)
                gdi32.StretchBlt(
                    mem_dc, dest[0], dest[1], dest[2] - dest[0], dest[3] - dest[1],
                    self.capture.hdc, 0, 0, self.capture.width, self.capture.height,
                    win32.SRCCOPY,
                )
            else:
                self._fill(mem_dc, dest, self._brush_bar)

            self._paint_caption(mem_dc)
            gdi32.BitBlt(hdc, 0, 0, w, h, mem_dc, 0, 0, win32.SRCCOPY)
        finally:
            gdi32.SelectObject(mem_dc, old)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)

    def _paint_caption(self, hdc) -> None:
        cap = self._caption_height()
        if not cap:
            return
        w, h = self._width, self._height
        pad = self.settings.padding
        top = h - pad - cap
        self._fill(hdc, (pad, top, w - pad, h - pad), self._brush_bar)

        old_font = gdi32.SelectObject(hdc, self._font)
        try:
            gdi32.SetBkMode(hdc, win32.TRANSPARENT)
            flags = win32.DT_LEFT | win32.DT_SINGLELINE | win32.DT_VCENTER | win32.DT_NOPREFIX
            name = self.target.display_name if self.target else "SidePeek"
            if self.mode == "capture" and not (self.capture and self.capture.valid):
                name = f"{name}  ·  等待画面"

            for text, align in (
                (name, win32.DT_LEFT),
                (self._elapsed_text(), win32.DT_RIGHT),
            ):
                rc = win32.wt.RECT(pad + 8, top, w - pad - 8, h - pad)
                gdi32.SetTextColor(hdc, COLOR_SHADOW)
                shifted = win32.wt.RECT(rc.left + 1, rc.top + 1, rc.right + 1, rc.bottom + 1)
                user32.DrawTextW(hdc, text, -1, ctypes.byref(shifted), flags | align)
                gdi32.SetTextColor(hdc, COLOR_TEXT)
                user32.DrawTextW(hdc, text, -1, ctypes.byref(rc), flags | align)
        finally:
            gdi32.SelectObject(hdc, old_font)

    def _elapsed_text(self) -> str:
        if not self._shown_at:
            return ""
        seconds = max(0, int(time.time() - self._shown_at))
        return f"后台 {seconds // 60}:{seconds % 60:02d}"

    # ------------------------------------------------------------------
    # capture timer
    # ------------------------------------------------------------------
    def start_polling(self, interval_ms: int) -> None:
        if self.hwnd:
            user32.SetTimer(self.hwnd, TIMER_POLL, max(80, interval_ms), None)

    def _start_frame_timer(self) -> None:
        if not self.hwnd:
            return
        interval = max(16, int(1000 / max(1, self.settings.fps)))
        user32.SetTimer(self.hwnd, TIMER_FRAME, interval, None)

    def _stop_frame_timer(self) -> None:
        if self.hwnd:
            user32.KillTimer(self.hwnd, TIMER_FRAME)

    def _on_frame_timer(self) -> None:
        if self.mode != "capture" or not self.capture or not self.visible:
            return
        if self.capture.grab():
            self.source_size = (self.capture.width, self.capture.height)
        user32.InvalidateRect(self.hwnd, None, False)

    # ------------------------------------------------------------------
    # input handling
    # ------------------------------------------------------------------
    def _hit_corner(self, client_pt) -> bool:
        x, y = client_pt
        size = 18
        return (
            x >= self._width - size and y >= self._height - size
            and self._width > size * 3 and self._height > size * 3
        )

    def _start_drag(self) -> None:
        pt = win32.wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        rect = win32.window_rect(self.hwnd)
        self._drag_active = True
        self._drag_moved = False
        self._drag_start = (pt.x, pt.y)
        self._drag_origin = (rect[0], rect[1]) if rect else (0, 0)
        user32.SetCapture(self.hwnd)

    def _on_mouse_move(self, lparam) -> None:
        if not self._drag_active:
            pt = win32.wt.POINT(_signed_short(lparam), _signed_short(lparam >> 16))
            user32.SetCursor(self._cursor_size if self._hit_corner((pt.x, pt.y))
                             else self._cursor_arrow)
            return
        pos = win32.wt.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        dx = pos.x - self._drag_start[0]
        dy = pos.y - self._drag_start[1]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag_moved = True
        user32.SetWindowPos(
            self.hwnd, win32.HWND_TOPMOST,
            self._drag_origin[0] + dx, self._drag_origin[1] + dy, 0, 0,
            win32.SWP_NOSIZE | win32.SWP_NOACTIVATE | win32.SWP_NOZORDER,
        )

    def _end_drag(self) -> None:
        if not self._drag_active:
            return
        self._drag_active = False
        user32.ReleaseCapture()
        if self._drag_moved:
            rect = win32.window_rect(self.hwnd)
            if rect:
                self.settings.anchor = "custom"
                self.settings.pos = (rect[0], rect[1])
        elif self.settings.click_to_focus:
            self.on_activate()

    def _open_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(menu, win32.MF_STRING, MENU_ACTIVATE, "回到游戏窗口")
            user32.AppendMenuW(menu, win32.MF_STRING, MENU_CLEAR_TARGET, "清除当前目标")
            user32.AppendMenuW(menu, win32.MF_STRING, MENU_TOGGLE, "暂停 / 恢复监视")
            user32.AppendMenuW(menu, win32.MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, win32.MF_STRING, MENU_QUIT, "退出 SidePeek")

            pt = win32.wt.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            win32.force_foreground(self.hwnd)
            cmd = user32.TrackPopupMenu(
                menu,
                win32.TPM_RETURNCMD | win32.TPM_RIGHTBUTTON | win32.TPM_NONOTIFY,
                pt.x, pt.y, 0, self.hwnd, None,
            )
        finally:
            user32.DestroyMenu(menu)

        if cmd == MENU_ACTIVATE:
            self.on_activate()
        elif cmd == MENU_CLEAR_TARGET:
            self.on_clear_target()
        elif cmd == MENU_TOGGLE:
            self.on_toggle_pause()
        elif cmd == MENU_QUIT:
            self.on_quit()

    # ------------------------------------------------------------------
    # message pump
    # ------------------------------------------------------------------
    def _wndproc(self, hwnd, msg, wparam, lparam) -> int:
        if msg == win32.WM_PAINT:
            self._paint()
            return 0
        if msg == win32.WM_ERASEBKGND:
            return 1
        if msg == win32.WM_TIMER:
            if wparam == TIMER_FRAME:
                self._on_frame_timer()
                if self.settings.caption:
                    user32.InvalidateRect(hwnd, None, False)
            elif wparam == TIMER_POLL:
                self.on_check()
            return 0
        if msg == win32.WM_APP + 1:          # foreground changed
            self.on_check()
            return 0
        if msg == win32.WM_NCHITTEST:
            pt = win32.wt.POINT(_signed_short(lparam), _signed_short(lparam >> 16))
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            return win32.HTBOTTOMRIGHT if self._hit_corner((pt.x, pt.y)) else win32.HTCLIENT
        if msg == win32.WM_LBUTTONDOWN:
            self._start_drag()
            return 0
        if msg == win32.WM_LBUTTONUP:
            self._end_drag()
            return 0
        if msg == win32.WM_MOUSEMOVE:
            self._on_mouse_move(lparam)
            return 0
        if msg == win32.WM_RBUTTONUP:
            self._open_menu()
            return 0
        if msg == win32.WM_SIZE:
            rect = win32.client_rect(hwnd)
            self._width = max(1, rect[2] - rect[0])
            self._height = max(1, rect[3] - rect[1])
            self.settings.width = self._width
            self.settings.height = self._height
            if self.settings.anchor != "custom":
                self._place()
            self._apply_layout()
            user32.InvalidateRect(hwnd, None, False)
            return 0
        if msg == win32.WM_DISPLAYCHANGE:
            if self.settings.anchor != "custom":
                self._place()
            return 0
        if msg == win32.WM_HOTKEY:
            self._on_hotkey(int(wparam))
            return 0
        if msg == win32.WM_CLOSE:
            self.on_quit()
            return 0
        if msg == win32.WM_DESTROY:
            self._cleanup()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == 1:
            self.on_toggle_pause()
        elif hotkey_id == 2:
            self.on_lock()
        elif hotkey_id == 3:
            self.on_quit()
        else:
            self.on_check()

    def _cleanup(self) -> None:
        self._detach()
        Overlay._instances.pop(self.hwnd, None)
        for brush in (self._brush_accent, self._brush_bg, self._brush_bar):
            if brush:
                gdi32.DeleteObject(brush)
        if self._font:
            gdi32.DeleteObject(self._font)
        self._brush_accent = self._brush_bg = self._brush_bar = self._font = 0
