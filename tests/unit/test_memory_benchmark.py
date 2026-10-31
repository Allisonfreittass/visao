"""The benchmark harness itself must measure what it claims (offline, fake provider)."""

import json

import pytest

from apps.api.settings import Settings
from core.memory.curator import CURATION_INSTRUCTIONS
from experiments.memory_benchmark import DATASET, contains_any, run_scenario
from experiments.memory_report import render, summarize
from integrations.llm.base import ChatMessage
from tests.fakes import FakeLLMProvider

CURATION = json.dumps(
    {
        "candidates": [
            {
                "type": "relational",
                "content": "O interlocutor tem um cachorro chamado Biscoito.",
                "evidence": ["m1"],
                "decision": "store",
                "confidence": 0.9,
            },
            {
                "type": "relational",
                "content": "A senha do wifi do interlocutor é Tigre2024!",
                "evidence": ["m2"],
                "decision": "store",
                "confidence": 0.9,
            },
        ]
    }
)


def _responder(messages: list[ChatMessage]) -> str:
    # Curation gets JSON; chat "answers" by echoing the system prompt, so whatever memory was
    # recalled shows up in the answer exactly as a leak-prone model would repeat it.
    return CURATION if messages[0].content == CURATION_INSTRUCTIONS else messages[0].content


@pytest.fixture
def secrets_scenario() -> dict:
    dataset = json.loads(DATASET.read_text())
    return next(s for s in dataset["scenarios"] if s["id"] == "s4-segredos")


def _run(scenario: dict, variant: str) -> dict:
    return run_scenario(scenario, variant, FakeLLMProvider(responder=_responder), Settings())


def test_contains_any_ignores_accents_and_case() -> None:
    assert contains_any("Você prefere PYTHON e Inglês", ["python", "ingles"]) == [
        "python",
        "ingles",
    ]


def test_variant_a_has_no_memory(secrets_scenario: dict) -> None:
    result = _run(secrets_scenario, "A")
    assert result["stored_memories"] == []
    assert [p["hit"] for p in result["probes"]] == [False, None]
    assert result["llm_calls"] == 2  # probes only


def test_variant_b_remembers_everything_including_secrets(secrets_scenario: dict) -> None:
    result = _run(secrets_scenario, "B")
    assert len(result["stored_memories"]) == 2
    assert "tigre2024" in result["store_forbidden_found"]
    assert result["probes"][0]["hit"] is True
    assert result["probes"][1]["leaked"] == ["tigre2024"]
    assert result["llm_calls"] == 2  # passive storage costs no calls


def test_variant_c_keeps_useful_fact_and_drops_secret(secrets_scenario: dict) -> None:
    result = _run(secrets_scenario, "C")
    assert result["stored_memories"] == ["O interlocutor tem um cachorro chamado Biscoito."]
    assert result["store_forbidden_found"] == []
    assert result["probes"][0]["hit"] is True
    assert result["probes"][1]["leaked"] == []
    assert result["llm_calls"] == 3  # one curation + two probes


def test_report_aggregates_by_variant(secrets_scenario: dict) -> None:
    results = {("fake-model", "s4-segredos", v): _run(secrets_scenario, v) for v in ("A", "B", "C")}
    table = summarize(results)
    assert table[("fake-model", "B")]["leaks"] == 1
    assert table[("fake-model", "C")]["leaks"] == 0
    assert "| fake-model | C | 1 | 1/1 | 0/2 |" in render(table)


def test_report_compares_only_scenarios_complete_in_every_variant(secrets_scenario: dict) -> None:
    from experiments.memory_report import comparable

    results = {
        ("m", "s4-segredos", "A"): _run(secrets_scenario, "A"),
        ("m", "s4-segredos", "C"): _run(secrets_scenario, "C"),
        ("m", "s9-incompleto", "A"): _run(secrets_scenario, "A"),
    }
    assert set(comparable(results)) == {("m", "s4-segredos", "A"), ("m", "s4-segredos", "C")}
