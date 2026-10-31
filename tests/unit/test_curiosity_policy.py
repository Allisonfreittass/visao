import pytest

from core.curiosity.engine import (
    ASK_USER,
    DEFER,
    IGNORE,
    WEB_RESEARCH,
    Assessment,
    AssessmentOutputError,
    decide,
    is_trivial,
    parse_assessment,
)


def _assessment(**overrides: object) -> Assessment:
    fields: dict[str, object] = {
        "gap": True,
        "trigger": "uncertainty",
        "depends_on": "public_fact",
        "about_private_person": False,
        "question": "Qual é a capital da Austrália?",
        "hypothesis": "Camberra",
        "search_query": "capital da Austrália",
        "uncertainty": 0.6,
        "expected_value": 0.8,
        "urgency": 0.5,
        "risk": 0.0,
    }
    fields.update(overrides)
    return Assessment(**fields)  # type: ignore[arg-type]


def _decide(assessment: Assessment, budget: bool = True, asked: bool = False) -> tuple[str, str]:
    d = decide(assessment, research_budget_left=budget, already_asked=asked)
    return d.action, d.reason


@pytest.mark.parametrize(
    "text", ["oi", "Obrigado!", "valeu", "ok", "bom dia", "Combinado.", "sim", "kkkk", "beleza"]
)
def test_trivial_turns_skip_assessment(text: str) -> None:
    assert is_trivial(text)


@pytest.mark.parametrize(
    "text", ["Qual a capital da Austrália?", "Me ajuda a planejar a semana", "oi, quem foi Turing?"]
)
def test_real_turns_are_assessed(text: str) -> None:
    assert not is_trivial(text)


def test_public_fact_goes_to_research() -> None:
    assert _decide(_assessment()) == (WEB_RESEARCH, "public_fact")


def test_personal_goes_to_the_user() -> None:
    assert _decide(_assessment(depends_on="personal")) == (ASK_USER, "personal")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"gap": False}, "no_gap"),
        ({"question": ""}, "no_gap"),
        ({"about_private_person": True}, "private_third_party"),
        ({"risk": 0.9}, "risk"),
        ({"expected_value": 0.2}, "low_value"),
        ({"depends_on": "none"}, "not_actionable"),
        ({"search_query": ""}, "no_query"),
    ],
)
def test_ignored_cases(overrides: dict[str, object], reason: str) -> None:
    assert _decide(_assessment(**overrides)) == (IGNORE, reason)


def test_personal_question_about_a_relative_is_asked_not_blocked() -> None:
    # Regression (real eval, 2026-10-31): "help me pick a gift for my mother" was flagged as about
    # a private person and the question to the user was wrongly suppressed.
    assessment = _assessment(depends_on="personal", about_private_person=True)
    assert _decide(assessment) == (ASK_USER, "personal")


def test_no_budget_defers_research() -> None:
    assert _decide(_assessment(), budget=False) == (DEFER, "research_budget")


def test_same_personal_question_is_not_repeated() -> None:
    assert _decide(_assessment(depends_on="personal"), asked=True) == (IGNORE, "already_asked")


def test_parse_clamps_scores_and_tolerates_wrapping() -> None:
    parsed = parse_assessment(
        'Resultado:\n```json\n{"gap": true, "depends_on": "public_fact", "question": "q",'
        ' "expected_value": 7, "risk": -1, "uncertainty": "x"}\n```'
    )
    assert (parsed.expected_value, parsed.risk, parsed.uncertainty) == (1.0, 0.0, 0.0)
    assert parsed.gap is True


@pytest.mark.parametrize("text", ["nada", "[1, 2]", "{quebrado"])
def test_parse_rejects_garbage(text: str) -> None:
    with pytest.raises(AssessmentOutputError):
        parse_assessment(text)
