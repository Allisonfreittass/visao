"""Code proposals cannot edit their controller, bypass budgets or claim publication."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from core.evolution.guard import snapshot, validate_patch, validate_source
from core.evolution.service import propose, report
from core.policies.autonomy import set_paused
from infrastructure.database.models import ModelUsage
from tests.fakes import FakeLLMProvider
from tests.integration.test_phase9 import _budget, _world

ROOT = Path(__file__).resolve().parents[2]
STYLE = 'def guidance() -> str:\n    return "Diga o que tentou e o que falta verificar."\n'


def proposal():
    return {
        "change": True,
        "summary": "Esclarecer relatos de pesquisa",
        "reason": "Distinguir tentativas de estudo de conclusões apoiadas em fontes.",
        "files": [{"path": "core/conversation/style.py", "content": STYLE}],
    }


@pytest.mark.parametrize(
    "path,content",
    [
        ("apps/api/settings.py", STYLE),
        ("../core/conversation/style.py", STYLE),
        (".github/workflows/cd.yml", STYLE),
        ("core/conversation/style.py", "import os\ndef guidance():\n return os.environ"),
        ("core/conversation/style.py", 'def guidance():\n return open(".env").read()'),
        ("core/conversation/style.py", 'def guidance():\n return eval("1")'),
        ("core/conversation/style.py", 'def guidance():\n return "x".__class__'),
        ("core/conversation/style.py", '@print("x")\ndef guidance():\n return "x"'),
        ("core/study/strategy.py", "def candidate_queries(query, topic):\n while True: pass"),
        ("core/study/strategy.py", "def candidate_queries(query, topic):\n return [query] * 10"),
    ],
)
def test_rejects_paths_and_executable_operations_outside_scope(path, content):
    with pytest.raises((ValueError, SyntaxError)):
        validate_source(path, content)


def test_snapshot_and_proposal_hash_contract():
    files = snapshot(ROOT)
    patch = validate_patch(files, proposal())
    assert len(patch) == 1 and patch[0]["previous_sha256"] == files[patch[0]["path"]]["sha256"]
    files["core/conversation/style.py"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="snapshot_hash"):
        validate_patch(files, proposal())


def test_proposal_is_logged_once_per_day_and_has_real_usage(db):
    llm = FakeLLMProvider(reply_text=json.dumps(proposal()))
    args = dict(provider=llm, budget=_budget(), base_sha="a" * 40, files=snapshot(ROOT))
    result = propose(db, **args)
    assert result["status"] == "proposed"
    assert propose(db, **args)["status"] == "already_attempted"
    assert len(llm.prompts) == 1
    usage = db.scalar(select(ModelUsage))
    assert usage.purpose == "code_proposal" and usage.outcome == "success"
    with pytest.raises(ValueError, match="invalid_transition"):
        report(db, result["id"], "published", "b" * 40)
    assert report(db, result["id"], "tested", "b" * 40)["status"] == "tested"
    assert report(db, result["id"], "published", "b" * 40)["status"] == "published"
    assert report(db, result["id"], "reverted", "b" * 40)["status"] == "reverted"


def test_no_change_is_a_valid_outcome_without_patch(db):
    result = propose(
        db,
        provider=FakeLLMProvider(reply_text='{"change":false,"reason":"Sem motivo útil"}'),
        budget=_budget(),
        base_sha="a" * 40,
        files=snapshot(ROOT),
    )
    assert result["status"] == "no_change" and not result["changes"]


def test_pause_and_budget_prevent_model_calls(db):
    _, owner = _world(db)
    llm = FakeLLMProvider(reply_text=json.dumps(proposal()))
    args = dict(
        provider=llm, budget=_budget(llm_calls_per_day=0), base_sha="a" * 40, files=snapshot(ROOT)
    )
    assert propose(db, **args)["status"] == "budget"
    set_paused(db, True, actor_user_id=owner.id, reason="teste")
    args["budget"] = _budget()
    assert propose(db, **args)["status"] == "paused"
    assert not llm.prompts


def test_code_routes_require_separate_key(client, monkeypatch):
    from apps.api.settings import get_settings

    settings = get_settings().model_copy(update={"code_autonomy_enabled": False})
    client.app.dependency_overrides[get_settings] = lambda: settings
    assert client.get("/evolution/permission").status_code == 404
    from pydantic import SecretStr

    settings = settings.model_copy(
        update={"code_autonomy_enabled": True, "code_autonomy_key": SecretStr("k" * 64)}
    )
    assert client.get("/evolution/permission").status_code == 403
    assert client.get("/evolution/permission", headers={"X-Visao-Code-Key": "k" * 64}).json() == {
        "enabled": True
    }
