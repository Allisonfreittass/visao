"""Sources unrelated to the question never reach the reply (core/research/relevance.py)."""

from dataclasses import dataclass

from core.research.relevance import relevant

QUESTION = "quanto custa viajar pro Chile em agosto de 2027 a dois?"


@dataclass
class S:
    title: str
    snippet: str


# The three sources of the video (14/11/2026), with excerpts like the ones the search returned.
POET = S(
    "Cecília Meireles – Wikipédia, a enciclopédia livre",
    "Cecília Benevides de Carvalho Meireles foi uma poetisa, pintora e professora brasileira. "
    "Autora de Viagem (1939) e Romanceiro da Inconfidência.",
)
INSURER = S(
    "AM Best Affirms Credit Ratings of Chubb Seguros Chile S.A.",
    "AM Best has affirmed the Financial Strength Rating of A++ (Superior) of Chubb Seguros "
    "Chile S.A.",
)
COSTS = S(
    "Quanto custa viajar para o Chile? Guia de custos para 2027",
    "Passagens, hospedagem em Santiago e passeios: veja quanto gastar numa viagem ao Chile.",
)


def test_the_video_sources_the_poet_and_the_insurer_go_the_article_stays():
    assert relevant([POET, INSURER, COSTS], QUESTION, "custo de viagem ao Chile") == [COSTS]


def test_a_single_topic_word_needs_a_single_match():
    page = S("Recursão (ciência da computação)", "Em programação, recursão é...")
    assert relevant([page, POET], "o que é recursão?") == [page]


def test_without_topic_words_nothing_is_dropped():
    assert relevant([POET], "quanto custa?") == [POET]
