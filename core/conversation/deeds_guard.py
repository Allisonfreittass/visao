"""A reply never claims to have done something in the app that was not done (ADR-0021).

On 17/11/2026 it answered "Anotado: a viagem ao Chile fica no projeto «Viagem para o Chile»"
with no project and no note anywhere, and then said it could not create projects. When no action
in the app ran this turn, a sentence that says it noted, created, moved, paused or deleted a
project, a note, a panel or a page goes, in code; removing never adds a claim.
"""

import re

from core.memory.text import fold

_SENTENCE_BREAK = re.compile(r"(?<=[.!?;\n])\s+")
_CLAIM = re.compile(
    r"\b(anotad[oa]s?|anotei|registrei|registrad[oa]s?|criei|criad[oa]|apaguei|apagad[oa]|"
    r"exclui|excluid[oa]|removi|removid[oa]|renomeei|salvei|salv[oa]|guardei|guardad[oa]|movi|"
    r"coloquei|pausei|retomei)\b"
)
_THING = re.compile(r"\b(projeto|projetos|anotac\w*|notas?|painel|paineis|pagina)\b")
# "Não consigo acrescentar isso agora" right after offering to (17/11/2026): it can.
_DENIES = re.compile(
    r"\b(nao (consigo|posso|tenho como|da para|da pra)|sem como)\b.{0,40}"
    r"\b(anotar|acrescentar|adicionar|incluir|criar|colocar|atualizar|apagar)\b"
)
# "Você pode colar este texto na tela do projeto" (17/11/2026): it does that itself.
_HANDS_OVER = re.compile(
    r"\b(voce|vc) (pode|precisa|tem que|deve)\b.{0,30}"
    r"\b(colar|copiar|anotar|acrescentar|adicionar|criar|colocar)\b.{0,60}"
    r"\b(projeto|anotac\w*|notas?|painel)\b"
)
FALLBACK = "Não fiz nada no app nesta resposta."
MIN_KEPT_CHARS = 12


def violations(text: str) -> list[str]:
    """Sentences claiming something done in the app."""
    found = []
    for sentence in _SENTENCE_BREAK.split(text):
        folded = fold(sentence)
        claimed = _CLAIM.search(folded) and _THING.search(folded)
        if claimed or _DENIES.search(folded) or _HANDS_OVER.search(folded):
            found.append(sentence)
    return found


def strip(text: str) -> str:
    kept = text
    for sentence in violations(text):
        kept = kept.replace(sentence, "", 1)
    kept = re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", kept)).strip()
    return kept if len(kept) >= MIN_KEPT_CHARS else FALLBACK
