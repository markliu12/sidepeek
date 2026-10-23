# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.1] - 2026-10-23

### Added

- Optional Bark phone notifications for detected CS2 round results, with a tray-menu test action.
- **Round-result wording follows the banner.** A simplified-Chinese client is
  notified in simplified Chinese, a traditional one in traditional, and
  `ROUND WIN` / `ROUND LOSS` in English, so the toast (and the Bark push) matches
  what the player just read on screen instead of always being Chinese. The new
  `notification_language` setting (`auto` by default, or `zh-CN` / `zh-TW` / `en`)
  pins one language; locale spellings such as `en-US` or `zh-Hant` are accepted.
  Verdicts that come from the colour fallback carry no text, so they use the OCR
  engine's own language, or the pinned one.
- **The language is also a tray-menu entry.** Right-click the tray icon ->
  `提醒语言` -> `自动（跟随游戏语言）` / `简体中文` / `繁體中文` / `English`. The
  choice is saved to `config.json` and applies to the next round; no restart.

### Changed

- **English banners are recognised too.** `ROUND WIN` / `ROUND LOSS` — any case,
  plus the `won` / `lost` variants — now map onto the same results. The trailing
  word boundary keeps scoreboard columns such as `ROUND LOSSES` and `Round Wins`
  out. Verified end to end: Windows' `zh-Hans-CN` engine reads Latin text
  perfectly, so no second OCR engine is created and nothing gets slower.
- **A Latin-only OCR engine no longer silences Chinese clients.** If the machine
  has `en-US` but no Chinese recogniser, an empty reading is not treated as
  "no banner" any more — the colour probe stays enabled for that configuration.
- **Recognition is more forgiving of OCR noise.** A round now counts when `回合`
  is followed by any result character within three characters, so a label with
  one mangled glyph (`回合失畋`) still resolves. The team line `反恐精英胜利` still
  cannot match, because it never contains `回合`.
- **The crop is upscaled 2x before OCR.** Measured on Chinese UI text: at a
  24-32 px line height the 1x path returned nothing while the 2x path returned
  readable text; from 48 px up both worked. Windows' engine is simply better on
  larger glyphs, and the crop is only a few hundred pixels wide.
- **The banner band is taller and wider** (y 10-34%, x 32-68%). 16:10 displays
  place the banner at a different relative height than 16:9, and HUD scaling
  moves it as well, so the band now leaves room instead of hugging the label.
- Windows' `get_software_bitmap_transformed_async` needs its five positional
  arguments in this projection order — `(pixel_format, alpha_mode, transform,
  exif_orientation, color_management)`. Nothing else returns a scaled bitmap.

### Fixed

- **Round notifications fired while no round was over.** The colour probe ran
  whenever OCR failed to *classify* the crop, including when OCR read nothing at
  all. Two cases were reported in one evening: the CS2 main menu, which is a live
  render of a map whose rusty red walls cleared the coverage threshold with the
  game sitting idle, and an Inferno-style orange wall mid-round. A round banner
  always carries a label and a map texture does not, so colour is now only
  consulted when Windows OCR cannot produce a verdict at all - when no Chinese
  OCR engine is installed, or when it throws on a frame. When OCR works, its
  answer is final, including "this is not a round result". Detection log lines
  now include the recognised text.

## [0.5.0] - 2026-10-23

### Added

- **CS2 round-end notifications.** While CS2 sits in the background, a sampling
  loop reads the round-result banner in the centre of the screen and sends one
  Windows app notification per round — `CS2 回合胜利` or `CS2 回合失败`. Chinese
  text is read with the built-in Windows OCR engine, with a red/yellow banner
  colour probe as the fallback for stylized fonts, and both simplified and
  traditional wording is recognized. The tray menu can turn the feature off.
- **Type checking.** `mypy` runs over the source with a dedicated configuration
  (`mypy.ini`) and as a separate CI job, catching type errors in the `ctypes`
  layer before they ship.
- **More targeted tests** for the capture path — the blank-frame heuristic and
  the `grab` short-circuits — and for the `hide_when_hovered` / hidden-window
  branches of the watch decision.
- **Executable smoke test in CI.** The packaged build now runs
  `SidePeek.exe --list` on the build runner, so a broken bundle (missing import,
  bad `ctypes` binding, ...) fails the build instead of shipping silently.

### Changed

- **Less work per frame for the `capture` backend.** The frame timer now
  invalidates only the picture rectangle instead of the whole overlay, so the
  caption strip is no longer repainted at frame rate. Process image names are
  cached by PID, which removes one `OpenProcess` + `QueryFullProcessImageNameW`
  round-trip per window on every fallback enumeration, and the blank-frame
  sanity check reads the frame through a `memoryview` instead of a per-pixel
  Python loop.
- **One asyncio loop for the round monitor** instead of building a new one twice
  a second, and the "detected" log line now records whether OCR or the colour
  probe produced the hit.

### Fixed

- **CS2 notifications never appeared as Windows toasts.** The parameterless
  `ToastNotificationManager.CreateToastNotifier()` resolves the app id from a
  Start Menu shortcut that matches the *running process* and fails with
  `ERROR_NOT_FOUND (0x80070490)` for an unpackaged exe, so every round silently
  degraded to a tray balloon. The app id is now passed explicitly
  (`CreateToastNotifier(AUMID)`), which is the documented path for desktop apps.
- **One round could notify three times.** The banner fades in and out over a few
  seconds; frames around the fade dropped below the colour detector's threshold,
  re-armed the latch and fired again 4-10 s later. A round-end cooldown
  (`MIN_NOTIFY_INTERVAL`, 10 s) now swallows those repeats, and the latch needs a
  longer stable absence before it re-arms.
- **Colour fallback fired on blood and red map props.** The probe accepted 2% of
  banner-coloured pixels inside a large box; a real banner fills a big block, so
  the bar is now 10% coverage plus a 2.5x dominance margin over the other colour.
- **Simplified Chinese banners were never matched.** Only `回合勝利` / `回合落敗`
  were recognized, so a client running in simplified Chinese (whose OCR engine was
  also selected as `zh-Hans-CN`) could only ever be detected by colour. Both
  scripts, and the `回合失败` variant, now map onto one canonical result.

## [0.4.0] - 2026-10-21

### Added

- **Single instance.** A named mutex keeps a second copy from running: it would otherwise
  fight the first one for the global hotkeys and leave a second notification-area icon
  behind. Starting the program again makes the running copy show a balloon pointing at
  its icon, and the new process exits with code 0. The command-line diagnostics are
  exempt, so they stay usable while the program runs.
- **Log file.** Everything that used to go to stdout — startup, target changes, hotkey
  conflicts, resume handling — is also appended to
  `%LOCALAPPDATA%\SidePeek\sidepeek.log`, rolled over at 512 KB. Unhandled exceptions are
  written there and shown in a message box; the windowed build used to fail silently.
- **Run at login** in the notification area menu, backed by a per-user
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` entry, so no administrator rights
  are involved. Off by default: nothing is written to the registry until the entry is
  clicked, and clicking it again removes the value.
- **Fit to the picture** (`按画面比例自适应`) in both context menus. Dragging the resize
  handle now turns `fit_aspect` off — a size picked by hand must not be overridden the
  next time the thumbnail appears — which makes this entry the way back.
- Hotkey registration failures are reported with a notification-area balloon. With
  `console=False` the old console line was invisible to everyone running the executable.

### Changed

- `fit_aspect` is now persisted with the rest of the layout instead of being read-only.

### Fixed

- Rounded corners were lost after a resize on Windows 10, which falls back to a window
  region: the region was built once in `create()` and never rebuilt in `WM_SIZE`.
- A frozen or black picture after resuming from sleep. Thumbnails do not survive a
  suspend/resume cycle and `show_target` returned early for an unchanged target, so
  nothing ever re-registered them; `WM_POWERBROADCAST` now forces a fresh attach.
- Minimising the thumbnail collapsed the stored size to the 160 × 90 minimum, because
  `WM_SIZE` treated the zero-sized client area of a minimised window as a real size.

## [0.3.0] - 2026-10-21

### Added

- **Target picker.** Both menus gained a `监视窗口` submenu listing every window that can be
  watched, largest first, with the current target marked. Selecting one pins it; selecting
  `自动` releases the pin and returns to automatic detection. This is the multi-game case:
  choosing from a list instead of remembering which window `Ctrl+Alt+L` last pinned, and it
  also supplies the "unlock" action that was missing after the clear-target removal.
- `fit_aspect` (enabled by default). The thumbnail height now follows the aspect ratio of the
  game instead of assuming 16:9, so 16:10, 21:9 and 4:3 titles fill the frame without black
  bars. The width remains the dimension the user controls.

### Removed

- The "clear current target" menu item, from both the notification area menu and the thumbnail
  menu. It did not do what its label promised: clearing the remembered target was undone by
  the automatic detection within one poll (~300 ms), which re-selected the same
  monitor-filling window. The only visible effect was hiding the thumbnail. Pinning the window
  you do want with `Ctrl+Alt+L` is the supported way to change targets; a session-scoped
  "ignore this window" behaviour may replace the item later.

## [0.2.0] - 2026-10-21

### Added

- Notification area icon, available for as long as the program runs, including while the
  thumbnail is hidden. Right-click opens a menu with return to game, clear target,
  pause/resume and quit; double-click toggles monitoring; the tooltip reports the state.
  The icon is restored automatically when Explorer restarts.
- `CHANGELOG.md`, and a test that keeps `version_info.txt` in sync with
  `sidepeek.__version__`.

### Changed

- Default thumbnail size changed from 480 x 270 to 492 x 304. Border padding and the
  caption strip are subtracted from the window, so the previous default left a 468 x 236
  picture area (1.98:1) and pillarboxed 16:9 games. The new default leaves exactly
  480 x 270 of picture. Existing installations keep their saved size.

### Fixed

- The elapsed-time label in the caption strip never updated when the `dwm` backend was in
  use; nothing repainted the window in that mode.
- `--width`, `--height`, `--backend` and `--target` were written back to `config.json` on
  exit, so a one-off override became permanent.
- The thumbnail could be resized below the point where the resize handle remained
  reachable, and the resulting size was persisted.
- Starting the program after switching away from the game displayed nothing, because no
  fullscreen window had been observed in the foreground yet.
- A target window that had been destroyed was retained in the internal state when the game
  recreated its window at a different resolution.

## [0.1.0] - 2026-10-21

### Added

- Initial release. Live thumbnail of the game window while it is in the background, using
  `DwmRegisterThumbnail` with a `PrintWindow` capture fallback.
- Event-driven watcher (`EVENT_SYSTEM_FOREGROUND`) with a polling fallback, zero-config
  fullscreen detection, process allowlist and a hotkey to lock the current window.
- Frameless topmost thumbnail: drag, resize, click to return to the game, context menu,
  caption strip with process name and elapsed time.
- Global hotkeys: `Ctrl+Alt+G` pause, `Ctrl+Alt+L` lock, `Ctrl+Alt+Q` quit.
- Diagnostics: `--list`, `--self-test`, `--screenshot`.
- Standalone Windows executable with an icon and a version resource.
- Unit test suite and continuous integration on Python 3.9, 3.11 and 3.13.

[Unreleased]: https://github.com/markliu12/sidepeek/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/markliu12/sidepeek/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/markliu12/sidepeek/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/markliu12/sidepeek/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/markliu12/sidepeek/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/markliu12/sidepeek/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/markliu12/sidepeek/releases/tag/v0.1.0
