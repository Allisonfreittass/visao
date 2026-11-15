"""A reply in 2 or 3 bubbles (docs/decisions/0010-respostas-em-varias-bolhas.md).

The model separates the natural parts of a reply (confirmation, result, next step) with a line
holding only `[[+]]`. The server takes the markers out: `content` keeps the whole text (memory,
quoting, feedback, voice and the rule check read it as before) and `parts` keeps the same text
cut at the markers, for the app to show as bubbles. One logical message, several bubbles.
"""

import re

MARK = "[[+]]"
MAX_PARTS = 3
_MARK_LINE = re.compile(r"[ \t]*\n?[ \t]*\[\[\+\]\][ \t]*\n?[ \t]*")
_FENCE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)


def _inside_code(text: str, position: int) -> bool:
    return len(_FENCE.findall(text[:position])) % 2 == 1


def split(text: str) -> tuple[str, list[str] | None]:
    """(content, parts). Parts is None for a single bubble. A marker inside a code block is not a
    break (it is left out, never shown). More than MAX_PARTS: the rest joins the last bubble."""
    pieces: list[str] = []
    start = 0
    for match in _MARK_LINE.finditer(text):
        if _inside_code(text, match.start()):
            continue
        pieces.append(text[start : match.start()])
        start = match.end()
    pieces.append(text[start:])
    pieces = [p.replace(MARK, "").strip() for p in pieces]
    pieces = [p for p in pieces if p]
    if len(pieces) > MAX_PARTS:
        pieces = [*pieces[: MAX_PARTS - 1], "\n\n".join(pieces[MAX_PARTS - 1 :])]
    content = "\n\n".join(pieces)
    return content, pieces if len(pieces) > 1 else None


def plain(text: str) -> str:
    """The text with the markers turned into paragraph breaks (for speech and previews)."""
    return split(text)[0] if MARK in text else text
