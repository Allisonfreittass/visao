"""Renders the ASCII genesis as a GIF for the README (Geist Mono, the app's colours)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import muninn_ascii as player
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = HERE.parents[1] / "apps/web/public/fonts/geist-mono-latin.woff2"
TINTA = (16, 18, 20)
FPS = 15


def _font(size: int) -> ImageFont.FreeTypeFont:
    f = TTFont(FONT)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, size)


def render_gif(path: Path) -> None:
    g = player.Genesis(json.loads(player.DATA.read_text()))
    font = _font(14)
    cw, lh, pad = round(font.getlength("M")), 17, 24
    w, h = g.cols * cw + 2 * pad, (g.rows + 2) * lh + 2 * pad

    def frame(t: float) -> Image.Image:
        im = Image.new("RGB", (w, h), TINTA)
        d = ImageDraw.Draw(im)
        for r, row in enumerate(g.frame(t)):
            for c, (ch, rgb) in enumerate(row):
                if ch != " ":
                    d.text((pad + c * cw, pad + r * lh), ch, font=font, fill=rgb)
        return im

    frames = [frame(i / FPS) for i in range(int(player.TOTAL * FPS) + 1)]
    durations = [round(1000 / FPS)] * (len(frames) - 1) + [3000]
    palette = frames[-1].quantize(colors=32, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=True)
    print(f"ok {path.name}: {len(frames)} quadros")
