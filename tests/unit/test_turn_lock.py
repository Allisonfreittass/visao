"""One turn at a time per conversation (core/conversation/turn_lock.py)."""

import threading
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.conversation import turn_lock


@pytest.fixture
def session():
    with Session(create_engine("sqlite://")) as s:
        yield s


def _hold(session, conversation_id, entered, leave):
    with turn_lock.held(session, conversation_id):
        entered.set()
        leave.wait(5)


def test_a_second_turn_of_the_same_conversation_waits_and_then_gives_up(session):
    conversation = uuid.uuid4()
    entered, leave = threading.Event(), threading.Event()
    first = threading.Thread(target=_hold, args=(session, conversation, entered, leave))
    first.start()
    entered.wait(5)
    try:
        with pytest.raises(turn_lock.Busy), turn_lock.held(session, conversation, wait=0.05):
            pass
        # Another conversation is not held up.
        with turn_lock.held(session, uuid.uuid4(), wait=0.05):
            pass
    finally:
        leave.set()
        first.join(5)
    with turn_lock.held(session, conversation, wait=0.05):
        pass
    assert turn_lock._locks == {}  # nothing left behind


def test_the_database_key_fits_a_signed_bigint():
    for value in (uuid.UUID(int=0), uuid.UUID(int=(1 << 128) - 1), uuid.uuid4()):
        assert -(1 << 63) <= turn_lock._key(value) < (1 << 63)
