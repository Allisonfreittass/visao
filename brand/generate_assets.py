"""Gera os ícones e imagens da marca a partir do anel de rastros e do Muninn (DESIGN.md §5).

    pip install pillow fonttools brotli
    python brand/generate_assets.py

Substitui o antigo generate-assets.swift (que só rodava no macOS). Escreve em brand/,
apps/web/public/ e no AppIcon.appiconset do iPhone. Desenha tudo em 4x e reduz, para bordas lisas.
"""

from __future__ import annotations

import io
import math
import struct
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand"
PUB = ROOT / "apps/web/public"
APPICON = ROOT / "apps/ios/Visao/Assets.xcassets/AppIcon.appiconset"
FONTS = PUB / "fonts"
LINEART = BRAND / "muninn/muninn-lineart.png"

TINTA = (16, 18, 20)
LINHA = (44, 49, 54)
CINZA = (154, 161, 168)
PAPEL = (243, 241, 236)
AMBAR = (240, 162, 59)
FAINT = (3, 7, 8, 13, 17, 20)  # the dim marks, the same in the app
SS = 4  # supersampling


# --- drawing -------------------------------------------------------------------------------


def ring(draw, cx, cy, r_in, r_out, width, color, faint_alpha=0.35, gap=True, bg=TINTA):
    """23 radial marks (the gap at the top is the name), the dim ones blended toward `bg`."""
    for i in range(24):
        if gap and i == 0:
            continue
        a = -math.pi / 2 + i * 2 * math.pi / 24
        c = color
        if i in FAINT:
            c = tuple(round(bg[k] + (color[k] - bg[k]) * faint_alpha) for k in range(3))
        p1 = (cx + math.cos(a) * r_in, cy + math.sin(a) * r_in)
        p2 = (cx + math.cos(a) * r_out, cy + math.sin(a) * r_out)
        draw.line([p1, p2], fill=c, width=round(width))
        for p in (p1, p2):  # round caps
            draw.ellipse(
                [p[0] - width / 2, p[1] - width / 2, p[0] + width / 2, p[1] + width / 2], fill=c
            )


def thin_ring(draw, cx, cy, r, width, color):
    """Below 32 px: a thin circle with its gap (DESIGN.md §5)."""
    gap = 18  # degrees
    draw.arc(
        [cx - r, cy - r, cx + r, cy + r],
        start=-90 + gap / 2,
        end=270 - gap / 2,
        fill=color,
        width=round(width),
    )


def dot(draw, cx, cy, r, color):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def done(im, w, h):
    return im.resize((w, h), Image.LANCZOS)


def rounded_mask(size, radius):
    m = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size * SS - 1, size * SS - 1], radius=radius * SS, fill=255
    )
    return m.resize((size, size), Image.LANCZOS)


def mark(size, *, bg=TINTA, fg=PAPEL, eye=AMBAR, scale=1.0, simple=False):
    """The ring + amber dot on a square, edge to edge (iOS and maskable round it themselves)."""
    s = size * SS
    im = Image.new("RGB", (s, s), bg)
    d = ImageDraw.Draw(im)
    c = s / 2
    if simple:
        thin_ring(d, c, c, s * 0.34 * scale, s * 0.075 * scale, fg)
        dot(d, c, c, s * 0.12 * scale, eye)
    else:
        ring(d, c, c, s * 0.25 * scale, s * 0.36 * scale, s * 0.032 * scale, fg, bg=bg)
        dot(d, c, c, s * 0.055 * scale, eye)
    return done(im, size, size)


def muninn(size, bg=TINTA):
    """Muninn inside the ring, as on the login (DESIGN.md §5): art at 76 %, eye in amber."""
    s = size * SS
    im = Image.new("RGB", (s, s), bg)
    d = ImageDraw.Draw(im)
    c = s / 2
    ring(d, c, c, s * 0.44, s * 0.475, s * 0.009, PAPEL, bg=bg)
    art = Image.open(LINEART).convert("RGB")
    side = round(s * 0.76)
    art = art.resize((side, side), Image.LANCZOS)
    tint = Image.new("RGB", (side, side))
    td = ImageDraw.Draw(tint)
    for y in range(side):  # papel at the top to cinza at the bottom, as in the genesis
        t = y / side
        td.line(
            [(0, y), (side, y)],
            fill=tuple(round(PAPEL[k] + (CINZA[k] - PAPEL[k]) * t * 0.7) for k in range(3)),
        )
    art = ImageChops.multiply(art, tint)
    off = (round(s * 0.12), round(s * 0.12 + s * 0.014))
    base = im.crop((off[0], off[1], off[0] + side, off[1] + side))
    im.paste(ImageChops.lighter(base, art), off)
    ex, ey = s * 0.5158, s * 0.357
    glow = Image.new("L", (s, s), 0)
    ImageDraw.Draw(glow).ellipse(
        [ex - s * 0.016, ey - s * 0.016, ex + s * 0.016, ey + s * 0.016], fill=70
    )
    im.paste(
        Image.new("RGB", (s, s), AMBAR),
        (0, 0),
        glow.resize((s // 8, s // 8)).resize((s, s), Image.BICUBIC),
    )
    dot(d, ex, ey, s * 0.0075, AMBAR)
    return done(im, size, size)


# --- fonts ---------------------------------------------------------------------------------


def font_file(name: str) -> io.BytesIO:
    f = TTFont(FONTS / name)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return buf


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_file(name), size * SS)


def wordmark_svg(text: str = "VISÃO", tracking: float = 0.14) -> str:
    """The codename in Geist Mono caps (DESIGN.md §3), as outlines: no font needed to show it."""
    f = TTFont(FONTS / "geist-mono-latin.woff2")
    upm = f["head"].unitsPerEm
    cmap, gs, hmtx = f.getBestCmap(), f.getGlyphSet(), f["hmtx"]
    asc = f["hhea"].ascent
    x, paths = 0.0, []
    for ch in text:
        gname = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[gname].draw(pen)
        paths.append(
            f'<path transform="translate({x:.0f} {asc}) scale(1 -1)" d="{pen.getCommands()}"/>'
        )
        x += hmtx[gname][0] + tracking * upm
    w = x - tracking * upm
    h = asc - f["hhea"].descent
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h}" '
        'role="img" aria-label="VISÃO">'
        f'<g fill="#F3F1EC">{"".join(paths)}</g></svg>\n'
    )


# --- outputs -------------------------------------------------------------------------------


def save(im: Image.Image, *paths: Path) -> None:
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p, optimize=True)
        print("ok", p.relative_to(ROOT))


def ico(images: list[Image.Image], path: Path) -> None:
    datas = []
    for im in images:
        b = io.BytesIO()
        im.save(b, "PNG")
        datas.append((im.size[0], b.getvalue()))
    out = struct.pack("<HHH", 0, 1, len(datas))
    offset = 6 + 16 * len(datas)
    for size, data in datas:
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out += b"".join(d for _, d in datas)
    path.write_bytes(out)
    print("ok", path.relative_to(ROOT))


def og_image() -> Image.Image:
    w, h = 1200, 630
    im = Image.new("RGB", (w * SS, h * SS), TINTA)
    em = muninn(560).resize((560 * SS, 560 * SS), Image.LANCZOS)
    im.paste(em, (40 * SS, 35 * SS))
    d = ImageDraw.Draw(im)
    x = 640 * SS
    d.text((x, 150 * SS), "VISÃO", font=font("geist-mono-latin.woff2", 22), fill=PAPEL, spacing=0)
    d.text(
        (x, 200 * SS), "Nasce sem nome.", font=font("newsreader-300-latin.woff2", 58), fill=PAPEL
    )
    d.text(
        (x, 270 * SS),
        "Lembra só do que",
        font=font("newsreader-300-italic-latin.woff2", 58),
        fill=CINZA,
    )
    d.text(
        (x, 340 * SS),
        "você deixar.",
        font=font("newsreader-300-italic-latin.woff2", 58),
        fill=CINZA,
    )
    mono = font("geist-mono-latin.woff2", 17)
    d.text((x, 450 * SS), "Virtual Intelligence with", font=mono, fill=CINZA)
    d.text((x, 476 * SS), "Supervised Autonomy & Opt-in memory", font=mono, fill=CINZA)
    d.line([(x, 430 * SS), (x + 48 * SS, 430 * SS)], fill=AMBAR, width=2 * SS)
    return done(im, w, h)


def main() -> None:
    # iPhone (1024, edge to edge: iOS rounds the corners).
    # Dark: a deeper ground. Tinted: grey on black, iOS colours it.
    normal = mark(1024)
    dark = mark(1024, bg=(8, 9, 10))
    tinted = mark(1024, bg=(0, 0, 0), fg=(255, 255, 255), eye=(255, 255, 255))
    save(normal, APPICON / "AppIcon.png", BRAND / "app-icon.png")
    save(dark, APPICON / "AppIcon-dark.png", BRAND / "app-icon-dark.png")
    save(tinted, APPICON / "AppIcon-tinted.png", BRAND / "app-icon-tinted.png")

    # Web / PWA.
    save(mark(180), PUB / "apple-touch-icon.png")
    for size in (192, 512):
        im = mark(size).convert("RGBA")
        im.putalpha(rounded_mask(size, round(size * 0.225)))
        save(im, PUB / f"icon-{size}.png")
    save(mark(512, scale=0.82), PUB / "maskable-512.png")  # inside the 80 % safe zone
    ico([mark(16, simple=True), mark(32, simple=True), mark(48)], PUB / "favicon.ico")

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect width="100" height="100" rx="22" fill="#101214"/>'
        '<path d="M 55.3 15.4 A 35 35 0 1 1 44.7 15.4" fill="none" stroke="#F3F1EC" '
        'stroke-width="7" stroke-linecap="round"/>'
        '<circle cx="50" cy="50" r="11" fill="#F0A23B"/></svg>\n'
    )
    for p in (PUB / "favicon.svg", BRAND / "favicon.svg"):
        p.write_text(svg)
        print("ok", p.relative_to(ROOT))

    (BRAND / "visao-wordmark.svg").write_text(wordmark_svg())
    print("ok brand/visao-wordmark.svg")
    save(muninn(512), BRAND / "muninn-512.png")
    og = og_image()
    save(og, BRAND / "og-image.png", PUB / "og-image.png")


if __name__ == "__main__":
    main()
