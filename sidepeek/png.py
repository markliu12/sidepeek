"""Minimal dependency-free PNG writer (used by ``--screenshot`` diagnostics)."""

from __future__ import annotations

import struct
import zlib


def write_png(path: str, width: int, height: int, bgra: bytes) -> None:
    """Write a 24-bit RGB PNG from a top-down BGRA byte buffer."""
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        row = bgra[y * stride:(y + 1) * stride]
        rgb_row = bytearray(width * 3)
        rgb_row[0::3] = row[2::4]
        rgb_row[1::3] = row[1::4]
        rgb_row[2::3] = row[0::4]
        raw.append(0)                      # filter type: none
        raw += rgb_row

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as fh:
        fh.write(data)
