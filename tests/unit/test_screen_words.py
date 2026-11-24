"""Only the owner's own words ask for a look at the screen (docs/TELA.md), read by code."""

import pytest

from core.arm.screen import wants_screen


@pytest.mark.parametrize(
    "text",
    [
        "olha minha tela",
        "Olha a minha tela e me diz o que é esse erro",
        "vê o que está na minha tela",
        "dá uma olhada aqui na tela",
        "confere a tela pra mim",
        "lê o que tá na tela",
        "o que é isso na minha tela?",
        "o que aparece na tela agora?",
        "tira um print da minha tela",
        "captura de tela, por favor",
        "/tela que erro é esse",
    ],
)
def test_asking_to_look(text):
    assert wants_screen(text)


@pytest.mark.parametrize(
    "text",
    [
        "minha tela quebrou",
        "comprei uma tela nova de 27 polegadas",
        "não olha minha tela agora",
        "olha que bonito o pôr do sol",
        "a tela de login do app está feia",
        "",
    ],
)
def test_not_asking(text):
    assert not wants_screen(text)
