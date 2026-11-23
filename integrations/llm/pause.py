"""The pause of a provider whose quota ran out, kept in the database (ADR-0022).

Before, each process (the API, the worker) found out on its own and paused for a fixed 15 min in
memory. Now the pause is one row (SystemFlag), shared by every process, and lasts until the reset
the provider itself announced, when it announced one. Same short transactions as the budget
ledger: never a lock held during a model call.
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from infrastructure.database.models import SystemFlag

logger = logging.getLogger(__name__)

FLAG = "llm_pause_v1"
DEFAULT_SECONDS = 15 * 60
MIN_SECONDS = 60
MAX_SECONDS = 24 * 3600


def pause_seconds(retry_at: float | None, now: float) -> float:
    """How long to skip a provider: until its announced reset, kept between 1 min and 24 h."""
    if retry_at is None:
        return DEFAULT_SECONDS
    return min(max(retry_at - now, MIN_SECONDS), MAX_SECONDS)


def key(name: str, model: str, credential: str = "") -> str:
    """A new API key (its fingerprint, never the key) starts with no pause."""
    return f"{name}|{model}|{credential}" if credential else f"{name}|{model}"


class PauseBoard:
    """Reads and writes {provider|model: paused until, in seconds since the epoch}."""

    def __init__(
        self, factory: Callable[[], Session], *, clock: Callable[[], float] = time.time
    ) -> None:
        self._factory = factory
        self._clock = clock

    def snapshot(self) -> dict[str, float]:
        """The pauses still running. Empty when the database cannot be read: a broken read must
        not silence the agent (the in-memory pause of the process still applies)."""
        try:
            with self._factory() as db:
                flag = db.get(SystemFlag, FLAG)
                value = dict(flag.value or {}) if flag else {}
        except Exception:  # noqa: BLE001
            logger.warning("llm pause board unreadable", extra={"event": "llm_pause_unreadable"})
            return {}
        now = self._clock()
        return {k: float(v) for k, v in value.items() if isinstance(v, int | float) and v > now}

    def pause(self, name: str, model: str, until: float, credential: str = "") -> None:
        try:
            with self._factory() as db:
                dialect = db.get_bind().dialect.name
                insert = sqlite_insert if dialect == "sqlite" else pg_insert
                db.execute(insert(SystemFlag).values(name=FLAG, value={}).on_conflict_do_nothing())
                flag = db.scalar(
                    select(SystemFlag).where(SystemFlag.name == FLAG).with_for_update()
                )
                assert flag is not None
                now = self._clock()
                value = {
                    k: v
                    for k, v in (flag.value or {}).items()
                    if isinstance(v, int | float) and v > now
                }
                entry = key(name, model, credential)
                value[entry] = max(until, float(value.get(entry, 0)))
                flag.value = value
                db.commit()
        except Exception:  # noqa: BLE001
            logger.warning("llm pause not saved", extra={"event": "llm_pause_unsaved"})
            return
        logger.info(
            f"llm provider {name} paused for {int(until - self._clock())}s",
            extra={"event": "llm_paused", "provider": name, "model": model},
        )
