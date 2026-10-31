"""Lexical normalization shared by deduplication and retrieval (Portuguese-first)."""

import re
import unicodedata

# Short, high-frequency words that carry no topic. Kept small on purpose.
STOPWORDS = frozenset(
    """
    que para com uma uns umas por mais como mas foi ser tem sao era isso isto esse essa este esta
    aquele aquela ele ela eles elas voce voces meu minha meus minhas seu sua seus suas nos dos das
    nas num numa pelo pela pelos pelas sobre entre quando onde qual quais quem muito muita tambem
    ainda ja nao sim sem ate the and you are was what with this that from have
    """.split()
)

_WORD = re.compile(r"\w+")


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(fold(text)) if len(t) >= 3 and t not in STOPWORDS}


def overlap(a: set[str], b: set[str]) -> float:
    """Cosine-like overlap of token sets, 0..1."""
    if not a or not b:
        return 0.0
    return len(a & b) / (len(a) * len(b)) ** 0.5


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
