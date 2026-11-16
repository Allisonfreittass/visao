"""The patterns that catch a reply denying the browser (docs/decisions/0013): the two real
replies of 16/11/2026 and their variations, and the true sentences that must pass."""

import pytest

from core.conversation import browser_guard

# The two replies of 16/11/2026, as they were sent, with the browser working.
AT_1137 = (
    "Depende da agência e do centro, mas aula costuma ser um custo a mais relevante. Em geral, "
    "cada aula de meio dia ou de dia inteiro é cobrada à parte, e o valor varia conforme o centro "
    "e a época. Como não tenho preços atuais, não consigo dar um número confiável."
)
AT_1135 = (
    "Agosto é inverno no Chile, então esquiar faz bastante sentido. Quando tiver a cidade de "
    "saída e se vocês querem ficar em Santiago ou sair para algum centro de esqui, eu te ajudo a "
    "organizar o que pedir à agência ou pesquisar nos sites."
)


@pytest.mark.parametrize(
    "text",
    [
        AT_1137,
        AT_1135,
        "Não tenho acesso a sites de passagem.",
        "Não tenho acesso à internet.",
        "Não consigo consultar os preços ao vivo.",
        "Não consigo ver preços em tempo real.",
        "Infelizmente não consigo cotar isso.",
        "Não posso navegar.",
        "Não tenho informações atualizadas sobre preços.",
        "Sugiro pesquisar nos sites de passagem.",
        "Vale consultar direto nos sites das companhias.",
        "O melhor é pedir à agência um orçamento.",
    ],
)
def test_denials_and_handing_over_the_search_are_caught(text):
    assert browser_guard.violations(text)


@pytest.mark.parametrize(
    "text",
    [
        "O preço pode mudar até você comprar.",
        "Confira no site antes de pagar.",
        "Abri o Google Voos às 9h: a LATAM sai por R$ 2.019.",
        "Não consigo reservar nem comprar, só aviso e mando o link.",
        "Tentei ver os preços ao vivo agora e não consegui.",
        "A agência de turismo da cidade fecha às 18h.",
        "Consigo ver os preços de agora nos sites.",
        "Não tenho certeza se a aula inclui o equipamento.",
        "Os preços atuais estão no quadro abaixo.",
    ],
)
def test_true_sentences_about_prices_and_sites_pass(text):
    assert browser_guard.violations(text) == []


def test_stripping_keeps_the_rest_and_closes_with_a_true_sentence():
    fixed = browser_guard.strip(AT_1137, browser_guard.FALLBACK)
    assert "não tenho preços atuais" not in fixed
    assert fixed.startswith("Depende da agência e do centro")
    assert fixed.endswith(browser_guard.FALLBACK)
    assert browser_guard.violations(fixed) == []


def test_a_reply_that_was_only_the_denial_becomes_the_fallback():
    assert browser_guard.strip("Não consigo cotar isso.", browser_guard.TRIED) == (
        browser_guard.TRIED
    )


def test_what_is_missing_is_asked_in_one_question():
    assert browser_guard.asks_for(["origem", "datas"]) == (
        "Consigo ver os preços de agora nos sites; para buscar, me diz origem e datas?"
    )
    assert browser_guard.violations(browser_guard.asks_for(["origem"])) == []
