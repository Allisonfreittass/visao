"""Cloud scheduler: private entry point and complete study without a conversation message."""

from pydantic import SecretStr
from sqlalchemy import select

from apps.api.routes import cloud
from apps.api.settings import Settings, get_settings
from apps.worker.handlers import cycle_handler
from core.identity.genesis import run_genesis
from core.policies.autonomy import set_paused
from infrastructure.database.models import ScheduledJob, StudyEntry
from tests.integration.test_study import world

KEY = "test-cron-key-with-at-least-thirty-two-characters"


def test_private_cloud_tick_is_absent_without_configuration(client):
    assert client.post("/internal/cloud/tick").status_code == 404


def test_cloud_tick_rejects_missing_or_wrong_secret(client):
    client.app.dependency_overrides[get_settings] = lambda: Settings(cloud_tick_key=SecretStr(KEY))
    assert client.post("/internal/cloud/tick").status_code == 403
    assert (
        client.post("/internal/cloud/tick", headers={"X-Visao-Cron-Key": "wrong"}).status_code
        == 403
    )


def test_cloud_scheduler_studies_with_no_conversation_or_user_message(client, db, monkeypatch):
    owner, llm, search = world(db)
    settings = Settings(cloud_tick_key=SecretStr(KEY))
    client.app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(
        cloud,
        "build_handlers",
        lambda settings: {"cognitive_cycle": cycle_handler(settings, llm, search)},
    )
    response = client.post("/internal/cloud/tick", headers={"X-Visao-Cron-Key": KEY})
    assert response.status_code == 200
    assert response.json()["jobs"][0] == "done"
    entry = db.scalar(select(StudyEntry))
    assert entry.owner_user_id == owner.id and entry.status == "READY"
    before = len(llm.prompts)
    client.post("/internal/cloud/tick", headers={"X-Visao-Cron-Key": KEY})
    assert len(llm.prompts) == before  # same schedule window and six-hour study cooldown


def test_cloud_tick_respects_pause_before_enqueuing_jobs(client, db):
    run_genesis(db)
    settings = Settings(cloud_tick_key=SecretStr(KEY))
    client.app.dependency_overrides[get_settings] = lambda: settings
    set_paused(db, True, actor_user_id=None, reason="teste")
    response = client.post("/internal/cloud/tick", headers={"X-Visao-Cron-Key": KEY})
    assert response.json()["status"] == "paused"
    assert db.scalar(select(ScheduledJob)) is None
