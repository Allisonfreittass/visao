"""The cheap word check in front of the browser planner (core/browse.py): it must let through
every way of asking for a live price, including a short follow-up in a conversation about fares,
and stay quiet in ordinary talk, where a planning call would be money for nothing."""

import pytest

from core.browse import candidate

TRAVEL_TALK = (
    "user: quanto custa viajar pro Chile em agosto de 2027 a dois?\n"
    "assistant: Uma semana em Santiago sai por volta de R$ 6 mil para dois, com passagem e hotel."
)


@pytest.mark.parametrize(
    "text",
    [
        # The exact phrases of the video (14/11/2026).
        "quanto custa viajar pro Chile em agosto de 2027 a dois?",
        "Então não consegue cotar em tempo real?",
        "cota pra mim as diárias em Providencia",
        "consegue cotar a ida e volta?",
        "faz um orçamento da viagem",
        "qual o valor da tarifa só ida?",
        "quanto está o hostel em Santiago?",
        "quanto tá a passagem pra Santiago?",
    ],
)
def test_ways_of_asking_for_a_live_price_are_candidates(text):
    assert candidate(text)


@pytest.mark.parametrize(
    "text",
    [
        "e em tempo real?",
        "e hoje, como está?",
        "consegue ver ao vivo?",
        "saindo de BH, de 10 a 20 de agosto",
        "somos duas pessoas",
        "de Confins pra Santiago",
    ],
)
def test_a_short_follow_up_to_talk_about_fares_is_a_candidate(text):
    assert candidate(text, TRAVEL_TALK)
    assert not candidate(text, "user: bom dia\nassistant: bom dia! dormiu bem?")


@pytest.mark.parametrize(
    "text",
    [
        "bom dia, tudo bem?",
        "agora vou dormir",
        "hoje foi um dia difícil",
        "me explica o que é recursão",
        "o show foi incrível",
        "/mac visao rode git status",
    ],
)
def test_ordinary_talk_is_not_a_candidate(text):
    assert not candidate(text)


def test_thanks_after_talk_about_fares_is_not_a_candidate():
    assert not candidate("valeu, obrigado!", TRAVEL_TALK)
    assert not candidate("legal", TRAVEL_TALK)


def test_the_status_says_what_it_does_in_the_owners_words():
    from core.browse import step_for

    flights = "https://www.google.com/travel/flights?q=Flights%20to%20SCL"
    assert step_for(flights) == ("Cotando voos", "google.com")
    assert step_for("https://www.google.com/travel/search?q=hot%C3%A9is")[0] == "Olhando hotéis"
    assert step_for("https://www.latam.com/pt-br/") == ("Lendo latam.com", "latam.com")
