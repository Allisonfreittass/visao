""" "Como foi meu dia" and "me cobra" are read in code: the day is measured and the follow-up gets
a real day and hour (25/11/2026, the Jarvis test)."""

from datetime import UTC, datetime

import pytest

from core import day, followups

# A Wednesday, 22:00 in São Paulo (01:00 UTC on Thursday).
NOW = datetime(2026, 11, 26, 1, 0, tzinfo=UTC)
SP = "America/Sao_Paulo"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("E aí, como foi meu dia hoje?", "past"),
        ("me faz um resumo do dia", "past"),
        ("o que rolou hoje?", "past"),
        ("como vai ser meu dia?", "ahead"),
        ("o que eu tenho pra hoje?", "ahead"),
        ("como foi a viagem dele?", None),
        ("bom dia!", None),
    ],
)
def test_the_day_question_is_read_in_code(text, kind):
    assert day.asks(text) == kind


def test_a_reply_that_does_not_know_the_day_is_caught():
    assert day.contradicted("Não sei como foi seu dia; você ainda não me contou o que fez.")
    assert not day.contradicted("Hoje foram 44 commits e a agenda ficou livre.")


@pytest.mark.parametrize(
    "text",
    ["me cobra: o painel essa semana", "me lembra de pagar o boleto amanhã", "cobra de mim isso"],
)
def test_a_follow_up_request_is_read(text):
    assert followups.asks(text)


def test_everyday_talk_is_not_a_follow_up():
    assert not followups.asks("ele me cobrou ontem e eu esqueci")
    assert not followups.asks("lembra quando a gente falou do Chile?")


def local(moment):
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo(SP))


def test_the_hour_of_a_follow_up_follows_the_owners_words():
    # "essa semana" on a Wednesday night: Friday at 17:00.
    friday = local(followups.when("me cobra o painel essa semana", NOW, SP))
    assert (friday.weekday(), friday.hour, friday.minute) == (4, 17, 0)
    tomorrow = local(followups.when("me lembra amanhã de ligar pro banco", NOW, SP))
    assert (tomorrow.day, tomorrow.hour) == (26, 9)
    # "hoje" at 22:00, past the evening: two hours from now.
    soon = local(followups.when("me cobra hoje ainda", NOW, SP))
    assert soon.hour == 0 and soon.day == 26
    thursday = local(followups.when("me lembra na quinta", NOW, SP))
    assert thursday.weekday() == 3
    later = followups.when("me avisa daqui a 3 horas", NOW, SP)
    assert (later - NOW).total_seconds() == 3 * 3600
    default = local(followups.when("me cobra isso", NOW, SP))
    assert (default.day, default.hour) == (26, 9)
