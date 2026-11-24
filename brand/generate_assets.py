"""Gera os ícones do app web a partir do corvo no eclipse (DESIGN.md §5).

    pip install pillow
    python brand/generate_assets.py

As fontes são os dois desenhos em brand/corvo/: `icone-grande-512.png` para tudo acima de 72 px e
`icone-pequeno-256.png` (traço mais grosso, lê melhor pequeno) para 72 px ou menos. Escreve em
apps/web/public/. O ícone do iPhone e a og-image ainda são os da marca anterior e não saem daqui:
mudam quando o iPhone e o selo do login migrarem.
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CORVO = ROOT / "brand/corvo"
PUB = ROOT / "apps/web/public"

TINTA = (16, 18, 20)  # the ground of the drawing, under its rounded corners
SMALL_MAX = 72  # px: up to here, the small drawing


def source(size: int) -> Image.Image:
    name = "icone-pequeno-256.png" if size <= SMALL_MAX else "icone-grande-512.png"
    return Image.open(CORVO / name).convert("RGBA")


def icon(size: int) -> Image.Image:
    """The icon as drawn: rounded corners, transparent around them."""
    return source(size).resize((size, size), Image.LANCZOS)


def full_bleed(size: int) -> Image.Image:
    """Edge to edge, the corners filled with tinta: for whoever masks the icon (iOS, Android)."""
    ground = Image.new("RGBA", (size, size), (*TINTA, 255))
    return Image.alpha_composite(ground, icon(size)).convert("RGB")


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
    # PWA and browser.
    save(full_bleed(180), PUB / "apple-touch-icon.png")
    for size in (192, 512):
        save(icon(size), PUB / f"icon-{size}.png")
    # Maskable: edge to edge. The crow already runs off the bottom and the left; a round mask
    # trims a little of the eclipse, the squircles keep it.
    save(full_bleed(512), PUB / "maskable-512.png")
    ico([icon(16), icon(32), icon(48)], PUB / "favicon.ico")

    # In the app (<Corvo>): the two drawings, as they are.
    save(source(512), PUB / "marca/corvo-512.png")
    save(source(SMALL_MAX), PUB / "marca/corvo-256.png")


if __name__ == "__main__":
    main()
