"""Small native Windows dialog for configuring Bark notifications."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from typing import Callable

from . import win32
from .config import Settings

_CLASS = "SidePeekBarkSettings"
_WM_COMMAND = 0x0111
_WS_TABSTOP = 0x00010000
_ES_AUTOHSCROLL = 0x0080
_ES_PASSWORD = 0x0020
_BS_DEFPUSHBUTTON = 0x00000001
_ID_KEY = 1
_ID_SAVE = 2
_ID_TEST = 3
_ID_CLOSE = 4
_ID_STATUS = 5

_instances: dict[int, "_Dialog"] = {}
_wndproc_ref = None
_registered = False


class _Dialog:
    def __init__(self, settings: Settings, save: Callable[[], None], test: Callable[[], None]):
        self.settings = settings
        self.save = save
        self.test = test
        self.hwnd = 0
        self.key_edit = 0
        self.status = 0

    def handle(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == _WM_COMMAND:
            command = wparam & 0xFFFF
            if command in (_ID_SAVE, _ID_TEST):
                key = ctypes.create_unicode_buffer(512)
                win32.user32.GetWindowTextW(self.key_edit, key, len(key))
                self.settings.bark_device_key = key.value.strip()
                self.save()
                if command == _ID_SAVE:
                    win32.user32.SetWindowTextW(self.status, "已保存。之后 SidePeek 会自动发送回合提醒。")
                elif self.settings.bark_device_key:
                    win32.user32.SetWindowTextW(self.status, "已保存，正在发送测试提醒……")
                    self.test()
                else:
                    win32.user32.SetWindowTextW(self.status, "请先粘贴 Bark Key。")
                return 0
            if command == _ID_CLOSE:
                win32.user32.DestroyWindow(hwnd)
                return 0
        if message == win32.WM_CLOSE:
            win32.user32.DestroyWindow(hwnd)
            return 0
        if message == win32.WM_DESTROY:
            _instances.pop(hwnd, None)
            return 0
        return win32.user32.DefWindowProcW(hwnd, message, wparam, lparam)


def _wndproc(hwnd, message, wparam, lparam):
    dialog = _instances.get(hwnd)
    if dialog:
        try:
            return dialog.handle(hwnd, message, wparam, lparam)
        except Exception:
            return win32.user32.DefWindowProcW(hwnd, message, wparam, lparam)
    return win32.user32.DefWindowProcW(hwnd, message, wparam, lparam)


def _create_control(parent: int, class_name: str, text: str, style: int,
                    x: int, y: int, width: int, height: int, control_id: int = 0) -> int:
    return win32.user32.CreateWindowExW(
        0, class_name, text, style | win32.WS_CHILD | win32.WS_VISIBLE,
        x, y, width, height, parent, control_id or None,
        win32.kernel32.GetModuleHandleW(None), None,
    )


def show_bark_settings(owner: int, settings: Settings,
                       save: Callable[[], None], test: Callable[[], None]) -> None:
    """Show a modal native dialog; the Bark Key is stored in the normal config."""
    global _registered, _wndproc_ref
    if not _registered:
        _wndproc_ref = win32.WNDPROC(_wndproc)
        wc = win32.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(wc)
        wc.lpfnWndProc = _wndproc_ref
        wc.hInstance = win32.kernel32.GetModuleHandleW(None)
        wc.hCursor = win32.user32.LoadCursorW(0, win32.H(win32.IDC_ARROW))
        wc.lpszClassName = _CLASS
        if not win32.user32.RegisterClassExW(ctypes.byref(wc)):
            error = ctypes.get_last_error()
            if error != 1410:  # already registered
                raise ctypes.WinError(error)
        _registered = True

    dialog = _Dialog(settings, save, test)
    hwnd = win32.user32.CreateWindowExW(
        0, _CLASS, "SidePeek 手机提醒设置",
        win32.WS_CAPTION | win32.WS_SYSMENU,
        0, 0, 460, 220, owner, None, win32.kernel32.GetModuleHandleW(None), None,
    )
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    dialog.hwnd = hwnd
    _instances[hwnd] = dialog

    _create_control(hwnd, "STATIC", "Bark Key：", 0, 18, 20, 100, 22)
    dialog.key_edit = _create_control(
        hwnd, "EDIT", settings.bark_device_key,
        _WS_TABSTOP | _ES_AUTOHSCROLL | _ES_PASSWORD | 0x0080,
        18, 45, 408, 26, _ID_KEY,
    )
    _create_control(hwnd, "STATIC", "在 iPhone 的 Bark App 复制设备 Key 并粘贴到这里。Key 会保存在 SidePeek.exe 同目录的 config.json。",
                    0, 18, 81, 408, 42)
    dialog.status = _create_control(hwnd, "STATIC", "保存后可点击“测试”确认手机能收到通知。",
                                    0, 18, 126, 408, 22, _ID_STATUS)
    _create_control(hwnd, "BUTTON", "保存", _WS_TABSTOP, 178, 158, 78, 28, _ID_SAVE)
    _create_control(hwnd, "BUTTON", "保存并测试", _WS_TABSTOP | _BS_DEFPUSHBUTTON,
                    264, 158, 100, 28, _ID_TEST)
    _create_control(hwnd, "BUTTON", "关闭", _WS_TABSTOP, 372, 158, 54, 28, _ID_CLOSE)

    rect = win32.wt.RECT()
    if owner and win32.user32.GetWindowRect(owner, ctypes.byref(rect)):
        x = rect.left + max(0, (rect.right - rect.left - 460) // 2)
        y = rect.top + max(0, (rect.bottom - rect.top - 220) // 2)
        win32.user32.SetWindowPos(hwnd, 0, x, y, 460, 220, 0x0040)
    win32.user32.ShowWindow(hwnd, win32.SW_SHOW)
    win32.user32.UpdateWindow(hwnd)
    win32.user32.SetFocus(dialog.key_edit)
    if owner:
        win32.user32.EnableWindow(owner, False)

    msg = win32.wt.MSG()
    try:
        while win32.user32.IsWindow(hwnd):
            result = win32.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            win32.user32.TranslateMessage(ctypes.byref(msg))
            win32.user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        if owner:
            win32.user32.EnableWindow(owner, True)
