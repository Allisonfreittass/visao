"""Observable behavior, computed in code from what was actually said (master prompt §8).

These numbers are the evidence for "behavior changed". The model's own description of itself
is never used as evidence.
"""

import re
from statistics import mean

_SENTENCE = re.compile(r"[^.!?…]+[.!?…]+|[^.!?…]+$")
_WORD = re.compile(r"\w+")
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
# Trailing punctuation belongs to the sentence, not the URL.
_URL = re.compile(r"https?://\S*[^\s.,;:!?)\]]")
_HEDGE = re.compile(
    r"(?i)\b(n[aã]o sei|talvez|possivelmente|incert[oa]|n[aã]o tenho certeza|"
    r"n[aã]o (?:consigo|posso) (?:afirmar|confirmar|verificar))\b"
)
# Generic assistant formulas (Phase 9 §10). Measured, not banned: frequent automatic use is a
# sign that the reply ignores the cognitive context.
GENERIC_PHRASES = re.compile(
    r"(?i)(fico à disposição|estou à disposição|como posso (te |lhe )?ajud|em que posso ajudar|"
    r"sou apenas uma (inteligência artificial|ia)|não (tenho|possuo) autonomia|"
    r"se (você )?(quiser|desejar|precisar)[^.]{0,40}(posso|pode|é só))"
)
_DISAGREE = re.compile(r"(?i)\b(discordo|n[aã]o concordo|na verdade,|n[aã]o é bem assim)\b")

METRIC_KEYS = (
    "chars",
    "words",
    "sentences",
    "questions",
    "list_items",
    "citations",
    "hedges",
    "disagreements",
    "generic_phrases",
)


def measure(text: str) -> dict[str, int]:
    stripped = text.strip()
    return {
        "chars": len(stripped),
        "words": len(_WORD.findall(stripped)),
        # URLs removed first: their dots are not sentence ends.
        "sentences": len([s for s in _SENTENCE.findall(_URL.sub("", stripped)) if s.strip()]),
        "questions": stripped.count("?"),
        "list_items": len(_LIST_ITEM.findall(stripped)),
        "citations": len(_URL.findall(stripped)),
        "hedges": len(_HEDGE.findall(stripped)),
        "disagreements": len(_DISAGREE.findall(stripped)),
        "generic_phrases": len(GENERIC_PHRASES.findall(stripped)),
    }


def summarize(observations: list[dict[str, int]]) -> dict[str, float]:
    """Mean of every metric; empty input gives zeros (with n=0 so callers can tell)."""
    summary = {
        key: round(mean(o.get(key, 0) for o in observations), 2) if observations else 0.0
        for key in METRIC_KEYS
    }
    summary["n"] = len(observations)
    return summary
