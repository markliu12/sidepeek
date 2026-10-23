"""CS2 round-result recognition and Windows notification helpers."""

from __future__ import annotations

import asyncio
import ctypes
import os
import struct
import sys
import threading
import time
import uuid
from ctypes import wintypes
from typing import Callable

from .capture import WindowCapture
from .diag import log

POLL_SECONDS = 0.5
PRESENT_FRAMES = 2
ABSENT_FRAMES = 4
# A round cannot end twice in a row this fast, so a detection inside the
# window is a banner fade artefact and must not produce a second toast.
MIN_NOTIFY_INTERVAL = 10.0
APP_ID = "MarkLiu.SidePeek"

# CS2 both localises the banner and switches between simplified and
# traditional Chinese depending on the client, and OCR may hand back either.
ROUND_LABELS = {
    "回合胜利": "win",
    "回合勝利": "win",
    "回合获胜": "win",
    "回合獲勝": "win",
    "回合失败": "loss",
    "回合失敗": "loss",
    "回合落败": "loss",
    "回合落敗": "loss",
}
ROUND_TITLES = {
    "win": "CS2 回合胜利",
    "loss": "CS2 回合失败",
}
ROUND_MESSAGE = "回合已结束，切回游戏准备下一回合。"

# Fractions of the viewport that hold the round-result banner. The OCR crop is
# slightly wider than the colour probe; both trace back to the same banner.
BANNER_BOX = (0.35, 0.14, 0.65, 0.28)
COLOR_BOX = (0.37, 0.15, 0.63, 0.27)
# Share of the colour probe that a real banner has to cover, and how far it
# has to out-vote the other banner colour.
COVERAGE = 0.10
DOMINANCE = 2.5


def normalize_ocr_text(text: str) -> str:
    """Remove whitespace so OCR line breaks do not split the result label."""
    return "".join(text.split())


def classify_round_result(text: str) -> str | None:
    normalized = normalize_ocr_text(text)
    for phrase, result in ROUND_LABELS.items():
        if phrase in normalized:
            return result
    return None


class RoundResultState:
    """Require stable positives, re-arm only after a stable absence.

    ``observe`` returns ``"win"``/``"loss"`` exactly once per round end. Both
    the latch and the cooldown exist because the banner fades in and out over
    several seconds: frames around the fade dip below the detector's threshold,
    which used to re-arm the latch and fire the same round twice.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.candidate: str | None = None
        self.present_count = 0
        self.absent_count = 0
        self.latched = False
        self.last_notified: float | None = None

    def observe(self, result: str | None) -> str | None:
        if result is None:
            self.candidate = None
            self.present_count = 0
            if self.latched:
                self.absent_count += 1
                if self.absent_count >= ABSENT_FRAMES:
                    self.latched = False
                    self.absent_count = 0
            return None

        self.absent_count = 0
        if self.latched:
            return None
        if result == self.candidate:
            self.present_count += 1
        else:
            self.candidate = result
            self.present_count = 1
        if self.present_count < PRESENT_FRAMES:
            return None

        self.latched = True
        now = self._clock()
        if self.last_notified is not None and now - self.last_notified < MIN_NOTIFY_INTERVAL:
            return None
        self.last_notified = now
        return result


def crop_result_region(bgra: bytes, width: int, height: int) -> tuple[bytes, int, int]:
    """Crop the central CS2 banner area and return a top-down 32-bit BMP."""
    # CS2 places the result card in the upper-middle portion of the viewport.
    left, top = round(width * BANNER_BOX[0]), round(height * BANNER_BOX[1])
    right, bottom = round(width * BANNER_BOX[2]), round(height * BANNER_BOX[3])
    crop_w, crop_h = right - left, bottom - top
    if width <= 0 or height <= 0 or len(bgra) < width * height * 4 or crop_w < 8 or crop_h < 8:
        return b"", 0, 0

    rows = []
    for y in range(top, bottom):
        start = (y * width + left) * 4
        rows.append(bgra[start:start + crop_w * 4])
    pixels = b"".join(reversed(rows))  # BMP rows are bottom-up.
    file_size = 14 + 40 + len(pixels)
    header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    dib = struct.pack("<IiiHHIIiiII", 40, crop_w, crop_h, 1, 32, 0, len(pixels), 2835, 2835, 0, 0)
    return header + dib + pixels, crop_w, crop_h


def classify_banner_color(bgra: bytes, width: int, height: int) -> str | None:
    """Fallback for Chinese OCR engines that cannot read CS2's stylized font.

    CS2 uses a saturated red loss banner and a saturated golden-yellow win
    banner. The banner is a solid block, so the colour has to *fill* a fair
    share of the sampled area - the old 2% threshold fired on blood spatter,
    red map props and the kill feed, which is what produced three toasts for
    one round.
    """
    if width < 8 or height < 8 or len(bgra) < width * height * 4:
        return None
    left, top = round(width * COLOR_BOX[0]), round(height * COLOR_BOX[1])
    right, bottom = round(width * COLOR_BOX[2]), round(height * COLOR_BOX[3])
    if right - left < 8 or bottom - top < 8:
        return None
    red = yellow = seen = 0
    # Subsample to keep capture analysis inexpensive at 4K resolutions.
    stride = max(1, width // 640)
    view = memoryview(bgra)
    for y in range(top, bottom, stride):
        row = y * width * 4
        for x in range(left, right, stride):
            offset = row + x * 4
            b, g, r = view[offset], view[offset + 1], view[offset + 2]
            seen += 1
            if r > 150 and r > g * 1.35 and r > b * 1.5 and g < 130:
                red += 1
            elif r > 170 and g > 115 and r > b * 1.6 and g > b * 1.35 and b < 120:
                yellow += 1
    if not seen:
        return None
    if red / seen >= COVERAGE and red > yellow * DOMINANCE:
        return "loss"
    if yellow / seen >= COVERAGE and yellow > red * DOMINANCE:
        return "win"
    return None


class WindowsOcr:
    """Windows.Media.Ocr wrapper; constructed lazily on its worker thread."""

    def __init__(self) -> None:
        from winrt.windows.globalization import Language  # type: ignore[import-not-found]
        from winrt.windows.media.ocr import OcrEngine  # type: ignore[import-not-found]
        self._Language = Language
        self._OcrEngine = OcrEngine
        self.engine = self._create_engine()

    def _create_engine(self):
        languages = []
        try:
            languages.append(self._Language("zh-TW"))
        except Exception:
            pass
        try:
            languages.append(self._Language("zh-CN"))
        except Exception:
            pass
        for language in languages:
            try:
                engine = self._OcrEngine.try_create_from_language(language)
            except Exception:
                engine = None
            if engine is not None:
                log(f"CS2 OCR language: {language.language_tag}")
                return engine
        try:
            engine = self._OcrEngine.try_create_from_user_profile_languages()
        except Exception as exc:
            raise RuntimeError(f"Windows OCR initialization failed: {exc}") from exc
        if engine is None:
            raise RuntimeError("no compatible Windows OCR language is installed (install Chinese OCR language support)")
        log(f"CS2 OCR language: {engine.recognizer_language.language_tag} (user profile)")
        return engine

    async def recognize(self, bmp: bytes) -> str:
        from winrt.windows.graphics.imaging import BitmapDecoder  # type: ignore[import-not-found]
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream  # type: ignore[import-not-found]

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(bmp)
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await self.engine.recognize_async(bitmap)
        return "\n".join(line.text for line in result.lines)


class WindowsToast:
    """Send a desktop toast associated with a per-user Start Menu shortcut."""

    def __init__(self) -> None:
        self._ensure_shortcut()

    @staticmethod
    def _guid(value: str) -> GUID:
        return GUID.from_uuid(uuid.UUID(value))

    def _ensure_shortcut(self) -> None:
        # AUMID-bound desktop toasts require a Start Menu shortcut carrying the
        # System.AppUserModel.ID property. ShellLink and IPropertyStore keep this
        # setup dependency-free and scoped to the current user.
        ole32 = ctypes.OleDLL("ole32")
        init_hr = ole32.CoInitializeEx(None, 0x2)
        owns_com = init_hr in (0, 1)
        clsid_shell_link = self._guid("00021401-0000-0000-C000-000000000046")
        iid_shell_link = self._guid("000214F9-0000-0000-C000-000000000046")
        iid_persist_file = self._guid("0000010b-0000-0000-C000-000000000046")
        iid_property_store = self._guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")

        class PropertyKey(ctypes.Structure):
            _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

        class PropValue(ctypes.Structure):
            class Value(ctypes.Union):
                _fields_ = [("pwszVal", wintypes.LPWSTR), ("padding", ctypes.c_ubyte * 8)]
            _anonymous_ = ("value",)
            _fields_ = [("vt", wintypes.WORD), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD), ("value", Value)]

        def method(pointer, index, restype, argtypes):
            vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])

        shell = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(clsid_shell_link), None, 1, ctypes.byref(iid_shell_link), ctypes.byref(shell))
        if hr < 0:
            raise OSError(f"CoCreateInstance(IShellLinkW) failed: 0x{hr & 0xffffffff:08x}")
        try:
            target = sys.executable
            args = ""
            if not getattr(sys, "frozen", False):
                target = sys.executable
                args = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "run.py"))
            method(shell, 20, ctypes.c_long, [wintypes.LPCWSTR])(shell, target)
            method(shell, 11, ctypes.c_long, [wintypes.LPCWSTR])(shell, args)
            method(shell, 7, ctypes.c_long, [wintypes.LPCWSTR])(shell, "SidePeek")
            icon = os.path.join(os.path.dirname(sys.executable), "assets", "sidepeek.ico")
            if not os.path.exists(icon):
                icon = sys.executable
            method(shell, 17, ctypes.c_long, [wintypes.LPCWSTR, ctypes.c_int])(shell, icon, 0)

            persist = ctypes.c_void_p()
            hr = method(shell, 0, ctypes.c_long, [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)])(shell, ctypes.byref(iid_persist_file), ctypes.byref(persist))
            if hr < 0:
                raise OSError(f"IShellLink QueryInterface(IPersistFile) failed: 0x{hr & 0xffffffff:08x}")
            try:
                appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
                start_menu = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")
                os.makedirs(start_menu, exist_ok=True)
                shortcut = os.path.join(start_menu, "SidePeek.lnk")
            finally:
                method(persist, 2, wintypes.ULONG, [])(persist)

            store = ctypes.c_void_p()
            hr = method(shell, 0, ctypes.c_long, [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)])(shell, ctypes.byref(iid_property_store), ctypes.byref(store))
            if hr < 0:
                raise OSError(f"IShellLink QueryInterface(IPropertyStore) failed: 0x{hr & 0xffffffff:08x}")
            try:
                key = PropertyKey(self._guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 5)
                value = PropValue()
                value.vt = 31  # VT_LPWSTR
                value.pwszVal = APP_ID
                hr = method(store, 6, ctypes.c_long, [ctypes.POINTER(PropertyKey), ctypes.POINTER(PropValue)])(store, ctypes.byref(key), ctypes.byref(value))
                if hr < 0:
                    raise OSError(f"IPropertyStore.SetValue(AppUserModelID) failed: 0x{hr & 0xffffffff:08x}")
                hr = method(store, 7, ctypes.c_long, [])(store)
                if hr < 0:
                    raise OSError(f"IPropertyStore.Commit failed: 0x{hr & 0xffffffff:08x}")
            finally:
                method(store, 2, wintypes.ULONG, [])(store)
            persist = ctypes.c_void_p()
            hr = method(shell, 0, ctypes.c_long, [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)])(shell, ctypes.byref(iid_persist_file), ctypes.byref(persist))
            if hr < 0:
                raise OSError(f"IShellLink QueryInterface(IPersistFile) failed: 0x{hr & 0xffffffff:08x}")
            try:
                hr = method(persist, 6, ctypes.c_long, [wintypes.LPCWSTR, wintypes.BOOL])(persist, shortcut, True)
                if hr < 0:
                    raise OSError(f"IShellLink Save failed: 0x{hr & 0xffffffff:08x}")
            finally:
                method(persist, 2, wintypes.ULONG, [])(persist)
        finally:
            method(shell, 2, wintypes.ULONG, [])(shell)
            if owns_com:
                ole32.CoUninitialize()

    @staticmethod
    def show(title: str, message: str) -> None:
        from winrt.windows.data.xml.dom import XmlDocument  # type: ignore[import-not-found]
        from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager  # type: ignore[import-not-found]

        xml = XmlDocument()
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        xml.load_xml(
            '<toast><visual><binding template="ToastGeneric">'
            f"<text>{safe_title}</text><text>{safe_message}</text>"
            "</binding></visual></toast>"
        )
        notification = ToastNotification(xml)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [wintypes.LPCWSTR]
        set_app_id.restype = ctypes.c_long
        hr = set_app_id(APP_ID)
        if hr < 0:
            raise OSError(f"SetCurrentProcessExplicitAppUserModelID failed: 0x{hr & 0xffffffff:08x}")
        # The parameterless overload resolves the AUMID by matching the running
        # process against a Start Menu shortcut and fails with ERROR_NOT_FOUND
        # (0x80070490) for an unpackaged exe. Naming the AUMID explicitly is
        # the documented path for desktop apps and works with the shortcut
        # written by _ensure_shortcut.
        try:
            notifier = ToastNotificationManager.create_toast_notifier_with_id(APP_ID)
        except Exception:
            notifier = ToastNotificationManager.create_toast_notifier()
        notifier.show(notification)


class CS2RoundMonitor:
    """Background sampling loop. Provider returns an eligible CS2 HWND or 0."""

    def __init__(self, target_provider: Callable[[], int], notify: Callable[[str, str], None]) -> None:
        self.target_provider = target_provider
        self.notify = notify
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="SidePeek-CS2-OCR", daemon=True)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._started = True
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self._started:
            self.thread.join(timeout=2.0)

    def _run(self) -> None:
        capture: WindowCapture | None = None
        hwnd = 0
        state = RoundResultState()
        ocr: WindowsOcr | None = None
        ocr_failure_logged = False
        loop_failure_logged = False
        # One loop for the lifetime of the thread: asyncio.run() built and tore
        # down a loop twice a second, which is pure overhead and can abandon a
        # WinRT operation that is still in flight.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            try:
                ocr = WindowsOcr()
            except Exception as exc:
                log(f"CS2 round OCR unavailable; using banner colour fallback: {exc}")

            while not self.stop_event.is_set():
                try:
                    current = self.target_provider()
                    if current != hwnd:
                        if capture:
                            capture.release()
                        capture = WindowCapture(current) if current else None
                        hwnd = current
                        state = RoundResultState()
                    if not current or not capture:
                        self.stop_event.wait(POLL_SECONDS)
                        continue
                    if capture.grab():
                        frame = capture.pixel_bytes()
                        bmp, _, _ = crop_result_region(frame, capture.width, capture.height)
                        result = None
                        source = ""
                        if bmp and ocr:
                            try:
                                recognized = loop.run_until_complete(ocr.recognize(bmp))
                                result = classify_round_result(recognized)
                                source = "ocr"
                            except Exception as exc:
                                if not ocr_failure_logged:
                                    log(f"CS2 OCR failed; using banner colour fallback: {exc}")
                                    ocr_failure_logged = True
                        if result is None:
                            result = classify_banner_color(frame, capture.width, capture.height)
                            source = "colour"
                        event = state.observe(result)
                        if event:
                            self.notify(ROUND_TITLES[event], ROUND_MESSAGE)
                            log(f"CS2 round result detected: {event} (via {source})")
                    else:
                        state.observe(None)
                except Exception as exc:
                    if not loop_failure_logged:
                        log(f"CS2 round monitor error: {exc}")
                        loop_failure_logged = True
                self.stop_event.wait(POLL_SECONDS)
        finally:
            if capture:
                capture.release()
            try:
                loop.close()
            except Exception:
                pass


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_uuid(cls, value: uuid.UUID) -> "GUID":
        return cls.from_buffer_copy(value.bytes_le)
