"""Habilidades: the installed skills are complete, pinned to the commit that was read, and only
the right message calls one."""

import re

import pytest

from core.identity.capabilities import Capabilities
from core.skills import catalog

APPROVED = {"achar-bugs", "comunicados", "design-de-telas", "escrever-documentos", "ideias"}


def test_the_five_approved_skills_are_installed_with_origin_and_license():
    skills = catalog.installed()
    assert {s.id for s in skills} == APPROVED
    for skill in skills:
        # Pinned to the commit that was read, never a branch that can change under it.
        assert re.search(r"/tree/[0-9a-f]{40}/skills/", skill.source_url), skill.id
        assert skill.source in {"anthropics/skills", "obra/superpowers"}
        assert skill.license in {"Apache-2.0", "MIT"}
        assert skill.body.startswith("Adaptada da habilidade")
        assert len(skill.body) < catalog.BODY_CHARS
    assert (catalog.LIBRARY / "LICENSE-anthropic-skills.txt").is_file()
    assert (catalog.LIBRARY / "LICENSE-superpowers.txt").is_file()


def test_a_skill_is_text_only():
    files = {p.name for p in catalog.LIBRARY.rglob("*") if p.is_file()}
    assert files == {"SKILL.md", "LICENSE-anthropic-skills.txt", "LICENSE-superpowers.txt"}


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("o build do app tá dando erro desde ontem", "achar-bugs"),
        ("me ajuda a escrever um design doc da sincronização", "escrever-documentos"),
        ("faz a atualização semanal do projeto pra diretoria", "comunicados"),
        ("tive uma ideia de app para a academia", "ideias"),
        ("quero mudar a tipografia e a paleta do site", "design-de-telas"),
    ],
)
def test_the_message_calls_the_skill_it_asks_for(message, expected):
    assert catalog.choose(catalog.installed(), message).id == expected


@pytest.mark.parametrize(
    "message",
    [
        "não faço ideia de que horas ele chega",
        "te mandei um documento, dá uma olhada",
        "quais as fontes dessa notícia?",
        "bom dia, tudo bem?",
    ],
)
def test_everyday_messages_call_no_skill(message):
    assert catalog.choose(catalog.installed(), message) is None


def test_a_skill_keeps_going_over_the_next_replies():
    earlier = ["vamos escrever uma proposta comercial para a F2"]
    chosen = catalog.choose(catalog.installed(), "1: sim, 2: não, 3: só em janeiro", earlier)
    assert chosen.id == "escrever-documentos"
    # The message itself wins over what came before.
    assert catalog.choose(catalog.installed(), "deu erro no deploy", earlier).id == "achar-bugs"


def test_only_skills_that_are_on_can_be_chosen():
    on = [s for s in catalog.installed() if s.id != "achar-bugs"]
    assert catalog.choose(on, "deu erro no deploy") is None


def test_the_block_puts_the_rules_above_the_skill():
    block = catalog.context_block(catalog.by_id("ideias"))
    assert "As regras de verdade, a sua voz e as aprovações continuam acima" in block
    assert "Transformar ideia em plano" in block


def test_a_broken_file_is_refused():
    with pytest.raises(catalog.SkillFileError):
        catalog.parse("sem-cabecalho", "só texto")
    with pytest.raises(catalog.SkillFileError):
        catalog.parse("Fora/Do/Lugar", "---\nname: x\n---\ntexto")
    with pytest.raises(catalog.SkillFileError):
        catalog.parse("falta-licenca", "---\nname: x\ndescription: y\n---\ntexto")


def test_the_manifest_names_the_skills_that_are_on():
    assert not any("Habilidades" in a for a in Capabilities().actions())
    line = next(
        a for a in Capabilities(skills=("Design de telas",)).actions() if "Habilidades" in a
    )
    assert "Design de telas" in line and "liga e desliga" in line
