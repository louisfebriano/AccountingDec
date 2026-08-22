"""Generate deterministic CatatKas PNG icons without external dependencies."""

from pathlib import Path
import struct
import zlib


ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "pwa" / "icons"
BACKGROUND = (31, 122, 91)
FOREGROUND = (246, 247, 242)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _scaled_rect(rect: tuple[int, int, int, int], size: int, safe_scale: float) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = rect
    values = []
    for index, value in enumerate((x1, y1, x2, y2)):
        centered = 50 + (value - 50) * safe_scale
        pixel = round(centered * size / 100)
        values.append(max(0, min(size, pixel)))
    return tuple(values)


def generate_icon(path: Path, size: int, safe_scale: float = 1.0) -> None:
    """Write a flat green icon with a geometric CK monogram."""
    pixels = [list(BACKGROUND) for _ in range(size * size)]
    strokes = (
        (18, 26, 26, 68),
        (25, 18, 44, 26),
        (25, 68, 44, 76),
        (55, 18, 63, 76),
        (63, 43, 70, 51),
        (69, 35, 76, 43),
        (75, 27, 82, 35),
        (69, 51, 76, 59),
        (75, 59, 82, 76),
    )
    for stroke in strokes:
        x1, y1, x2, y2 = _scaled_rect(stroke, size, safe_scale)
        for y in range(y1, y2):
            offset = y * size
            for x in range(x1, x2):
                pixels[offset + x] = list(FOREGROUND)

    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw.extend(pixels[y * size + x])

    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    generate_icon(ICON_DIR / "icon-192.png", 192)
    generate_icon(ICON_DIR / "icon-512.png", 512)
    generate_icon(ICON_DIR / "icon-maskable-512.png", 512, safe_scale=0.78)


if __name__ == "__main__":
    main()
