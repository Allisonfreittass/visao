import re

from core.conversation.service import build_context
from core.identity.system_prompt import build_system_prompt
from infrastructure.database.models import AgentIdentity, Message


def _msg(role: str, content: str) -> Message:
    return Message(role=role, content=content)


def test_context_keeps_most_recent_within_budget() -> None:
    history = [_msg("user", "a" * 600), _msg("assistant", "b" * 600), _msg("user", "c" * 300)]
    context = build_context(history, char_budget=1000)
    assert [m.content[0] for m in context] == ["b", "c"]


def test_context_always_keeps_latest_message() -> None:
    context = build_context([_msg("user", "x" * 5000)], char_budget=1000)
    assert len(context) == 1


def test_system_prompt_without_name() -> None:
    prompt = build_system_prompt(AgentIdentity(chosen_name=None, genesis_version="2.1"))
    assert "Nome pessoal: nenhum até o momento." in prompt
    assert not re.search(r"(?i)\bvis(ã|a)o\b|\bvision\b", prompt)
    assert not re.search(r"(?i)\b(escolh|choose|sugir|suggest)", prompt)


def test_system_prompt_with_chosen_name() -> None:
    prompt = build_system_prompt(AgentIdentity(chosen_name="Escolhido", genesis_version="2.1"))
    assert "Nome pessoal escolhido: Escolhido." in prompt
