"""Thin ``ctypes`` bindings for the Win32 / GDI / DWM APIs used by SidePeek.

Only the small subset this project needs is declared here, but every function
that is called has explicit ``argtypes`` / ``restype`` so it behaves correctly
on both 32-bit and 64-bit CPython.

Handles are typed as ``c_void_p`` so they come back as plain Python ``int``
(or ``None`` for NULL), which makes them easy to compare, store and pass back.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

# --------------------------------------------------------------------------
# DLLs
# --------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:                                     # pragma: no cover
    dwmapi = None


# --------------------------------------------------------------------------
# Basic types
# --------------------------------------------------------------------------
H = ctypes.c_void_p
LRESULT = ctypes.c_ssize_t
LONG_PTR = ctypes.c_ssize_t
UINT_PTR = ctypes.c_size_t

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, H, wt.UINT, wt.WPARAM, wt.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, H, wt.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, H, wt.DWORD, H, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD
)

HWND_TOPMOST = H(-1)
HWND_NOTOPMOST = H(-2)


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
# window styles
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
WS_EX_APPWINDOW = 0x00040000

CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
CS_DROPSHADOW = 0x00020000

SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_RESTORE = 9

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020

GWL_STYLE = -16
GWL_EXSTYLE = -20

# messages
WM_DESTROY = 0x0002
WM_SIZE = 0x0005
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_ERASEBKGND = 0x0014
WM_SHOWWINDOW = 0x0018
WM_GETMINMAXINFO = 0x0024
WM_NCHITTEST = 0x0084
WM_KEYDOWN = 0x0100
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A
WM_HOTKEY = 0x0312
WM_DISPLAYCHANGE = 0x007E
WM_APP = 0x8000

HTCLIENT = 1
HTCAPTION = 2
HTBOTTOMRIGHT = 17

IDC_ARROW = 32512
IDC_SIZENWSE = 32642

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

MONITOR_DEFAULTTONEAREST = 2

SPI_GETWORKAREA = 0x0030

PW_RENDERFULLCONTENT = 0x00000002

SRCCOPY = 0x00CC0020
HALFTONE = 4
BLACKNESS = 0x00000042
DIB_RGB_COLORS = 0

DT_LEFT = 0x0000
DT_CENTER = 0x0001
DT_RIGHT = 0x0002
DT_VCENTER = 0x0004
DT_BOTTOM = 0x0008
DT_SINGLELINE = 0x0020
DT_NOPREFIX = 0x0800

TRANSPARENT = 1
CLEARTYPE_QUALITY = 5
DEFAULT_CHARSET = 1
FW_SEMIBOLD = 600

# DWM thumbnail flags
DWM_TNP_RECTDESTINATION = 0x00000001
DWM_TNP_RECTSOURCE = 0x00000002
DWM_TNP_OPACITY = 0x00000004
DWM_TNP_VISIBLE = 0x00000008
DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


# --------------------------------------------------------------------------
# Structures
# --------------------------------------------------------------------------
class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", H),
        ("hIcon", H),
        ("hCursor", H),
        ("hbrBackground", H),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", H),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", H),
        ("fErase", wt.BOOL),
        ("rcPaint", wt.RECT),
        ("fRestore", wt.BOOL),
        ("fIncUpdate", wt.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
    ]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", wt.POINT),
        ("ptMaxSize", wt.POINT),
        ("ptMaxPosition", wt.POINT),
        ("ptMinTrackSize", wt.POINT),
        ("ptMaxTrackSize", wt.POINT),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", ctypes.c_byte),
        ("rgbGreen", ctypes.c_byte),
        ("rgbRed", ctypes.c_byte),
        ("rgbReserved", ctypes.c_byte),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wt.DWORD),
        ("rcDestination", wt.RECT),
        ("rcSource", wt.RECT),
        ("opacity", ctypes.c_ubyte),
        ("fVisible", wt.BOOL),
        ("fSourceClientAreaOnly", wt.BOOL),
    ]


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


# --------------------------------------------------------------------------
# user32
# --------------------------------------------------------------------------
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wt.WORD

user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    H, H, H, ctypes.c_void_p,
]
user32.CreateWindowExW.restype = H

user32.DefWindowProcW.argtypes = [H, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.DestroyWindow.argtypes = [H]
user32.DestroyWindow.restype = wt.BOOL

user32.ShowWindow.argtypes = [H, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL

user32.SetWindowPos.argtypes = [
    H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT
]
user32.SetWindowPos.restype = wt.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), H, wt.UINT, wt.UINT]
user32.GetMessageW.restype = ctypes.c_int

user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wt.MSG), H, wt.UINT, wt.UINT, wt.UINT
]
user32.PeekMessageW.restype = wt.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.TranslateMessage.restype = wt.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

user32.PostMessageW.argtypes = [H, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL

user32.SendMessageW.argtypes = [H, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = LRESULT

user32.SetTimer.argtypes = [H, UINT_PTR, wt.UINT, H]
user32.SetTimer.restype = UINT_PTR

user32.KillTimer.argtypes = [H, UINT_PTR]
user32.KillTimer.restype = wt.BOOL

user32.GetClientRect.argtypes = [H, ctypes.POINTER(wt.RECT)]
user32.GetClientRect.restype = wt.BOOL

user32.GetWindowRect.argtypes = [H, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = wt.BOOL

user32.IsWindow.argtypes = [H]
user32.IsWindow.restype = wt.BOOL

user32.IsWindowVisible.argtypes = [H]
user32.IsWindowVisible.restype = wt.BOOL

user32.IsIconic.argtypes = [H]
user32.IsIconic.restype = wt.BOOL

user32.IsZoomed.argtypes = [H]
user32.IsZoomed.restype = wt.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = H

user32.SetForegroundWindow.argtypes = [H]
user32.SetForegroundWindow.restype = wt.BOOL

user32.BringWindowToTop.argtypes = [H]
user32.BringWindowToTop.restype = wt.BOOL

user32.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD

user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL

user32.SetWinEventHook.argtypes = [
    wt.DWORD, wt.DWORD, H, WINEVENTPROC, wt.DWORD, wt.DWORD, wt.UINT
]
user32.SetWinEventHook.restype = H

user32.UnhookWinEvent.argtypes = [H]
user32.UnhookWinEvent.restype = wt.BOOL

user32.RegisterHotKey.argtypes = [H, ctypes.c_int, wt.UINT, wt.UINT]
user32.RegisterHotKey.restype = wt.BOOL

user32.UnregisterHotKey.argtypes = [H, ctypes.c_int]
user32.UnregisterHotKey.restype = wt.BOOL

user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL

user32.GetWindowTextW.argtypes = [H, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetClassNameW.argtypes = [H, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowDC.argtypes = [H]
user32.GetWindowDC.restype = H

user32.GetDC.argtypes = [H]
user32.GetDC.restype = H

user32.ReleaseDC.argtypes = [H, H]
user32.ReleaseDC.restype = ctypes.c_int

user32.PrintWindow.argtypes = [H, H, wt.UINT]
user32.PrintWindow.restype = wt.BOOL

user32.FillRect.argtypes = [H, ctypes.POINTER(wt.RECT), H]
user32.FillRect.restype = ctypes.c_int

user32.DrawTextW.argtypes = [H, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT]
user32.DrawTextW.restype = ctypes.c_int

user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = H

user32.AppendMenuW.argtypes = [H, wt.UINT, UINT_PTR, wt.LPCWSTR]
user32.AppendMenuW.restype = wt.BOOL

user32.TrackPopupMenu.argtypes = [
    H, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, H, ctypes.c_void_p
]
user32.TrackPopupMenu.restype = wt.BOOL

user32.DestroyMenu.argtypes = [H]
user32.DestroyMenu.restype = wt.BOOL

user32.LoadCursorW.argtypes = [H, H]
user32.LoadCursorW.restype = H

user32.SetCursor.argtypes = [H]
user32.SetCursor.restype = H

user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL

user32.ScreenToClient.argtypes = [H, ctypes.POINTER(wt.POINT)]
user32.ScreenToClient.restype = wt.BOOL

user32.SetCapture.argtypes = [H]
user32.SetCapture.restype = H

user32.ReleaseCapture.argtypes = []
user32.ReleaseCapture.restype = wt.BOOL

user32.InvalidateRect.argtypes = [H, ctypes.POINTER(wt.RECT), wt.BOOL]
user32.InvalidateRect.restype = wt.BOOL

user32.BeginPaint.argtypes = [H, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = H

user32.EndPaint.argtypes = [H, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.restype = wt.BOOL

user32.SetWindowRgn.argtypes = [H, H, wt.BOOL]
user32.SetWindowRgn.restype = ctypes.c_int

user32.MonitorFromWindow.argtypes = [H, wt.DWORD]
user32.MonitorFromWindow.restype = H

user32.GetMonitorInfoW.argtypes = [H, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wt.BOOL

user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]
user32.SystemParametersInfoW.restype = wt.BOOL

user32.SetProcessDPIAware.argtypes = []
user32.SetProcessDPIAware.restype = wt.BOOL

user32.SetProcessDpiAwarenessContext.argtypes = [H]
user32.SetProcessDpiAwarenessContext.restype = wt.BOOL

user32.GetWindowLongW.argtypes = [H, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long

user32.GetWindowLongPtrW = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
user32.GetWindowLongPtrW.argtypes = [H, ctypes.c_int]
user32.GetWindowLongPtrW.restype = LONG_PTR

user32.SetWindowLongPtrW = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
user32.SetWindowLongPtrW.argtypes = [H, ctypes.c_int, LONG_PTR]
user32.SetWindowLongPtrW.restype = LONG_PTR


# --------------------------------------------------------------------------
# gdi32
# --------------------------------------------------------------------------
gdi32.CreateCompatibleDC.argtypes = [H]
gdi32.CreateCompatibleDC.restype = H

gdi32.CreateCompatibleBitmap.argtypes = [H, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = H

gdi32.CreateDIBSection.argtypes = [
    H, ctypes.POINTER(BITMAPINFO), wt.UINT,
    ctypes.POINTER(ctypes.c_void_p), H, wt.DWORD,
]
gdi32.CreateDIBSection.restype = H

gdi32.SelectObject.argtypes = [H, H]
gdi32.SelectObject.restype = H

gdi32.DeleteObject.argtypes = [H]
gdi32.DeleteObject.restype = wt.BOOL

gdi32.DeleteDC.argtypes = [H]
gdi32.DeleteDC.restype = wt.BOOL

gdi32.BitBlt.argtypes = [H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         H, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.BitBlt.restype = wt.BOOL

gdi32.StretchBlt.argtypes = [H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wt.DWORD]
gdi32.StretchBlt.restype = wt.BOOL

gdi32.SetStretchBltMode.argtypes = [H, ctypes.c_int]
gdi32.SetStretchBltMode.restype = ctypes.c_int

gdi32.SetBrushOrgEx.argtypes = [H, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
gdi32.SetBrushOrgEx.restype = wt.BOOL

gdi32.CreateSolidBrush.argtypes = [wt.DWORD]
gdi32.CreateSolidBrush.restype = H

gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.CreatePen.restype = H

gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
    wt.DWORD, wt.LPCWSTR,
]
gdi32.CreateFontW.restype = H

gdi32.SetTextColor.argtypes = [H, wt.DWORD]
gdi32.SetTextColor.restype = wt.DWORD

gdi32.SetBkMode.argtypes = [H, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int

gdi32.CreateRoundRectRgn.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
]
gdi32.CreateRoundRectRgn.restype = H


# --------------------------------------------------------------------------
# kernel32
# --------------------------------------------------------------------------
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = H

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wt.DWORD

kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = H

kernel32.CloseHandle.argtypes = [H]
kernel32.CloseHandle.restype = wt.BOOL

kernel32.QueryFullProcessImageNameW.argtypes = [
    H, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL


# --------------------------------------------------------------------------
# dwmapi
# --------------------------------------------------------------------------
if dwmapi is not None:
    dwmapi.DwmIsCompositionEnabled.argtypes = [ctypes.POINTER(wt.BOOL)]
    dwmapi.DwmIsCompositionEnabled.restype = ctypes.c_long

    dwmapi.DwmRegisterThumbnail.argtypes = [H, H, ctypes.POINTER(H)]
    dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long

    dwmapi.DwmUnregisterThumbnail.argtypes = [H]
    dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long

    dwmapi.DwmUpdateThumbnailProperties.argtypes = [
        H, ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES)
    ]
    dwmapi.DwmUpdateThumbnailProperties.restype = ctypes.c_long

    dwmapi.DwmQueryThumbnailSourceSize.argtypes = [H, ctypes.POINTER(SIZE)]
    dwmapi.DwmQueryThumbnailSourceSize.restype = ctypes.c_long

    dwmapi.DwmSetWindowAttribute.argtypes = [H, wt.DWORD, ctypes.c_void_p, wt.DWORD]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

    dwmapi.DwmGetWindowAttribute.argtypes = [H, wt.DWORD, ctypes.c_void_p, wt.DWORD]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


# --------------------------------------------------------------------------
# Convenience helpers
# --------------------------------------------------------------------------
def rgb(r: int, g: int, b: int) -> int:
    """Pack an RGB triple into a COLORREF."""
    return (b << 16) | (g << 8) | r


def window_rect(hwnd) -> tuple[int, int, int, int] | None:
    rc = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
        return None
    return rc.left, rc.top, rc.right, rc.bottom


def client_rect(hwnd) -> tuple[int, int, int, int]:
    rc = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    return rc.left, rc.top, rc.right, rc.bottom


def window_title(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def process_name(hwnd) -> str:
    """Executable file name (``cs2.exe``) that owns ``hwnd``."""
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    ph = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not ph:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(ph, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(ph)


def process_id(hwnd) -> int:
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def foreground() -> int:
    return user32.GetForegroundWindow() or 0


def is_window(hwnd) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def is_visible(hwnd) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def is_minimized(hwnd) -> bool:
    return bool(user32.IsIconic(hwnd))


def is_maximized(hwnd) -> bool:
    return bool(user32.IsZoomed(hwnd))


def enum_windows() -> list[int]:
    out: list[int] = []

    @WNDENUMPROC
    def _cb(hwnd, _lp):
        out.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return out


def monitor_rect(hwnd) -> tuple[int, int, int, int]:
    """Full bounds of the monitor that is nearest to ``hwnd``."""
    mon = user32.MonitorFromWindow(hwnd or 0, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        r = info.rcMonitor
        return r.left, r.top, r.right, r.bottom
    rc = wt.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0)
    return rc.left, rc.top, rc.right, rc.bottom


def monitor_work_area(hwnd) -> tuple[int, int, int, int]:
    """Bounds of the monitor minus the taskbar."""
    mon = user32.MonitorFromWindow(hwnd or 0, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    rc = wt.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0)
    return rc.left, rc.top, rc.right, rc.bottom


def composition_enabled() -> bool:
    if dwmapi is None:
        return False
    enabled = wt.BOOL(0)
    try:
        return dwmapi.DwmIsCompositionEnabled(ctypes.byref(enabled)) == 0 and bool(
            enabled.value
        )
    except OSError:
        return False


def frame_bounds(hwnd) -> tuple[int, int, int, int] | None:
    """Visible window bounds, excluding the invisible resize border."""
    if dwmapi is not None:
        rc = wt.RECT()
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rc), ctypes.sizeof(rc)
        )
        if hr == 0:
            return rc.left, rc.top, rc.right, rc.bottom
    return window_rect(hwnd)


def dpi_aware() -> None:
    """Enable DPI awareness so all coordinates are physical pixels."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == (HANDLE)-4
        if user32.SetProcessDpiAwarenessContext(H(-4)):
            return
    except OSError:
        pass
    try:
        user32.SetProcessDPIAware()
    except OSError:
        pass


def force_foreground(hwnd) -> bool:
    """Try hard to bring ``hwnd`` to the foreground.

    Windows refuses ``SetForegroundWindow`` for processes that do not own the
    foreground window, so we temporarily attach to the foreground thread's
    input queue, which lifts that restriction.
    """
    if not is_window(hwnd):
        return False
    if is_minimized(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)

    fg = foreground()
    if fg == hwnd:
        return True

    cur_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if fg_tid and fg_tid != cur_tid:
        attached = bool(user32.AttachThreadInput(fg_tid, cur_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(fg_tid, cur_tid, False)

    return foreground() == hwnd
