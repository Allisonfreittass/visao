"""Muninn em ASCII: a gênese do Visão no terminal.

    python brand/muninn/muninn_ascii.py            # anima (≈6 s) e deixa o quadro final
    python brand/muninn/muninn_ascii.py --static   # só o quadro final

Só biblioteca padrão. Lê muninn-ascii.json (gerado por ascii_build.py a partir da ilustração).
Sem animação quando a saída não é um terminal, com NO_COLOR, ou com VISAO_NO_ANIM=1.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

DATA = Path(__file__).with_name("muninn-ascii.json")
PAPER = (243, 241, 236)
MUTED = (154, 161, 168)
AMBER = (240, 162, 59)
SCRAMBLE = "*+x%#=:"
FPS = 24
TOTAL = 6.2
CAPTION = "V.I.S.A.O.   chosen_name = null"


class Genesis:
    """The timeline, shared by the terminal player and the GIF renderer."""

    def __init__(self, data: dict, seed: int = 7) -> None:
        self.cols, self.rows = data["cols"], data["rows"]
        self.grid = data["grid"]
        self.eye = tuple(data["eye"])
        self.gap = tuple(data["gap"])
        rnd = random.Random(seed)  # noqa: S311 (animation, not security)
        inked = [
            (data["order"][r][c], r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if self.grid[r][c] != " "
        ]
        far = max(o for o, _, _ in inked)
        self.start = {(r, c): 0.25 + (o / far) * 3.1 + rnd.uniform(0, 0.35) for o, r, c in inked}
        self.noise = {k: rnd.choice(SCRAMBLE) for k in self.start}
        self.ring = [(m["r"], m["c"], m["ch"], 3.9 + m["i"] * 0.035) for m in data["ring"]]
        chest = max(self.start, key=lambda k: -data["order"][k[0]][k[1]])
        self.chest = chest

    def frame(self, t: float) -> list[list[tuple[str, tuple[int, int, int]]]]:
        out = [[(" ", PAPER)] * self.cols for _ in range(self.rows + 2)]
        for (r, c), s in self.start.items():
            if t < s:
                continue
            if t < s + 0.22:
                ch = self.noise[(r, c)] if int(t * 30) % 2 else SCRAMBLE[(r + c + int(t * 30)) % 7]
                out[r][c] = (ch, AMBER if (r * 7 + c) % 9 == 0 else MUTED)
            else:
                out[r][c] = (self.grid[r][c], PAPER)
        if t < 3.6:
            r, c = self.chest
            out[r][c] = ("@", AMBER)
        if t >= 3.7:
            r, c = self.eye[1], self.eye[0]
            out[r][c] = ("@", AMBER)
        for r, c, ch, s in self.ring:
            if t >= s and 0 <= r < self.rows and 0 <= c < self.cols:
                out[r][c] = (ch, MUTED if ch == ":" else PAPER)
        if t >= 4.9:
            c, r = self.gap
            on = int((t - 4.9) * 4) % 2 == 0 or t >= TOTAL - 0.3
            out[max(0, r)][c] = ("o" if on else " ", AMBER)
        if t >= 5.1:
            text = CAPTION
            c0 = (self.cols - len(text)) // 2
            k = text.index("null")
            for i, ch in enumerate(text):
                out[self.rows + 1][c0 + i] = (ch, AMBER if k <= i < k + 4 else MUTED)
        return out


def _paint(rows, color: bool) -> str:
    lines = []
    for row in rows:
        line, last = [], None
        for ch, rgb in row:
            if color and rgb != last and ch != " ":
                line.append(f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m")
                last = rgb
            line.append(ch)
        lines.append("".join(line).rstrip())
    return "\n".join(lines) + ("\x1b[0m" if color else "")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    g = Genesis(json.loads(DATA.read_text()))
    tty = sys.stdout.isatty()
    color = tty and "NO_COLOR" not in os.environ
    animate = tty and "--static" not in argv and os.environ.get("VISAO_NO_ANIM") != "1"
    if not animate:
        print(_paint(g.frame(TOTAL), color))
        return 0
    out = sys.stdout
    out.write("\x1b[?25l\x1b[2J")
    try:
        t0 = time.monotonic()
        while (t := time.monotonic() - t0) < TOTAL:
            out.write("\x1b[H" + _paint(g.frame(t), color))
            out.flush()
            time.sleep(1 / FPS)
        out.write("\x1b[H" + _paint(g.frame(TOTAL), color) + "\n")
    except KeyboardInterrupt:
        out.write("\x1b[H" + _paint(g.frame(TOTAL), color) + "\n")
    finally:
        out.write("\x1b[0m\x1b[?25h")
        out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
