# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed

- The "clear current target" menu item, from both the notification area menu and the thumbnail
  menu. It did not do what its label promised: clearing the remembered target was undone by
  the automatic detection within one poll (~300 ms), which re-selected the same
  monitor-filling window. The only visible effect was hiding the thumbnail. Pinning the window
  you do want with `Ctrl+Alt+L` is the supported way to change targets; a session-scoped
  "ignore this window" behaviour may replace the item later.

### Added

- `fit_aspect` (enabled by default). The thumbnail height now follows the aspect ratio of the
  game instead of assuming 16:9, so 16:10, 21:9 and 4:3 titles fill the frame without black
  bars. The width remains the dimension the user controls.

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

[Unreleased]: https://github.com/markliu12/sidepeek/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/markliu12/sidepeek/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/markliu12/sidepeek/releases/tag/v0.1.0
