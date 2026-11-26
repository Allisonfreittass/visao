"""A reply that contradicts what the turn measured is fixed in code before anyone reads it.

25/11/2026, on the Mac app with a small free model: GitHub was read on the server and the number
(42 commits) was in the reply's context, and the reply said "não abri o GitHub e o Mac continua
desligado", copying what an earlier reply had said; the Mac's arm had answered seconds before.
Prompt wording does not hold with such a model, so, like browser_guard and deeds_guard, the check
is in code and only removes or replaces; it never adds a fact the turn did not measure.
"""

import re

from core.memory.text import fold

# Matched on fold()ed text.
_DENIES_GITHUB = re.compile(
    r"\bnao\s+(?:abri|li|consegui|tenho|tive|acessei|vi|olhei)\b[^.\n]{0,60}\bgithub\b"
    r"|\bgithub\b[^.\n]{0,40}\bnao\s+(?:abri|abriu|consegui|tenho\s+acesso)"
    r"|\bnao\s+tenho\s+(?:como|esse\s+numero|acesso)\b"
)
_MAC_OFF = re.compile(
    r"\b(?:o\s+)?(?:seu\s+)?mac\b[^.\n]{0,40}\b(?:desligad\w*|offline|fora\s+do\s+ar)"
    r"|\bmac\b[^.\n]{0,40}\bnao\s+(?:esta|estou|esta\s+mais)\s+conectad\w*"
    r"|\bnao\s+estou\s+conectad\w*[^.\n]{0,40}\bmac\b"
)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?\s*")

MAC_ON = "Seu Mac está ligado agora: o braço respondeu há pouco."


def github_contradicted(reply: str, counts: list[str]) -> bool:
    """GitHub was read: the reply denies it, or gives none of the numbers read."""
    folded = fold(reply)
    if _DENIES_GITHUB.search(folded):
        return True
    said = any(re.search(rf"(?<!\d){re.escape(c)}(?!\d)", reply) for c in counts)
    return bool(counts) and not said


def github_reply(facts: list[str]) -> str:
    """The answer written by code from what was read, for when the model's contradicts it."""
    return " ".join(facts)


def fix_mac_off(reply: str) -> str | None:
    """The Mac is on: each sentence saying it is off goes, and one true sentence takes the first
    one's place. None when the reply says nothing of the kind."""
    sentences = _SENTENCE.findall(reply)
    wrong = [i for i, s in enumerate(sentences) if _MAC_OFF.search(fold(s))]
    if not wrong:
        return None
    kept: list[str] = []
    for i, sentence in enumerate(sentences):
        if i == wrong[0]:
            kept.append(MAC_ON + (" " if sentence.endswith((" ", "\n")) else ""))
        elif i not in wrong:
            kept.append(sentence)
    return "".join(kept).strip()
