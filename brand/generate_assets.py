"""Gera os ícones do app a partir do corvo de olho âmbar (DESIGN.md §5).

    pip install pillow cairosvg
    python brand/generate_assets.py

As fontes são os dois desenhos em vetor de brand/simbolo/: `corvo-olho-pequeno.svg` (corte fechado
na cabeça, só o olho e o bico) até 48 px, e `corvo-olho-icone.svg` de 64 px para cima. Cada tamanho
sai direto do vetor, sem reduzir um PNG grande. Escreve em apps/web/public/ e o ícone do app de Mac
em desktop/app/app-icon.png. O cairosvg precisa do libcairo do sistema.
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

PAPEL = (243, 241, 236)  # #F3F1EC, the ground of the drawing
SMALL_MAX = 48  # px: up to here, the close crop of the head


def svg(size: int) -> str:
    name = "corvo-olho-pequeno.svg" if size <= SMALL_MAX else "corvo-olho-icone.svg"
    return (SIMBOLO / name).read_text()


def render(size: int, *, rounded: bool = True) -> Image.Image:
    """The drawing at `size`, straight from the vector. Rounded: the corners it carries, transparent
    around them. Not rounded: edge to edge, for whoever masks the icon (iOS, Android)."""
    source = svg(size)
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


def mac_icon() -> Image.Image:
    """The Mac app's icon on Apple's grid: the macOS does not round or inset icons, so the
    drawing sits as an 824 px rounded square in 1024, with a soft shadow under it."""
    canvas, body = 1024, 824
    art = render(body)
    at = (canvas - body) // 2
    alpha = art.getchannel("A").point(lambda v: v * 90 // 255)
    shape = Image.new("RGBA", (body, body), (0, 0, 0, 0))
    shape.putalpha(alpha)
    shadow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shadow.paste(shape, (at, at + 12), shape)
    out = shadow.filter(ImageFilter.GaussianBlur(14))
    out.alpha_composite(art, (at, at))
    return out


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

    # The Mac app (docs/APP_MAC.md): `npx tauri icon app-icon.png` makes the sizes from it.
    save(mac_icon(), DESKTOP / "app-icon.png")


if __name__ == "__main__":
    main()
