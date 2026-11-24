"""What a turn is doing right now, for the owner watching it (docs/STATUS.md).

A turn says each step as it starts ("Abrindo github.com", "Pesquisando “voos Santiago”"), the app
polls and shows the latest one. Kept in this process's memory only: it is a live view, not a
record (the record is the turn's plan, core/decision/turn.py). Only steps that really happen are
said, never a step the turn might take.

The app polling also tells whether the owner is still looking: if it stopped polling while the
turn ran (phone locked, app closed), the reply goes out as a notification too.

The same turn is also a list of numbered events for the stream (docs/decisions/0011): `step`,
`delta` (text written so far, a piece at a time), `replace` (the whole text, when it changed
instead of growing), `sources`, `action`, `done` and `error`. Event numbers come from one counter
for the process, so a client that lost the connection resumes after the last one it saw.
"""

import itertools
import re
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from core.conversation.parts import MARK

# Steps kept per turn, and how long a finished turn stays readable.
MAX_STEPS = 12
KEEP_FINISHED_SECONDS = 30.0
# The app polls about once a second; longer than this without a poll means nobody is looking.
WATCH_GRACE_SECONDS = 6.0
LABEL_CHARS = 80
DETAIL_CHARS = 120
# A long reply streams in many pieces; past this the oldest go (a late reader gets a `replace`).
MAX_EVENTS = 3000
# A turn that ended without `done` or `error` (a crash in the route) still ends its stream.
UNCLOSED_GRACE_SECONDS = 10.0
# An unfinished marker at the end of the text so far ("[", "[[", "[[+", "[[pá…").
_OPEN_MARKER = re.compile(r"\[\[?[^\]\n]{0,40}$")
_BREAK = re.compile(r"\s*" + re.escape(MARK) + r"\s*")


@dataclass
class Event:
    id: int
    kind: str
    data: dict[str, Any]


# What kind of tool a step uses, for the call's nanorrobôs (DESIGN.md §6): the Muninn's particles
# take its shape while it runs. A step without a kind ("Pensando", "Escrevendo a resposta") is the
# crow.
KINDS = frozenset({"gmail", "agenda", "pesquisa", "site", "mac", "arquivo"})


@dataclass
class Step:
    label: str
    detail: str | None
    at: float
    kind: str | None = None


@dataclass
class _Turn:
    started: float
    steps: list[Step] = field(default_factory=list)
    finished: float | None = None
    last_seen: float | None = None
    cancelled: bool = False
    # The reply written so far, while it streams (else None). /progress shows it only in voice.
    draft: str | None = None
    modality: str = "text"
    events: list[Event] = field(default_factory=list)
    # The text the stream has given so far: the next `delta` continues it.
    shown: str = ""
    # `done` or `error` went out: the stream of this turn is over.
    closed: bool = False


class TurnCancelled(Exception):
    """The owner tapped Parar: the turn stops at its next step."""


_lock = threading.Lock()
_turns: dict[uuid.UUID, _Turn] = {}
_numbers = itertools.count(1)


def _emit(turn: _Turn, kind: str, data: dict[str, Any]) -> None:
    """Under the lock."""
    turn.events.append(Event(id=next(_numbers), kind=kind, data=data))
    if len(turn.events) > MAX_EVENTS:
        del turn.events[: len(turn.events) - MAX_EVENTS]


def _show(turn: _Turn, text: str, *, final: bool = False) -> None:
    """Under the lock: the text as the stream should show it now, as a delta when it only grew."""
    if text.startswith(turn.shown):
        piece = text[len(turn.shown) :]
        if piece:
            _emit(turn, "delta", {"text": piece})
    else:
        _emit(turn, "replace", {"text": text, "final": final})
    turn.shown = text


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
def tracking(conversation_id: uuid.UUID, modality: str = "text") -> Iterator[None]:
    """Steps said inside this block, by any code on this thread, belong to this conversation."""
    now = time.monotonic()
    with _lock:
        _sweep(now)
        previous = _turns.get(conversation_id)
        # A poll that came just before the turn started (the app polls right after sending)
        # counts as watching it.
        seen = previous.last_seen if previous else None
        recent = seen is not None and now - seen <= WATCH_GRACE_SECONDS
        _turns[conversation_id] = _Turn(
            started=now, last_seen=seen if recent else None, modality=modality
        )
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


def step(label: str, detail: str | None = None, kind: str | None = None) -> None:
    """Says what the turn starts doing now (and stops it there if the owner tapped Parar).
    `kind` is one of KINDS when the step uses a tool. Outside a tracked turn it does nothing."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"unknown step kind: {kind}")
    conversation_id = _current.get()
    if conversation_id is None:
        return
    checkpoint()
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is None or turn.finished:
            return
        said = Step(
            label=_clean(label, LABEL_CHARS),
            detail=_clean(detail, DETAIL_CHARS) if detail else None,
            at=time.monotonic(),
            kind=kind,
        )
        turn.steps.append(said)
        del turn.steps[:-MAX_STEPS]
        _emit(turn, "step", {"label": said.label, "detail": said.detail, "kind": said.kind})


def draft(text: str) -> None:
    """The reply written so far, for the phone to speak sentence by sentence while the rest is
        written. A page marker (`[[página: …]]`) and what follows it are not speech; a bubble break
    (`[[+]]`) is a paragraph. Outside a tracked
        turn it does nothing."""
    conversation_id = _current.get()
    if conversation_id is None:
        return
    # A bubble break is a pause in speech, not the end of it; written as the saved reply
    # writes it (core/conversation/parts.py), so the stream's text grows into the final one.
    text = _BREAK.sub("\n\n", text)
    cut = text.find("[[")
    if cut >= 0:
        text = text[:cut]
    # "[" alone may start a marker still being written, and trailing spaces may turn into a
    # bubble break: both held back until the next piece tells.
    text = _OPEN_MARKER.sub("", text).rstrip()
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is not None and not turn.finished:
            turn.draft = text
            _show(turn, text)


def final(text: str) -> None:
    """The reply as it will be kept (after the rule check): the rest of it as a delta, or the
    whole of it as a `replace` when the check changed what was already shown."""
    conversation_id = _current.get()
    if conversation_id is None:
        return
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is not None and not turn.finished:
            _show(turn, text, final=True)


def publish(conversation_id: uuid.UUID, kind: str, data: dict[str, Any]) -> None:
    """For the route, once the turn is over: `sources`, `action`, and the closing `done` or
    `error`. Nothing when that conversation has no turn here."""
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is None or turn.closed:
            return
        _emit(turn, kind, data)
        if kind in ("done", "error"):
            turn.closed = True


def follow(conversation_id: uuid.UUID, after: int | None, opened: float) -> tuple[list[Event], str]:
    """What the stream sends next, and its state: "waiting" (no turn of this stream yet), "live"
    or "over" (everything up to `done`/`error` is in the list). Reading counts as watching.

    Without `after`, a turn that closed before the stream opened is an earlier one: it waits for
    the next. With `after` (Last-Event-ID), it resumes the turn that holds the newer events."""
    now = time.monotonic()
    with _lock:
        turn = _turns.get(conversation_id)
        if turn is None:
            return [], "waiting"
        turn.last_seen = now
        if not turn.events and turn.finished is not None:
            return [], "waiting"
        if after is None and turn.closed and turn.finished is not None and turn.finished < opened:
            return [], "waiting"
        batch = [e for e in turn.events if e.id > (after or 0)]
        ended = turn.closed or (
            turn.finished is not None and now - turn.finished > UNCLOSED_GRACE_SECONDS
        )
        return batch, "over" if ended else "live"


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
            "steps": [{"label": s.label, "detail": s.detail, "kind": s.kind} for s in turn.steps],
            # In the text chat the stream shows the text; here only a voice call's draft, which
            # the phone speaks sentence by sentence.
            "draft": turn.draft if turn.modality == "voice" else None,
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
