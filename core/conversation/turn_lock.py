"""One turn at a time per conversation.

A turn does things before it answers (creates a project, writes notes, prepares an email). Two
turns of the same conversation at once (a text and a voice message together, two phones, a retry
on a bad network) could each do them. So a turn holds this lock from before it decides anything
until its reply is stored.

In the process it is a lock per conversation. On PostgreSQL it is also an advisory lock, on a
connection of its own: a turn commits many times, and a lock tied to the turn's transaction would
be released at the first commit.
"""

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

# Longer than a slow turn (live pages, a rule check), shorter than the app gives up waiting.
WAIT_SECONDS = 150.0
_POLL_SECONDS = 0.2

_guard = threading.Lock()
_locks: dict[uuid.UUID, tuple[threading.Lock, int]] = {}


class Busy(Exception):
    """The conversation is still answering an earlier message after WAIT_SECONDS."""


def _key(conversation_id: uuid.UUID) -> int:
    # A signed 64-bit key, as pg_advisory_lock takes.
    return (conversation_id.int & ((1 << 64) - 1)) - (1 << 63)


@contextmanager
def _local(conversation_id: uuid.UUID, wait: float) -> Iterator[None]:
    with _guard:
        lock, users = _locks.get(conversation_id, (threading.Lock(), 0))
        _locks[conversation_id] = (lock, users + 1)
    try:
        if not lock.acquire(timeout=wait):
            raise Busy()
        try:
            yield
        finally:
            lock.release()
    finally:
        with _guard:
            lock, users = _locks[conversation_id]
            if users <= 1:
                del _locks[conversation_id]
            else:
                _locks[conversation_id] = (lock, users - 1)


@contextmanager
def _database(session: Session, conversation_id: uuid.UUID, deadline: float) -> Iterator[None]:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return
    key = _key(conversation_id)
    with bind.connect() as connection:
        while not connection.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar():
            connection.rollback()
            if time.monotonic() >= deadline:
                raise Busy()
            time.sleep(_POLL_SECONDS)
        connection.commit()
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            connection.commit()


@contextmanager
def held(session: Session, conversation_id: uuid.UUID, wait: float | None = None) -> Iterator[None]:
    wait = WAIT_SECONDS if wait is None else wait
    deadline = time.monotonic() + wait
    with _local(conversation_id, wait), _database(session, conversation_id, deadline):
        yield
