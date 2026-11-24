#!/usr/bin/env python3
"""Draw the front page that sums up the world news of Tuesday 24 November 2026.

The program draws one 1024x1024 PNG with the Python standard library plus
Pillow when it is available, and writes it to $MAKEFUN_OUTPUT_DIR/entry.png
(or /output/entry.png). No network, no clock, no randomness: the same input
always produces the same bytes.

Layout: a newspaper front page. A masthead, the date as a full-width banner
headline, one English subtitle line, a black dateline bar, then six stories
in a 2x3 grid. Each story has a colour-coded pictogram drawn from shapes,
a region tag, a two-line headline and a one-line fact. All text is drawn
by the program itself, so no letter is ever a blurry generated glyph.

The six stories were all verified against reporting dated 24 November 2026:
Gaza (Reuters), Zaporizhzhia (Reuters), Asian markets (AP), South Korea
air-defence zone (AP), Malaysia repatriations (AP / The Guardian) and the
Sanofi-Insmed deal (Sanofi press release, 24 November 2026).

If Pillow is missing, a pure standard-library rasterizer built into this
file draws the same page with an embedded 5x7 bitmap font, so the entry
still produces a valid image in a bare Python 3.13 container.
"""

import hashlib
import math
import os
import struct
import sys
import zlib
from pathlib import Path

W = 1024
H = 1024

BLACK = (17, 17, 17)
DARK = (51, 51, 51)
GRAY = (110, 110, 110)
WHITE = (255, 255, 255)

MASTHEAD = "THE WORLD IN ONE PAGE"
DATE_LINE = "24 NOVEMBER 2026"
SUBTITLE = "Six stories, from Gaza to Seoul"
DATELINE_LEFT = "TUESDAY, 24 NOVEMBER 2026"
DATELINE_RIGHT = "SIX STORIES - ONE PAGE"
FOOTER = "Sources: Reuters, AP, Al Jazeera, Sanofi"

# tag, colour, icon, headline, one-line fact.
STORIES = [
    ("GAZA", (163, 22, 33), "burst",
     "Israel kills Hamas security chief", "Seven dead in Gaza"),
    ("UKRAINE", (29, 78, 137), "building",
     "Russian strike hits flats in Zaporizhzhia", "Two dead, 40 wounded"),
    ("MARKETS", (30, 122, 52), "chart",
     "Asian stocks surge on Huang's return", "Taiex +9%, Kospi +6%"),
    ("KOREA", (194, 94, 0), "plane",
     "Russian jets enter Korean air zone", "Alert lifted in minutes"),
    ("MALAYSIA", (15, 118, 110), "ship",
     "Malaysia to send 6,803 back to Myanmar", "Returns in December"),
    ("PHARMA", (109, 40, 217), "capsule",
     "Sanofi agrees $41bn buy of Insmed", "$175 a share, in cash"),
]


# ---------------------------------------------------------------------------
# Text helpers (backend-agnostic: they only call cv.text_width)
# ---------------------------------------------------------------------------

def wrap_words(text, measure, max_w):
    """Greedy word wrap. measure(word) gives a word's width in pixels."""
    lines = []
    current = ""
    for word in text.split(" "):
        trial = word if not current else current + " " + word
        if measure(trial) <= max_w or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_block(cv, text, kind, start_size, max_w, max_lines, min_size=24):
    """Largest size at which text wraps into at most max_lines lines."""
    size = start_size
    while size > min_size:
        if len(wrap_words(text, lambda t: cv.text_width(t, kind, size), max_w)) <= max_lines:
            return size
        size -= 1
    return size


def fit_single(cv, text, kind, start_size, max_w, min_size=24):
    """Largest size at which text fits on one line."""
    size = start_size
    while size > min_size and cv.text_width(text, kind, size) > max_w:
        size -= 1
    return size


# ---------------------------------------------------------------------------
# Icons: white pictograms drawn from shapes, centred on (cx, cy).
# ---------------------------------------------------------------------------

def draw_icon(cv, kind, cx, cy, disc_color):
    if kind == "burst":
        pts = []
        for k in range(16):
            ang = math.radians(k * 22.5 - 90.0)
            r = 24 if k % 2 == 0 else 10
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        cv.polygon(pts, WHITE)
        cv.disc(cx, cy, 4, disc_color)
    elif kind == "building":
        cv.rect(cx - 21, cy - 16, cx - 9, cy + 20, WHITE)
        cv.rect(cx - 5, cy - 2, cx + 6, cy + 20, WHITE)
        cv.rect(cx + 10, cy + 6, cx + 21, cy + 20, WHITE)
        cv.rect(cx - 18, cy - 10, cx - 12, cy - 4, disc_color)
        cv.rect(cx - 2, cy + 4, cx + 3, cy + 10, disc_color)
    elif kind == "chart":
        cv.line(cx - 22, cy + 14, cx - 8, cy, WHITE, 5)
        cv.line(cx - 8, cy, cx + 4, cy + 6, WHITE, 5)
        cv.line(cx + 4, cy + 6, cx + 20, cy - 16, WHITE, 5)
        cv.line(cx + 20, cy - 16, cx + 8, cy - 14, WHITE, 5)
        cv.line(cx + 20, cy - 16, cx + 18, cy - 4, WHITE, 5)
    elif kind == "plane":
        cv.polygon([(cx + 22, cy - 20), (cx - 20, cy + 8),
                    (cx - 10, cy + 16), (cx, cy + 2)], WHITE)
    elif kind == "ship":
        cv.polygon([(cx - 22, cy + 8), (cx + 22, cy + 8),
                    (cx + 16, cy + 20), (cx - 16, cy + 20)], WHITE)
        cv.line(cx, cy + 8, cx, cy - 20, WHITE, 3)
        cv.polygon([(cx + 2, cy - 20), (cx + 2, cy + 6), (cx + 16, cy + 6)], WHITE)
    elif kind == "capsule":
        cv.disc(cx - 14, cy, 8, WHITE)
        cv.disc(cx + 14, cy, 8, WHITE)
        cv.rect(cx - 14, cy - 8, cx + 14, cy + 8, WHITE)
        cv.line(cx, cy - 8, cx, cy + 8, disc_color, 3)


# ---------------------------------------------------------------------------
# Page layout. Only uses the Canvas methods below, so both backends draw
# exactly the same page.
# ---------------------------------------------------------------------------

def draw_story(cv, x, y, story):
    tag, color, icon, headline, detail = story
    w, h = 478, 228
    cv.rect(x, y, x + w, y + 6, color)
    cv.disc(x + 48, y + 50, 34, color)
    draw_icon(cv, icon, x + 48, y + 50, color)
    cv.text(x + 96, y + 36, tag, "sans_bold", 30, color, "left")
    size = fit_block(cv, headline, "sans_bold", 36, 450, 2)
    lines = wrap_words(headline, lambda t: cv.text_width(t, "sans_bold", size), 450)
    ly = y + 94
    for ln in lines[:2]:
        cv.text(x + 14, ly, ln, "sans_bold", size, BLACK, "left")
        ly += size + 6
    dsize = fit_single(cv, detail, "sans", 36, 450)
    cv.text(x + 14, y + 184, detail, "sans", dsize, DARK, "left")


def draw_page(cv):
    cv.rect(0, 0, W, H, WHITE)
    cv.outline(12, 12, 1012, 1012, BLACK, 3)
    msize = fit_single(cv, MASTHEAD, "serif_bold", 44, 976)
    cv.text(512, 28, MASTHEAD, "serif_bold", msize, BLACK, "center")
    cv.line(24, 82, 1000, 82, BLACK, 2)
    dsize = fit_single(cv, DATE_LINE, "sans_bold", 104, 976)
    cv.text(512, 92, DATE_LINE, "sans_bold", dsize, BLACK, "center")
    ssize = fit_single(cv, SUBTITLE, "serif", 30, 976)
    cv.text(512, 200, SUBTITLE, "serif", ssize, DARK, "center")
    cv.rect(24, 238, 1000, 268, BLACK)
    cv.text(40, 244, DATELINE_LEFT, "sans_bold", 23, WHITE, "left")
    cv.text(984, 244, DATELINE_RIGHT, "sans_bold", 23, WHITE, "right")
    for i, story in enumerate(STORIES):
        row, col = divmod(i, 2)
        draw_story(cv, 24 + col * 498, 276 + row * 234, story)
    fsize = fit_single(cv, FOOTER, "sans", 20, 976)
    cv.text(512, 982, FOOTER, "sans", fsize, GRAY, "center")


# ---------------------------------------------------------------------------
# Backend 1: Pillow (preferred, smooth anti-aliased text).
# ---------------------------------------------------------------------------

FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/noto",
    "/usr/local/share/fonts",
]
FONT_FILES = {
    "serif_bold": ["DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf",
                   "NotoSerif-Bold.ttf"],
    "serif": ["DejaVuSerif.ttf", "LiberationSerif-Regular.ttf",
              "NotoSerif-Regular.ttf"],
    "sans_bold": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
                  "NotoSans-Bold.ttf"],
    "sans": ["DejaVuSans.ttf", "LiberationSans-Regular.ttf",
             "NotoSans-Regular.ttf"],
}


def find_font(kind):
    import os as _os
    for name in FONT_FILES[kind]:
        for d in FONT_DIRS:
            p = _os.path.join(d, name)
            if _os.path.isfile(p):
                return p
    return None


class PilCanvas:
    def __init__(self):
        from PIL import Image, ImageDraw, ImageFont
        self._Image = Image
        self._ImageDraw = ImageDraw
        self._ImageFont = ImageFont
        self.image = Image.new("RGB", (W, H), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self._paths = {k: find_font(k) for k in FONT_FILES}
        self._cache = {}

    def _font(self, kind, size):
        key = (kind, size)
        if key not in self._cache:
            path = self._paths[kind]
            if path:
                self._cache[key] = self._ImageFont.truetype(path, size)
            else:
                self._cache[key] = self._ImageFont.load_default(size=size)
        return self._cache[key]

    def text_width(self, s, kind, size):
        return self._font(kind, size).getlength(s)

    def _xy(self, x, y, s, kind, size, anchor):
        w = self.text_width(s, kind, size)
        if anchor == "center":
            x = x - w / 2.0
        elif anchor == "right":
            x = x - w
        return x, y

    def text(self, x, y, s, kind, size, color, anchor="left"):
        font = self._font(kind, size)
        ax = {"left": "l", "center": "m", "right": "r"}[anchor]
        self.draw.text((x, y), s, font=font, fill=color, anchor=ax + "a")

    def rect(self, x0, y0, x1, y1, color):
        self.draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=color)

    def outline(self, x0, y0, x1, y1, color, width):
        for i in range(width):
            self.draw.rectangle([x0 + i, y0 + i, x1 - 1 - i, y1 - 1 - i],
                                outline=color)

    def line(self, x0, y0, x1, y1, color, width):
        self.draw.line([(x0, y0), (x1, y1)], fill=color, width=width)

    def disc(self, cx, cy, r, color):
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    def polygon(self, pts, color):
        self.draw.polygon([(px, py) for px, py in pts], fill=color)

    def png_bytes(self):
        import io
        buf = io.BytesIO()
        self.image.save(buf, format="PNG")
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Backend 2: pure standard library (used only when Pillow is unavailable).
# An embedded 5x7 bitmap font, a small rasterizer and a minimal PNG encoder.
# ---------------------------------------------------------------------------

GLYPHS = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ",": ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
    "'": ("00100", "00100", "01000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "$": ("00100", "01111", "10100", "01110", "00101", "11110", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00110", "00100", "00000", "00100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    ";": ("00000", "01100", "01100", "00000", "01100", "00100", "01000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "&": ("01100", "10010", "10100", "01000", "10101", "10010", "01101"),
}


def _chunk(kind, data):
    out = kind + data
    return struct.pack(">I", len(data)) + out + struct.pack(
        ">I", zlib.crc32(out) & 0xFFFFFFFF)


def encode_png(buf, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += buf[y * w * 3:(y + 1) * w * 3]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    return png


class StdCanvas:
    def __init__(self):
        self.buf = bytearray([255]) * (W * H * 3)

    def _px(self, x, y, color):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 3
            self.buf[i:i + 3] = bytes(color)

    def rect(self, x0, y0, x1, y1, color):
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(W, x1)):
                self._px(x, y, color)

    def outline(self, x0, y0, x1, y1, color, width):
        for i in range(width):
            self.rect(x0 + i, y0 + i, x1 - i, y0 + i + 1, color)
            self.rect(x0 + i, y1 - 1 - i, x1 - i, y1 - i, color)
            self.rect(x0 + i, y0 + i, x0 + i + 1, y1 - i, color)
            self.rect(x1 - 1 - i, y0 + i, x1 - i, y1 - i, color)

    def disc(self, cx, cy, r, color):
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(r * r - dy * dy))
            for x in range(cx - dx, cx + dx + 1):
                self._px(x, cy + dy, color)

    def line(self, x0, y0, x1, y1, color, width):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        r = max(0, (width - 1) // 2)
        while True:
            self.disc(x0, y0, r, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def polygon(self, pts, color):
        pts = [(int(px), int(py)) for px, py in pts]
        if not pts:
            return
        ymin = max(0, min(p[1] for p in pts))
        ymax = min(H - 1, max(p[1] for p in pts))
        n = len(pts)
        for y in range(ymin, ymax + 1):
            xs = []
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                for x in range(int(math.ceil(xs[i])), int(xs[i + 1]) + 1):
                    self._px(x, y, color)

    @staticmethod
    def _scale(size):
        return max(1, round(size / 7.0))

    def text_width(self, s, kind, size):
        sc = self._scale(size)
        return len(s.upper()) * 6 * sc - sc

    def text(self, x, y, s, kind, size, color, anchor="left"):
        s = s.upper()
        sc = self._scale(size)
        w = self.text_width(s, kind, size)
        if anchor == "center":
            x = int(x - w / 2)
        elif anchor == "right":
            x = int(x - w)
        x, y = int(x), int(y)
        for ci, ch in enumerate(s):
            glyph = GLYPHS.get(ch, GLYPHS[" "])
            ox = x + ci * 6 * sc
            for row in range(7):
                bits = glyph[row]
                for col in range(5):
                    if bits[col] == "1":
                        self.rect(ox + col * sc, y + row * sc,
                                  ox + (col + 1) * sc, y + (row + 1) * sc,
                                  color)

    def png_bytes(self):
        return encode_png(self.buf, W, H)


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

def build_png_bytes():
    try:
        from PIL import Image  # noqa: F401  (availability probe only)
        canvas = PilCanvas()
    except ImportError:
        canvas = StdCanvas()
    draw_page(canvas)
    return canvas.png_bytes()


def main():
    out_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "entry.png"
    data = build_png_bytes()
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"wrote {target} bytes={len(data)} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
