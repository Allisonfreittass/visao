"""Extrai os traços do Muninn a partir da ilustração mestre.

Uso:  python brand/muninn/trace.py [brand/muninn/muninn-lineart.png] [brand/muninn/strokes.json]
Precisa de: opencv-python, scikit-image, numpy.

Saída: lista de traços [x0, y0, x1, y1, ...] em coordenadas 0..1000, já escalados para caber
dentro do anel (76%, +14 no eixo y) e ordenados do peito para fora (ordem de desenho da gênese).
"""

import json
import math
import sys

import cv2
import numpy as np
from skimage.morphology import skeletonize

SRC = sys.argv[1] if len(sys.argv) > 1 else "brand/muninn/muninn-lineart.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else "brand/muninn/strokes.json"
SCALE, OFFSET_Y, CHEST = 0.76, 14, (627, 600)  # CHEST em pixels da imagem original

img = cv2.imread(SRC, cv2.IMREAD_GRAYSCALE)
sk = skeletonize(img > 90).astype(np.uint8)
H, W = sk.shape
NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
pix = set(zip(*[a.tolist() for a in np.nonzero(sk)], strict=True))


def neigh(p):
    return [(p[0] + dy, p[1] + dx) for dy, dx in NB if (p[0] + dy, p[1] + dx) in pix]


deg = {p: len(neigh(p)) for p in pix}
seen = set()


def edge(a, b):
    return (a, b) if a < b else (b, a)


def walk(a, b):
    path, prev, cur = [a, b], a, b
    seen.add(edge(a, b))
    while deg[cur] == 2:
        nxt = [q for q in neigh(cur) if q != prev and edge(cur, q) not in seen]
        if not nxt:
            break
        seen.add(edge(cur, nxt[0]))
        path.append(nxt[0])
        prev, cur = cur, nxt[0]
    return path


paths = []
for start in [p for p in pix if deg[p] != 2] + list(pix):
    for q in neigh(start):
        if edge(start, q) not in seen:
            paths.append(walk(start, q))


def tf(x, y):
    return ((x / W * 1000 - 500) * SCALE + 500, (y / H * 1000 - 500) * SCALE + 500 + OFFSET_Y)


items = []
for p in paths:
    if len(p) < 9:
        continue
    arr = np.array([[x, y] for y, x in p], dtype=np.float32).reshape(-1, 1, 2)
    ap = cv2.approxPolyDP(arr, 1.0, False).reshape(-1, 2)
    m = ap.mean(axis=0)
    flat = [round(float(v), 1) for x, y in ap for v in tf(x, y)]
    items.append((math.hypot(m[0] - CHEST[0], (m[1] - CHEST[1]) * 1.1), flat))

items.sort(key=lambda t: t[0])
with open(OUT, "w") as f:
    json.dump([s for _, s in items], f, separators=(",", ":"))
print(f"{len(items)} traços -> {OUT}")
