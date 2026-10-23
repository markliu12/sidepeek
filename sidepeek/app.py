"""Application glue: message loop, foreground hook, hotkeys and diagnostics."""

from __future__ import annotations

import argparse
import ctypes
import sys
import threading
from typing import Any

from . import __version__
from . import autostart, instance
from . import bark
from . import bark_settings
from . import config as config_mod
from . import win32
from .capture import WindowCapture
from .config import Settings
from .cs2_rounds import CS2RoundMonitor, WindowsToast
from .diag import install_excepthook, log, log_path
from .overlay import CLASS_NAME, Overlay
from .png import write_png
from .watcher import Target, Watcher, covers_monitor, describe


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def parse_hotkey(spec: str) -> tuple[int, int]:
    """``"ctrl+alt+g"`` -> ``(MOD_CONTROL | MOD_ALT, 0x47)``."""
    mods = 0
    vk = 0
    for part in spec.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in ("ctrl", "control", "ctl"):
            mods |= win32.MOD_CONTROL
        elif part in ("alt",):
            mods |= win32.MOD_ALT
        elif part in ("shift",):
            mods |= win32.MOD_SHIFT
        elif part in ("win", "meta"):
            mods |= win32.MOD_WIN
        elif len(part) == 1:
            vk = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit():
            vk = 0x70 + int(part[1:]) - 1          # VK_F1 == 0x70
    return mods, vk


def visible_windows(settings: Settings | None = None) -> list[tuple[int, str, str, int]]:
    """(hwnd, exe, title, area) for every visible top-level window."""
    out = []
    for hwnd in win32.enum_windows():
        if not win32.is_visible(hwnd):
            continue
        title = win32.window_title(hwnd)
        if not title:
            continue
        rect = win32.window_rect(hwnd)
        if not rect:
            continue
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if area < 40000:
            continue
        out.append((hwnd, win32.process_name(hwnd), title, area))
    out.sort(key=lambda item: item[3], reverse=True)
    return out


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class App:
    def __init__(
        self,
        settings: Settings,
        config_path: str,
        cli_overrides: frozenset[str] = frozenset(),
    ) -> None:
        self.settings = settings
        self.config_path = config_path
        self.cli_overrides = cli_overrides
        self.overlay = Overlay(settings, config_path)
        self.watcher = Watcher(settings)
        self._hook = None
        self._hook_ref: Any = None
        self._hotkeys: list[int] = []
        self._checking = False
        self.cs2_monitor: CS2RoundMonitor | None = None

    # -- lifecycle ---------------------------------------------------------
    def run(self) -> int:
        try:
            self.overlay.create()
        except OSError as exc:
            log(f"cannot create overlay window: {exc}")
            return 1

        self.overlay.on_check = self.check
        self.overlay.on_quit = self.quit
        self.overlay.on_activate = self.activate_target
        self.overlay.on_toggle_pause = self.toggle_pause
        self.overlay.on_lock = self.lock_foreground
        self.overlay.on_select_target = self.select_target
        self.overlay.on_toggle_autostart = self.toggle_autostart
        self.overlay.on_toggle_cs2_rounds = self.toggle_cs2_rounds
        self.overlay.on_test_bark = self.test_bark
        self.overlay.on_configure_bark = self.configure_bark
        self.overlay.candidates_provider = self.watcher.candidates
        self.overlay.autostart_provider = autostart.is_enabled

        if self.settings.cs2_round_notifications:
            self._start_cs2_monitor()

        self._install_hook()
        self._register_hotkeys()
        self.overlay.start_polling(self.settings.poll_ms)

        log("watching... hotkeys: "
            f"{self.settings.hotkey_toggle}=pause/resume  "
            f"{self.settings.hotkey_lock}=lock current window  "
            f"{self.settings.hotkey_quit}=quit")
        log(f"tray icon: {'ok' if self.overlay.tray_added else 'unavailable'}")

        self.check()
        try:
            self._message_loop()
        finally:
            self.overlay.destroy()
            self._teardown()
            config_mod.save_runtime(
                self.config_path, self.settings, skip=self.cli_overrides
            )
        return 0

    def _message_loop(self) -> None:
        msg = win32.wt.MSG()
        while True:
            ret = win32.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0:
                break
            if ret == -1:
                break
            win32.user32.TranslateMessage(ctypes.byref(msg))
            win32.user32.DispatchMessageW(ctypes.byref(msg))

    def _install_hook(self) -> None:
        # A foreground change is the single event we care about, so hook it
        # instead of busy-polling. The callback only posts a message; the real
        # work happens on the UI thread.
        def _cb(_hook, _event, _hwnd, _obj, _child, _thread, _time):
            win32.user32.PostMessageW(self.overlay.hwnd, win32.WM_APP + 1, 0, 0)

        self._hook_ref = win32.WINEVENTPROC(_cb)
        self._hook = win32.user32.SetWinEventHook(
            win32.EVENT_SYSTEM_FOREGROUND, win32.EVENT_SYSTEM_FOREGROUND,
            0, self._hook_ref, 0, 0,
            win32.WINEVENT_OUTOFCONTEXT | win32.WINEVENT_SKIPOWNPROCESS,
        )

    def _register_hotkeys(self) -> None:
        specs = (
            self.settings.hotkey_toggle,
            self.settings.hotkey_lock,
            self.settings.hotkey_quit,
        )
        failed: list[str] = []
        for index, spec in enumerate(specs, start=1):
            if not spec:
                continue
            mods, vk = parse_hotkey(spec)
            if not vk:
                failed.append(spec)
                continue
            if win32.user32.RegisterHotKey(self.overlay.hwnd, index, mods | win32.MOD_NOREPEAT, vk):
                self._hotkeys.append(index)
            else:
                failed.append(spec)

        for spec in failed:
            log(f"hotkey '{spec}' is taken or unparsable; skipped")
        if failed:
            # the packaged build has no console, so this is the only way the
            # user can learn that a hotkey they rely on is not active
            self.overlay.notify(
                "SidePeek 热键被占用",
                f"{'、'.join(failed)} 已被其他程序占用或无法识别。"
                "相应功能仍可从通知区域菜单使用。",
                warning=True,
            )

    def _teardown(self) -> None:
        if self.cs2_monitor:
            self.cs2_monitor.stop()
            self.cs2_monitor = None
        if self._hook:
            win32.user32.UnhookWinEvent(self._hook)
            self._hook = None
        for index in self._hotkeys:
            win32.user32.UnregisterHotKey(self.overlay.hwnd, index)
        self._hotkeys.clear()

    # -- actions -----------------------------------------------------------
    def check(self) -> None:
        if self._checking:
            return
        self._checking = True
        try:
            decision = self.watcher.evaluate(self.overlay.hwnd)
            if decision.show and decision.target:
                self.overlay.show_target(decision.target)
            else:
                self.overlay.hide()
        finally:
            self._checking = False

    def activate_target(self) -> None:
        target = self.overlay.target or self.watcher.last_game
        if target and win32.is_window(target.hwnd):
            win32.force_foreground(target.hwnd)

    def toggle_pause(self) -> None:
        self.watcher.paused = not self.watcher.paused
        self.overlay.set_paused(self.watcher.paused)
        log(f"{'paused' if self.watcher.paused else 'resumed'}")
        self.check()

    def lock_foreground(self) -> None:
        target = self.watcher.lock_foreground()
        if target:
            self.overlay.set_locked(target)
            log(f"locked target: {target.display_name} ({target.exe})")
        self.check()

    def select_target(self, target: Target | None) -> None:
        """Handle a choice from the "监视窗口" submenu.

        ``None`` means "automatic", which is also how a pinned target is
        released - there is no separate unlock action.
        """
        self.watcher.locked = target
        self.overlay.set_locked(target)
        if target is None:
            log("target: automatic")
        else:
            log(f"target: {target.display_name} ({target.exe})")
        self.check()

    def toggle_autostart(self) -> None:
        """Flip the HKCU Run entry and report the outcome."""
        before = autostart.is_enabled()
        after = autostart.toggle()
        if after == before:
            log("could not change the run-at-login value")
            self.overlay.notify(
                "SidePeek",
                "无法修改开机启动设置（注册表写入被拒绝）。",
                warning=True,
            )
            return
        log(f"start with Windows: {'on' if after else 'off'}")
        self.overlay.notify(
            "SidePeek",
            "下次登录 Windows 时将自动启动。" if after else "已取消开机自动启动。",
        )

    def _start_cs2_monitor(self) -> None:
        try:
            WindowsToast()
            self.cs2_monitor = CS2RoundMonitor(
                self._cs2_round_target,
                self._notify_cs2_round,
                language_provider=lambda: self.settings.notification_language,
            )
            self.cs2_monitor.start()
            log("CS2 round notifications: enabled")
        except Exception as exc:
            self.cs2_monitor = None
            log(f"CS2 round notifications could not initialize: {exc}")
            # the tray check mark would otherwise claim a feature that is not
            # running, and the packaged build has nowhere else to say so
            self.overlay.notify(
                "SidePeek",
                f"CS2 回合提醒未能启用：{exc}",
                warning=True,
            )

    def _cs2_round_target(self) -> int:
        if self.watcher.paused or not self.settings.cs2_round_notifications:
            return 0
        target = self.watcher.last_game
        if not target or target.exe.lower() != "cs2.exe":
            return 0
        hwnd = target.hwnd
        if (not win32.is_window(hwnd) or not win32.is_visible(hwnd)
                or win32.is_minimized(hwnd) or win32.foreground() == hwnd):
            return 0
        return hwnd

    def _notify_cs2_round(self, title: str, message: str) -> None:
        try:
            WindowsToast.show(title, message)
        except Exception as exc:
            log(f"CS2 Windows toast failed; falling back to tray notification: {exc}")
            if not self.overlay.notify(title, message):
                log("CS2 tray notification fallback was unavailable")
        if self.settings.bark_device_key:
            self._send_bark_async(title, message)

    def _send_bark_async(self, title: str, message: str, *, test: bool = False) -> None:
        key = self.settings.bark_device_key
        if not key:
            if test:
                self.overlay.notify("Bark 尚未配置", "请先在 config.json 中填写 bark_device_key。")
            return

        def send() -> None:
            try:
                bark.send_push(key, title, message, self.settings.bark_icon_url)
                log("Bark push sent")
                if test:
                    self.overlay.notify("Bark 测试提醒已发送", "请检查手机是否收到 SidePeek 测试通知。")
            except Exception as exc:
                log(f"Bark push failed: {type(exc).__name__}: {exc}")
                self.overlay.notify(
                    "Bark 推送失败",
                    "请检查网络与 Bark Key；详情见 sidepeek.log。",
                    warning=True,
                )

        threading.Thread(target=send, name="SidePeek-Bark", daemon=True).start()

    def test_bark(self) -> None:
        if not self.settings.bark_device_key:
            self.overlay.notify("Bark 尚未配置", "请先在 config.json 中填写 bark_device_key。")
            return
        self._send_bark_async(
            "SidePeek 测试提醒",
            "如果收到这条通知，Bark 已配置成功。",
            test=True,
        )

    def configure_bark(self) -> None:
        def save() -> None:
            config_mod.save_runtime(
                self.config_path, self.settings, skip=self.cli_overrides
            )
            log("Bark settings saved")

        bark_settings.show_bark_settings(
            self.overlay.hwnd, self.settings, save, self.test_bark
        )

    def toggle_cs2_rounds(self) -> None:
        self.settings.cs2_round_notifications = not self.settings.cs2_round_notifications
        if self.settings.cs2_round_notifications:
            self._start_cs2_monitor()
            if self.cs2_monitor is None:
                # keep the tray check mark honest: nothing is sampling now
                self.settings.cs2_round_notifications = False
        elif self.cs2_monitor:
            self.cs2_monitor.stop()
            self.cs2_monitor = None
            log("CS2 round notifications: disabled")
        config_mod.save_runtime(self.config_path, self.settings)

    def quit(self) -> None:
        win32.user32.PostQuitMessage(0)


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------
def _pick_window(settings: Settings) -> tuple[int, str, str] | None:
    ignore = set(settings.ignore) | {"python.exe", "pythonw.exe"}
    for hwnd, exe, title, _area in visible_windows(settings):
        if exe.lower() in ignore:
            continue
        if win32.is_minimized(hwnd):
            continue
        return hwnd, exe, title
    return None


def do_list() -> int:
    print(f"{'HWND':>10}  {'SIZE':>11}  {'FULL':^4}  EXE / TITLE")
    for hwnd, exe, title, area in visible_windows():
        rect = win32.window_rect(hwnd) or (0, 0, 0, 0)
        size = f"{rect[2] - rect[0]}x{rect[3] - rect[1]}"
        full = "yes" if covers_monitor(hwnd) else "-"
        print(f"{hwnd:>10}  {size:>11}  {full:^4}  {exe}  |  {title[:60]}")
    return 0


def do_self_test(settings: Settings) -> int:
    print("=" * 72)
    print("SidePeek self-test")
    print("=" * 72)
    print(f"python          : {sys.version.split()[0]} ({8 * ctypes.sizeof(ctypes.c_void_p)}-bit)")
    print(f"windows build   : {sys.getwindowsversion().build}")
    print(f"dwm composition : {win32.composition_enabled()}")
    print(f"backend setting : {settings.backend}")
    print()

    candidates = visible_windows(settings)
    print(f"visible top-level windows: {len(candidates)}")
    for hwnd, exe, title, area in candidates[:8]:
        flag = "FULLSCREEN" if covers_monitor(hwnd) else "          "
        print(f"  {flag} {exe:<24} {title[:44]}")
    print()

    picked = _pick_window(settings)
    if not picked:
        print("no suitable window found; run a game (or any app) and retry")
        return 1
    hwnd, exe, title = picked
    target = describe(hwnd)
    print(f"test target: {exe} | {title[:50]}")
    rect = win32.window_rect(hwnd)
    print(f"  window rect : {rect}")

    overlay = Overlay(settings, config_mod.default_path())
    failure = 0
    try:
        overlay.create()
        print("  window      : created")
        ok_dwm = overlay._attach_dwm(target)
        print(f"  dwm thumbnail: {'OK  size=' + str(overlay.source_size) if ok_dwm else 'FAILED  ' + overlay.fallback_reason}")
        overlay._detach()

        cap = WindowCapture(hwnd)
        ok_cap = cap.grab()
        print(f"  capture      : {'OK  ' + str((cap.width, cap.height)) + ' via ' + cap.method if ok_cap else 'FAILED (blank or unsupported window)'}")
        cap.release()

        if not ok_dwm and not ok_cap:
            failure = 2
    finally:
        overlay.destroy()

    print()
    if failure:
        print("result: this window cannot be peeked by either backend")
    else:
        print("result: ready - at least one backend works on this machine")
    return failure


def do_screenshot(settings: Settings, path: str, exe_hint: str = "") -> int:
    hint = exe_hint.lower()
    picked = None
    for hwnd, exe, title, area in visible_windows(settings):
        if hint and hint in exe.lower():
            picked = (hwnd, exe, title)
            break
    picked = picked or _pick_window(settings)
    if not picked:
        print("no window to capture")
        return 1
    hwnd, exe, title = picked
    cap = WindowCapture(hwnd)
    try:
        if not cap.grab():
            print(f"capture failed for {exe} ({title})")
            return 1
        write_png(path, cap.width, cap.height, cap.pixel_bytes())
        print(f"saved {cap.width}x{cap.height} frame of '{title}' -> {path} (via {cap.method})")
    finally:
        cap.release()
    return 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sidepeek",
        description="Show a live thumbnail of your game while it is in the background.",
    )
    p.add_argument("--config", help="path to config.json")
    p.add_argument("--backend", choices=("auto", "dwm", "capture"), help="override renderer")
    p.add_argument("--width", type=int, help="overlay width in px")
    p.add_argument("--height", type=int, help="overlay height in px")
    p.add_argument("--target", action="append", metavar="EXE",
                   help="process name to watch (repeatable), disables auto-detect")
    p.add_argument("--list", action="store_true", help="list visible windows and exit")
    p.add_argument("--self-test", action="store_true", help="check both renderers and exit")
    p.add_argument("--screenshot", metavar="PATH", help="save one frame of the target window")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

    install_excepthook()

    args = build_parser().parse_args(argv)
    settings, path = config_mod.load(args.config)

    # Fields overridden on the command line are for this run only; they must
    # not be written back to config.json on exit.
    cli_overrides: set[str] = set()
    if args.backend:
        settings.backend = args.backend
        cli_overrides.add("backend")
    if args.width:
        settings.width = args.width
        cli_overrides.add("width")
    if args.height:
        settings.height = args.height
        cli_overrides.add("height")
    if args.target:
        settings.targets = tuple(t.lower() for t in args.target)
        cli_overrides.add("targets")

    if args.list:
        return do_list()
    if args.self_test:
        return do_self_test(settings)
    if args.screenshot:
        hint = settings.targets[0] if settings.targets else ""
        return do_screenshot(settings, args.screenshot, hint)

    # The diagnostics above are one-shot and never touch hotkeys or the tray,
    # so only the long-running mode needs the instance lock.
    if not instance.acquire():
        instance.ping_running_instance(CLASS_NAME)
        log("another instance is already running; announced the existing one")
        return 0

    log(f"SidePeek {__version__} starting")
    log(f"config: {path}")
    log(f"log: {log_path()}")
    log(f"windows build: {sys.getwindowsversion().build}")

    app = App(settings, path, frozenset(cli_overrides))
    return app.run()
