"""Unit tests for hotkey parsing and the PNG diagnostic writer."""

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from sidepeek import win32
from sidepeek.app import parse_hotkey
from sidepeek.png import write_png


class ParseHotkeyTest(unittest.TestCase):
    def test_ctrl_alt_g(self):
        self.assertEqual(
            parse_hotkey("ctrl+alt+g"),
            (win32.MOD_CONTROL | win32.MOD_ALT, ord("G")),
        )

    def test_case_and_spaces_are_ignored(self):
        self.assertEqual(
            parse_hotkey("Ctrl + Shift + F5"),
            (win32.MOD_CONTROL | win32.MOD_SHIFT, 0x74),
        )

    def test_win_key(self):
        self.assertEqual(parse_hotkey("win+g"), (win32.MOD_WIN, ord("G")))

    def test_empty_disables(self):
        self.assertEqual(parse_hotkey(""), (0, 0))

    def test_unknown_chord_yields_no_vk(self):
        self.assertEqual(parse_hotkey("ctrl+alt+nosuchkey"), (win32.MOD_CONTROL | win32.MOD_ALT, 0))


class WritePngTest(unittest.TestCase):
    """The capture diagnostics write PNGs by hand, so the header matters."""

    def _chunks(self, data: bytes):
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        pos, out = 8, []
        while pos < len(data):
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            tag = data[pos + 4:pos + 8]
            payload = data[pos + 8:pos + 8 + length]
            crc = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
            self.assertEqual(crc, zlib.crc32(tag + payload) & 0xFFFFFFFF, "bad CRC")
            out.append((tag, payload))
            pos += 12 + length
        return out

    def test_writes_a_readable_rgb_png(self):
        # 2x2 BGRA, top-down; one pure red pixel at (0,0)
        bgra = bytes([
            0, 0, 255, 255,      # BGRA -> red
            0, 255, 0, 255,      # -> green
            255, 0, 0, 255,      # -> blue
            10, 20, 30, 255,
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.png"
            write_png(str(path), 2, 2, bgra)
            chunks = self._chunks(path.read_bytes())

        self.assertEqual([tag for tag, _ in chunks], [b"IHDR", b"IDAT", b"IEND"])
        width, height, depth, colour_type = struct.unpack(">IIBB", chunks[0][1][:10])
        self.assertEqual((width, height, depth, colour_type), (2, 2, 8, 2))

        raw = zlib.decompress(chunks[1][1])
        self.assertEqual(len(raw), 2 * (1 + 2 * 3))       # filter byte + RGB per row
        self.assertEqual(raw[0], 0)                       # filter: none
        self.assertEqual(raw[1:4], b"\xff\x00\x00")       # BGRA red  -> RGB
        self.assertEqual(raw[4:7], b"\x00\xff\x00")       # BGRA green -> RGB
        self.assertEqual(raw[1 + 6 + 1:1 + 6 + 4], b"\x00\x00\xff")


if __name__ == "__main__":
    unittest.main()
