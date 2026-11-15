"""Drops search results that have nothing to do with the question, before anyone sees them.

Real case (14/11/2026): asked the cost of a trip to Chile, the reply listed "Cecília Meireles ·
Wikipédia" and "AM Best Affirms Credit Ratings of Chubb Seguros" as sources. A cheap lexical
check, no model call: a result stays when its title and excerpt share enough topic words with
what was asked. A dropped result never reaches the reply prompt, so it cannot be cited.
"""

from collections.abc import Iterable, Sequence
from typing import Protocol

from core.memory.text import tokens

STEM = 5
# Words of the question that say how it is asked, not what it is about.
_ASKING = frozenset(
    """
    quanto quanta quantos quantas custa custam sai fica valor valores preco precos hoje agora
    consegue consigo pode podes poderia quero queria gostaria saber sabe fala explica real tempo
    vivo dois duas tres pessoas favor obrigado entao melhor
    """.split()
)


class Source(Protocol):
    title: str
    snippet: str


def _stems(words: Iterable[str]) -> set[str]:
    return {w[:STEM] for w in words}


def key_terms(*texts: str) -> set[str]:
    return _stems(t for text in texts for t in tokens(text) if t not in _ASKING)


def relevant[S: Source](sources: Sequence[S], *asked: str) -> list[S]:
    """The sources that share at least two topic words with what was asked (one when the
    question has a single topic word). Without topic words to compare, nothing is dropped."""
    key = key_terms(*asked)
    if not key:
        return list(sources)
    needed = min(2, len(key))
    return [s for s in sources if len(key & _stems(tokens(f"{s.title} {s.snippet}"))) >= needed]
