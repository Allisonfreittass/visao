"""Gera os ícones do app a partir do corvo de olho âmbar (DESIGN.md §5).

    pip install pillow cairosvg
    python brand/generate_assets.py

As fontes são os dois desenhos em vetor de brand/simbolo/: `corvo-olho-pequeno.svg` (corte fechado
na cabeça, só o olho e o bico) até 48 px, e `corvo-olho-icone.svg` de 64 px para cima. Cada tamanho
sai direto do vetor, sem reduzir um PNG grande. Escreve em apps/web/public/ (os dois SVGs vão para
marca/, de onde o <Corvo> os lê) e os ícones do app de Mac em desktop/app/src-tauri/icons/ (o
.icns inclusive, sem o `tauri icon`). O cairosvg precisa do libcairo do sistema.
"""

from __future__ import annotations

import io
import re
import struct
from pathlib import Path

import cairosvg
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SIMBOLO = ROOT / "brand/simbolo"
PUB = ROOT / "apps/web/public"
DESKTOP = ROOT / "desktop/app"
TAURI_ICONS = DESKTOP / "src-tauri/icons"

PAPEL = (243, 241, 236)  # #F3F1EC, the ground of the drawing
SMALL_MAX = 48  # px: up to here, the close crop of the head


def svg(small: bool) -> str:
    name = "corvo-olho-pequeno.svg" if small else "corvo-olho-icone.svg"
    return (SIMBOLO / name).read_text()


def render(size: int, *, rounded: bool = True, small: bool | None = None) -> Image.Image:
    """The drawing at `size`, straight from the vector: the close crop up to SMALL_MAX unless
    `small` says otherwise. Rounded: the corners it carries, transparent around them. Not rounded:
    edge to edge, for whoever masks the icon (iOS, Android)."""
    source = svg(size <= SMALL_MAX if small is None else small)
    if not rounded:
        source = re.sub(r'\s*clip-path="url\(#c\)"', "", source)
    png = cairosvg.svg2png(bytestring=source.encode(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def maskable(size: int, scale: float = 0.84) -> Image.Image:
    """Android's safe zone is the centered circle of 80 %. The crow runs off the bottom and the
    left, so the drawing shrinks into that corner and paper fills the rest: the head, the eye and
    the tip of the beak stay inside the circle, and no cut edge shows."""
    inner = round(size * scale)
    out = Image.new("RGBA", (size, size), (*PAPEL, 255))
    out.alpha_composite(render(inner, rounded=False), (0, size - inner))
    return out.convert("RGB")


def mac_icon(points: int, scale: int = 1) -> Image.Image:
    """The Mac app's icon on Apple's grid: the macOS does not round or inset icons, so the
    drawing sits as a rounded square of 824/1024 of the side, with a soft shadow under it.

    The drawing goes by the size in points, not in pixels: at 16 and 32 pt (Finder lists, the
    menu bar, Spotlight) the close crop, also in the 2x pixels of a Retina screen, so a slot never
    swaps drawings between screens; from 128 pt, the whole crow."""
    canvas = points * scale
    body = round(canvas * 824 / 1024)
    art = render(body, small=points <= SMALL_MAX)
    at = (canvas - body) // 2
    alpha = art.getchannel("A").point(lambda v: v * 90 // 255)
    shape = Image.new("RGBA", (body, body), (0, 0, 0, 0))
    shape.putalpha(alpha)
    shadow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shadow.paste(shape, (at, at + round(canvas * 12 / 1024)), shape)
    out = shadow.filter(ImageFilter.GaussianBlur(canvas * 14 / 1024))
    out.alpha_composite(art, (at, at))
    return out


def packbits(channel: bytes) -> bytes:
    """Apple's run-length code for the old 16 and 32 px icns entries (is32, il32)."""
    out, i = bytearray(), 0
    while i < len(channel):
        run = 1
        while i + run < len(channel) and run < 130 and channel[i + run] == channel[i]:
            run += 1
        if run >= 3:
            out += bytes((run + 125, channel[i]))
            i += run
            continue
        start = i
        while i < len(channel) and i - start < 128:
            if i + 2 < len(channel) and channel[i] == channel[i + 1] == channel[i + 2]:
                break
            i += 1
        out += bytes((i - start - 1,)) + channel[start:i]
    return bytes(out)


def icns(path: Path) -> None:
    """The Mac's .icns, with the same entries `tauri icon` writes: the old RGB + mask pairs for
    16 and 32 px and a PNG for each other size, each from mac_icon at its size in points."""

    def png(im: Image.Image) -> bytes:
        b = io.BytesIO()
        im.save(b, "PNG", optimize=True)
        return b.getvalue()

    def legacy(im: Image.Image) -> tuple[bytes, bytes]:
        r, g, b, a = im.split()
        rgb = b"".join(packbits(c.tobytes()) for c in (r, g, b))
        return rgb, a.tobytes()

    entries: list[tuple[bytes, bytes]] = []
    for kind, mask, points in ((b"is32", b"s8mk", 16), (b"il32", b"l8mk", 32)):
        rgb, alpha = legacy(mac_icon(points))
        entries += [(kind, rgb), (mask, alpha)]
    for kind, points, scale in (
        (b"ic11", 16, 2),
        (b"ic12", 32, 2),
        (b"ic07", 128, 1),
        (b"ic13", 128, 2),
        (b"ic08", 256, 1),
        (b"ic14", 256, 2),
        (b"ic09", 512, 1),
        (b"ic10", 512, 2),
    ):
        entries.append((kind, png(mac_icon(points, scale))))
    body = b"".join(struct.pack(">4sI", k, 8 + len(d)) + d for k, d in entries)
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)
    print("ok", path.relative_to(ROOT))


def save(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    print("ok", path.relative_to(ROOT))


def ico(images: list[Image.Image], path: Path) -> None:
    """An .ico with one PNG per size (every browser reads PNG inside .ico)."""
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


def main() -> None:
    # Browser tab: the close crop of the head.
    for size in (16, 32):
        save(render(size), PUB / f"favicon-{size}.png")
    ico([render(16), render(32), render(48)], PUB / "favicon.ico")

    # PWA. The iPhone rounds the touch icon itself: edge to edge.
    save(render(180, rounded=False).convert("RGB"), PUB / "apple-touch-icon.png")
    for size in (192, 512):
        save(render(size), PUB / f"icon-{size}.png")
    save(maskable(512), PUB / "maskable-512.png")

    # In the app (<Corvo>): the two drawings as vectors, sharp at any size.
    for name, out in (
        ("corvo-olho-icone.svg", "corvo-olho.svg"),
        ("corvo-olho-pequeno.svg", "corvo-olho-pequeno.svg"),
    ):
        (PUB / "marca" / out).write_text((SIMBOLO / name).read_text())
        print("ok", (PUB / "marca" / out).relative_to(ROOT))

    # The Mac app (docs/APP_MAC.md): the sizes Tauri reads, each drawn at its own size.
    save(mac_icon(512, 2), DESKTOP / "app-icon.png")
    save(mac_icon(32), TAURI_ICONS / "32x32.png")
    save(mac_icon(128), TAURI_ICONS / "128x128.png")
    save(mac_icon(128, 2), TAURI_ICONS / "128x128@2x.png")
    save(mac_icon(512), TAURI_ICONS / "icon.png")
    icns(TAURI_ICONS / "icon.icns")


if __name__ == "__main__":
    main()
