"""A reply in bubbles (core/conversation/parts.py): one message, the whole text in `content`,
the bubbles in `parts`; never a marker left on screen, never a break inside code."""

from core.conversation import progress
from core.conversation.parts import MARK, split


def test_markers_split_the_reply_and_content_keeps_it_whole():
    content, parts = split(f"Consigo ver ao vivo.\n{MARK}\nDe onde vocês saem?")
    assert parts == ["Consigo ver ao vivo.", "De onde vocês saem?"]
    assert content == "Consigo ver ao vivo.\n\nDe onde vocês saem?"
    assert MARK not in content


def test_a_reply_without_markers_is_one_bubble():
    assert split("Só uma parte.") == ("Só uma parte.", None)


def test_never_more_than_three_bubbles():
    _, parts = split(MARK.join(["um", "dois", "três", "quatro"]))
    assert parts == ["um", "dois", "três\n\nquatro"]


def test_a_marker_inside_code_is_not_a_break_and_never_shown():
    text = f"Assim:\n```python\nx = 1\n{MARK}\ny = 2\n```\n{MARK}\nPronto."
    content, parts = split(text)
    assert parts is not None and len(parts) == 2
    assert parts[1] == "Pronto." and MARK not in content


def test_empty_bubbles_are_dropped():
    assert split(f"{MARK}\nOi\n{MARK}\n{MARK}") == ("Oi", None)


def test_in_a_voice_call_a_bubble_break_is_a_pause_not_the_end(monkeypatch):
    import uuid

    conversation = uuid.uuid4()
    with progress.tracking(conversation):
        progress.draft(f"Consigo ver.{MARK}De onde vocês saem?")
        assert progress.snapshot(conversation)["draft"] == "Consigo ver.\n\nDe onde vocês saem?"
