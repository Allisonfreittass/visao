"""A reply that only hands the owner's question back, reworded, is not a reply.

25/11/2026: "Quantos commits foram feitos hoje no repositório Visao?" came back as "Você quer saber
quantos commits foram feitos hoje no Visao?". Measured in code: a short reply that ends in a
question and says mostly the owner's own words. Then the reply is written once more, told to
answer; the second draft is kept only if it is not an echo too.
"""

from core.memory.text import overlap, tokens

MAX_ECHO_CHARS = 240
MIN_OVERLAP = 0.6

NUDGE = (
    "Sua resposta acima só devolveu a pergunta da pessoa como confirmação, e isso é proibido. "
    "Escreva a resposta de verdade agora: use os dados que o contexto trouxe e, se faltar algo, "
    "diga numa frase o que falta. Não pergunte se é isso que ela quer."
)


def echoes(question: str, reply: str) -> bool:
    text = reply.strip()
    if not text or len(text) > MAX_ECHO_CHARS or not text.endswith("?"):
        return False
    asked, said = tokens(question), tokens(text)
    if len(asked) < 2:
        return False
    return overlap(asked, said) >= MIN_OVERLAP
