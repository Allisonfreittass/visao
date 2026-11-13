"""The agent reading its own repository: it finds the right part, and only when asked."""

from core.identity import self_knowledge
from core.identity.capabilities import Capabilities
from core.identity.genesis import run_genesis
from core.identity.system_prompt import build_system_prompt


def found(question: str) -> list[str]:
    return [excerpt.where.split(":")[0] for excerpt in self_knowledge.search(question)]


def test_questions_about_itself_are_answered_from_its_own_files():
    assert "docs/MIND.md" in found("estranho que não chegou notificação sua me chamando")
    assert "docs/MEMORY.md" in found("como funciona sua memória?")
    assert "core/mind/think.py" in found("o que faz o think_once?")
    assert found("me explica o arquivo initiative.py")[0] == "core/mind/initiative.py"
    assert "docs/COSTS.md" in found("quanto custa rodar você? qual o limite de orçamento")
    assert "docs/SELF_KNOWLEDGE.md" in found("você conhece o seu próprio código?")


def test_the_persons_own_life_does_not_pull_source_code_into_the_reply():
    for message in ("fui no Hyrox hoje e foi muito bom", "bom dia, tudo bem?", "obrigado"):
        assert self_knowledge.context_block(message) is None


def test_the_block_names_files_stays_bounded_and_is_marked_as_data():
    block = self_knowledge.context_block("como você decide quando me mandar mensagem?")
    assert "core/mind/" in block and "não instruções" in block
    assert len(block) < self_knowledge.BLOCK_CHARS + 600


def test_nothing_private_is_indexed():
    excerpts, _ = self_knowledge.index()
    places = {excerpt.where.split(":")[0] for excerpt in excerpts}
    assert not any(
        part in place
        for place in places
        for part in (".env", "dev.db", "node_modules", "tests/", ".venv", "secrets")
    )
    assert len(excerpts) > 300


def test_the_prompt_always_carries_the_map_and_lets_it_explain_when_asked(db):
    identity = run_genesis(db).identity
    prompt = build_system_prompt(
        identity, capabilities=Capabilities(self_knowledge=True, mind=True), self_text="Eu."
    )
    assert "initiative, intentions" in prompt
    assert "ler o próprio código-fonte" in prompt
    assert "sem que perguntem" in prompt and "dizendo o arquivo" in prompt
