"""With the browser there, a reply never denies it (docs/decisions/0013).

Real cases (16/11/2026), with the browser working and its line in the capabilities:
- "Como não tenho preços atuais, não consigo dar um número confiável."
- "eu te ajudo a organizar o que pedir à agência ou pesquisar nos sites" (the search handed to the
  owner, when the browser was one detail away from looking).

A prompt line is a hope; this is a check in code, like the owner's rules ("7 de 8 respostas
quebraram"). The patterns are pt-BR and narrow on purpose: "o preço pode mudar até você comprar"
or "confira no site antes de pagar" are fine. A reply that matches is rewritten by the same short
check as the owner's rules, with RULE added; what still matches after that loses the sentence
and gets `fallback` (one sentence that says it can look, that it tried, or what is missing).
"""

import re

_SENTENCE_BREAK = re.compile(r"(?<=[.!?;\n])\s+")

_LIVE = (
    r"(?:pre[çc]os?|valores?|tarifas?|cota[çc][õo]es|dados|informa[çc][õo]es)"
    r"(?: \w+){0,2}? (?:atuais|atualizad[oa]s|de agora|em tempo real|ao vivo|do momento|de hoje)"
)
_REACH = (
    r"(?:sites?|a internet|internet|a web|navegador|preços? (?:atuais|de agora|ao vivo|em tempo "
    r"real)|dados em tempo real|tempo real|consultas? ao vivo)"
)

# Saying it cannot see what it can.
_DENIES = re.compile(
    "|".join(
        (
            rf"n[ãa]o (?:tenho|tenho como ter|possuo|disponho de) (?:acesso a |como ver )?{_LIVE}",
            rf"n[ãa]o (?:tenho|possuo) acesso (?:a|à|aos|às) {_REACH}",
            rf"sem acesso (?:a|à|aos|às) {_REACH}",
            r"n[ãa]o (?:consigo|posso|tenho como) (?:\w+ )?(?:consultar|acessar|ver|verificar|"
            r"checar|olhar|pesquisar|buscar|navegar)(?: \w+){0,3}? (?:ao vivo|em tempo real|"
            r"online|na internet|nos sites|em sites|os sites|sites de)",
            r"n[ãa]o (?:consigo|posso|tenho como) (?:\w+ )?"
            r"(?:cotar|fazer (?:uma |a )?cota[çc][ãa]o)",
            r"n[ãa]o (?:consigo|posso) navegar",
        )
    ),
    re.IGNORECASE,
)
# Handing the owner the search it could do itself.
_HANDS_OVER = re.compile(
    "|".join(
        (
            r"(?:pesquisar|procurar|checar|consultar|verificar|olhar|buscar|comparar) "
            r"(?:direto )?(?:nos|em) sites(?: de (?:passage\w*|viage\w*|hot[ée]is|compra\w*))?",
            r"(?:pesquise|procure|cheque|consulte|verifique|olhe|busque|compare) "
            r"(?:direto )?(?:nos|em) sites",
            r"pedir (?:à|a|para a|pra) (?:uma )?ag[êe]ncia",
            r"(?:pe[çc]a|consulte|procure) (?:uma |a )?ag[êe]ncia",
        )
    ),
    re.IGNORECASE,
)

RULE = (
    "O navegador de verdade está disponível: a resposta nunca diz que não tem acesso a preços "
    "atuais, a sites ou a consulta ao vivo, e nunca manda a pessoa pesquisar nos sites ou pedir à "
    "agência no lugar da consulta. Tire essas frases. Se faltou um dado para consultar, a resposta "
    "pergunta só esse dado; se a consulta foi tentada e falhou, diz que tentou ver ao vivo agora e "
    "não conseguiu."
)
FALLBACK = "Consigo ver os preços de agora nos sites, num navegador de verdade: quer que eu olhe?"
TRIED = "Tentei ver os preços ao vivo agora e não consegui; posso tentar de novo."
MIN_KEPT_CHARS = 20


def asks_for(missing: list[str]) -> str:
    return (
        "Consigo ver os preços de agora nos sites; para buscar, me diz "
        + ", ".join(missing[:-1])
        + (" e " if len(missing) > 1 else "")
        + missing[-1]
        + "?"
    )


def violations(text: str) -> list[str]:
    """The sentences that deny the browser or hand the search to the owner."""
    return [
        s
        for s in _SENTENCE_BREAK.split(text)
        if s.strip() and (_DENIES.search(s) or _HANDS_OVER.search(s))
    ]


def strip(text: str, fallback: str = FALLBACK) -> str:
    """The reply without the offending sentences, closed by `fallback`. Used only when the
    rewrite did not fix it: removing never adds a claim, and `fallback` says what is true."""
    kept = text
    for sentence in violations(text):
        kept = kept.replace(sentence, "", 1)
    kept = re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", kept)).strip()
    if len(kept) < MIN_KEPT_CHARS:
        return fallback
    return f"{kept.rstrip()} {fallback}" if fallback else kept
