"""What a turn is doing right now, for the owner watching it (docs/STATUS.md).

A turn says each step as it starts ("Abrindo github.com", "Pesquisando “voos Santiago”"), the app
polls and shows the latest one. Kept in this process's memory only: it is a live view, not a
record (the record is the turn's plan, core/decision/turn.py). Only steps that really happen are
said, never a step the turn might take.

The app polling also tells whether the owner is still looking: if it stopped polling while the
turn ran (phone locked, app closed), the reply goes out as a notification too.
"""

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

# Steps kept per turn, and how long a finished turn stays readable.
MAX_STEPS = 12
KEEP_FINISHED_SECONDS = 30.0
# The app polls about once a second; longer than this without a poll means nobody is looking.
WATCH_GRACE_SECONDS = 6.0
LABEL_CHARS = 80
DETAIL_CHARS = 120


@dataclass
class Step:
    label: str
    detail: str | None
    at: float


@dataclass
class _Turn:
    started: float
    steps: list[Step] = field(default_factory=list)
    finished: float | None = None
    last_seen: float | None = None
    cancelled: bool = False


class TurnCancelled(Exception):
    """The owner tapped Parar: the turn stops at its next step."""


_lock = threading.Lock()
_turns: dict[uuid.UUID, _Turn] = {}
_current: ContextVar[uuid.UUID | None] = ContextVar("visao_turn_progress", default=None)


def _clean(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _sweep(now: float) -> None:
    stale = [
        k for k, t in _turns.items() if t.finished and now - t.finished > KEEP_FINISHED_SECONDS
    ]
    for key in stale:
        del _turns[key]


@contextmanager
def tracking(conversation_id: uuid.UUID) -> Iterator[None]:
    """Steps said inside this block, by any code on this thread, belong to this conversation."""
    now = time.monotonic()
    with _lock:
        _sweep(now)
        previous = _turns.get(conversation_id)
        # A poll that came just before the turn started (the app polls right after sending)
        # counts as watching it.
        seen = previous.last_seen if previous else None
        recent = seen is not None and now - seen <= WATCH_GRACE_SECONDS
        _turns[conversation_id] = _Turn(started=now, last_seen=seen if recent else None)
    token = _current.set(conversation_id)
    try:
        yield
    finally:
        _current.reset(token)
        with _lock:
            turn = _turns.get(conversation_id)
            if turn is not None:
                turn.finished = time.monotonic()


def cancel(conversation_id: uuid.UUID) -> bool:
    """Asks the turn in flight to stop. False when nothing is running there."""
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is None or turn.finished:
            return False
        turn.cancelled = True
        return True


def cancelled() -> bool:
    conversation_id = _current.get()
    if conversation_id is None:
        return False
    with _lock:
        turn = _turns.get(conversation_id)
        return bool(turn and turn.cancelled)


def checkpoint() -> None:
    """Raises TurnCancelled when the owner asked this turn to stop."""
    if cancelled():
        raise TurnCancelled()


def step(label: str, detail: str | None = None) -> None:
    """Says what the turn starts doing now (and stops it there if the owner tapped Parar).
    Outside a tracked turn it does nothing."""
    conversation_id = _current.get()
    if conversation_id is None:
        return
    checkpoint()
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is None or turn.finished:
            return
        turn.steps.append(
            Step(
                label=_clean(label, LABEL_CHARS),
                detail=_clean(detail, DETAIL_CHARS) if detail else None,
                at=time.monotonic(),
            )
        )
        del turn.steps[:-MAX_STEPS]


def snapshot(conversation_id: uuid.UUID) -> dict | None:
    """The live view for the app; reading it also marks that the owner is looking."""
    now = time.monotonic()
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is None:
            _turns[conversation_id] = _Turn(started=now, last_seen=now, finished=now)
            return None
        turn.last_seen = now
        return {
            "active": turn.finished is None,
            "elapsed_ms": round(((turn.finished or now) - turn.started) * 1000),
            "steps": [{"label": s.label, "detail": s.detail} for s in turn.steps],
        }


def owner_left(conversation_id: uuid.UUID) -> bool:
    """True when the app was watching this turn and then stopped: the reply should also be a
    notification. A turn nobody ever polled (an old app, a script) never counts as left."""
    now = time.monotonic()
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is None or turn.last_seen is None:
            return False
        return now - turn.last_seen > WATCH_GRACE_SECONDS


def reset() -> None:
    """Tests only."""
    with _lock:
        _turns.clear()
