"""One-off: turn the GitHub avatar into data/portrait.txt (ASCII art).

Run again only if the avatar changes:  python scripts/make_portrait.py [image]
Pixels close to the flat background colour become spaces; everything else
maps to a character ramp by brightness (bright fur = light glyphs, dark
sunglasses = dense glyphs, which read well on the dark hero card).
"""
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
COLS, ROWS = 56, 30  # glyphs are ~2x taller than wide
RAMP = " .:-=+*#%@"


def main() -> None:
    if len(sys.argv) > 1:
        im = Image.open(sys.argv[1])
    else:
        url = "https://avatars.githubusercontent.com/u/177326497?v=4&s=200"
        im = Image.open(BytesIO(urllib.request.urlopen(url, timeout=30).read()))
    im = ImageOps.autocontrast(im.convert("RGB").resize((COLS, ROWS), Image.LANCZOS), cutoff=1)
    border = [im.getpixel((x, y)) for x in range(COLS) for y in (0, 1)]
    border += [im.getpixel((x, y)) for y in range(ROWS) for x in (0, 1, COLS - 2, COLS - 1)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    lines = []
    for y in range(ROWS):
        row = ""
        for x in range(COLS):
            r, g, b = im.getpixel((x, y))
            dist = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
            if dist < 70:
                row += " "
                continue
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            # dark -> dense, bright -> light but never blank
            row += RAMP[max(1, min(len(RAMP) - 1, int((1 - lum) * (len(RAMP) - 1) + 1.5)))]
        lines.append(row)
    # drop specks: glyphs with fewer than 3 non-blank neighbours
    grid = [list(r) for r in lines]
    def filled(y, x):
        return 0 <= y < ROWS and 0 <= x < COLS and lines[y][x] != " "
    for y in range(ROWS):
        for x in range(COLS):
            if lines[y][x] != " ":
                n = sum(filled(y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
                if n < 3:
                    grid[y][x] = " "
    lines = ["".join(r).rstrip() for r in grid]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    pad = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    lines = [l[pad:] for l in lines]
    (ROOT / "data" / "portrait.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
