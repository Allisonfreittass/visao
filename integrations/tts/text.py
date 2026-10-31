"""Turns an LLM reply (often Markdown) into speakable text, split into sentences so the first
one can be synthesized and played while the rest is still being generated."""

import re

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_LIST_MARK = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ0-9\"“(])")
_SPACES = re.compile(r"[ \t]+")
_STRAY_MARKUP = re.compile(r"[*_#`~>|]+")

MAX_SENTENCE_CHARS = 300


def speakable(markdown: str) -> str:
    text = _CODE_BLOCK.sub(" (trecho de código omitido) ", markdown)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("link", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _HEADING.sub("", text)
    # A list item becomes its own sentence.
    text = _LIST_MARK.sub("", text)
    text = _STRAY_MARKUP.sub(" ", text)
    # Lines left with no letters or digits (separators, empty emphasis) are dropped.
    lines = [line.strip() for line in text.splitlines() if re.search(r"\w", line)]
    text = " ".join(line if line[-1] in ".!?…:;," else line + "." for line in lines)
    return _SPACES.sub(" ", text).strip()


def _split_long(sentence: str) -> list[str]:
    """Breaks very long sentences at commas/semicolons so no chunk takes too long to synthesize."""
    if len(sentence) <= MAX_SENTENCE_CHARS:
        return [sentence]
    parts, current = [], ""
    for piece in re.split(r"(?<=[,;:])\s+", sentence):
        if current and len(current) + len(piece) + 1 > MAX_SENTENCE_CHARS:
            parts.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        parts.append(current)
    return parts


def sentences(markdown: str) -> list[str]:
    text = speakable(markdown)
    if not text:
        return []
    out: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        out.extend(_split_long(sentence.strip()))
    return [s for s in out if s]
