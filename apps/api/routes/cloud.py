"""Private, bounded cloud scheduler entry point; never usable with a user's chat token."""

import secrets
import threading
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from apps.api.deps import AppSettings, SessionFactory
from apps.worker.handlers import build_handlers
from apps.worker.runner import run_once
from core.autonomy.cycle import schedule
from core.policies.autonomy import is_paused
from infrastructure.database.models import SystemFlag

router = APIRouter(include_in_schema=False)
_tick_lock = threading.Lock()


def _heartbeat(db, status: str, jobs: list[str]) -> None:
    now = datetime.now(UTC)
    value = {"last_tick_at": now.isoformat(), "status": status, "jobs": jobs}
    flag = db.get(SystemFlag, "cloud_scheduler")
    if flag is None:
        db.add(SystemFlag(name="cloud_scheduler", value=value, updated_at=now))
    else:
        flag.value, flag.updated_at = value, now
    db.commit()


@router.post("/internal/cloud/tick")
def tick(
    settings: AppSettings,
    factory: SessionFactory,
    cron_key: Annotated[str | None, Header(alias="X-Visao-Cron-Key")] = None,
) -> dict:
    expected = settings.cloud_tick_key
    if expected is None:
        raise HTTPException(404, "Não encontrado")
    if cron_key is None or not secrets.compare_digest(cron_key, expected.get_secret_value()):
        raise HTTPException(403, "Não autorizado")
    if not _tick_lock.acquire(blocking=False):
        return {"status": "busy", "jobs": []}
    try:
        with factory() as db:
            if is_paused(db):
                _heartbeat(db, "paused", [])
                return {"status": "paused", "jobs": []}
            schedule(db, datetime.now(UTC), settings.autonomy_cycle_minutes)
        handlers = build_handlers(settings)
        started = time.monotonic()
        outcomes = []
        # Short work bursts, rather than a permanently running poll loop that keeps the
        # database awake. Job leases and budgets are the same as in the local worker.
        for _ in range(3):
            if time.monotonic() - started >= settings.autonomy_max_seconds:
                break
            outcome = run_once(factory, handlers, "cloud-cron")
            outcomes.append(outcome)
            if outcome in {"idle", "paused"}:
                break
        status = "failed" if any(o in {"failed", "unknown_kind"} for o in outcomes) else "ok"
        with factory() as db:
            _heartbeat(db, status, outcomes)
        return {"status": status, "jobs": outcomes}
    finally:
        _tick_lock.release()
