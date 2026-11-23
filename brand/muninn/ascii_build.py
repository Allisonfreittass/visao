"""Transforma a ilustração do Muninn numa grade ASCII com a ordem de revelação.

    python brand/muninn/ascii_build.py      # escreve brand/muninn/muninn-ascii.json
    python brand/muninn/ascii_build.py --gif  # e o muninn-ascii.gif (pillow, fonttools, brotli)

O player (muninn_ascii.py) só usa a biblioteca padrão e lê o JSON.
"""

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
SRC = HERE / "muninn-lineart.png"
OUT = HERE / "muninn-ascii.json"
COLS, ROWS = 120, 60  # monospace cells are ~2:1, so this is a square
SCALE = 0.70  # the bird inside the ring, as in the app
CHEST = (0.5, 0.56)  # where the genesis starts, in 0..1
EYE = (0.5208, 0.2935)  # in the source image, 0..1

img = cv2.imread(str(SRC), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
H, W = img.shape
PEAK = 0.5  # cell mean that counts as fully inked


def cell_rect(c, r):
    """Source-pixel rectangle under grid cell (c, r), or None outside the bird."""
    u0 = (c / COLS - 0.5) / SCALE + 0.5
    u1 = ((c + 1) / COLS - 0.5) / SCALE + 0.5
    v0 = (r / ROWS - 0.5) / SCALE + 0.5 + 0.05
    v1 = ((r + 1) / ROWS - 0.5) / SCALE + 0.5 + 0.05
    if u1 <= 0 or v1 <= 0 or u0 >= 1 or v0 >= 1:
        return None
    x0, x1 = max(0, int(u0 * W)), min(W, int(u1 * W))
    y0, y1 = max(0, int(v0 * H)), min(H, int(v1 * H))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


RAMP = " .:-=+*#%@"


def glyph(cov):
    """Classic density ramp: how much line art falls in the cell."""
    v = min(1.0, cov * 2.4) ** 0.85
    return RAMP[int(v * (len(RAMP) - 1))]


grid, order = [], []
for r in range(ROWS):
    row, ords = "", []
    for c in range(COLS):
        rect = cell_rect(c, r)
        ch = " "
        if rect:
            x0, y0, x1, y1 = rect
            ch = glyph(float(img[y0:y1, x0:x1].mean()) / PEAK)
        row += ch
        d = math.hypot((c + 0.5) / COLS - CHEST[0], ((r + 0.5) / ROWS - CHEST[1]) * 1.05)
        ords.append(round(d, 4))
    grid.append(row)
    order.append(ords)

# the ring of traces: 23 marks around, the gap at the top is the name
ring = []
cx, cy = (COLS - 1) / 2, (ROWS - 1) / 2
for i in range(1, 24):
    a = -math.pi / 2 + i * 2 * math.pi / 24
    faint = i in (3, 7, 8, 13, 17, 20)
    for t in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        rad = 0.455 + t * 0.035
        c = round(cx + math.cos(a) * rad * COLS)
        r = round(cy + math.sin(a) * rad * ROWS)
        deg = math.degrees(a) % 180
        if deg < 22.5 or deg >= 157.5:
            ch = "-"
        elif deg < 67.5:
            ch = "\\"
        elif deg < 112.5:
            ch = "|"
        else:
            ch = "/"
        ring.append({"i": i, "c": c, "r": r, "ch": "." if faint else ch})

eye_c = round(((EYE[0] - 0.5) * SCALE + 0.5) * COLS)
eye_r = round(((EYE[1] - 0.05 - 0.5) * SCALE + 0.5) * ROWS)
data = {
    "cols": COLS,
    "rows": ROWS,
    "grid": grid,
    "order": order,
    "ring": ring,
    "eye": [eye_c, eye_r],
    "gap": [round(cx), round(cy - 0.47 * ROWS)],
}
OUT.write_text(json.dumps(data, separators=(",", ":")))
print(f"ok {OUT.name}: {COLS}x{ROWS}")
if "--gif" in sys.argv:
    from ascii_gif import render_gif

    render_gif(HERE / "muninn-ascii.gif")
