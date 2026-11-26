"""Habilidades: the installed skills are complete, pinned to the commit that was read, and only
the right message calls one."""

import re

import pytest

from core.identity.capabilities import Capabilities
from core.skills import catalog

APPROVED = {
    "achar-bugs",
    "comunicados",
    "design-de-telas",
    "escrever-documentos",
    "ideias",
    # 25/11/2026, the owner's "Jarvis" set, from anthropics/knowledge-work-plugins.
    "ler-contrato",
    "pesquisa-a-fundo",
    "preparar-reuniao",
    "resumo-reuniao",
    "revisao-semana",
    "revisar-codigo",
    "triagem-email",
}


def test_the_approved_skills_are_installed_with_origin_and_license():
    skills = catalog.installed()
    assert {s.id for s in skills} == APPROVED
    for skill in skills:
        # Pinned to the commit that was read, never a branch that can change under it.
        assert re.search(r"/tree/[0-9a-f]{40}/(?:[\w-]+/)?skills/", skill.source_url), skill.id
        assert skill.source in {
            "anthropics/skills",
            "obra/superpowers",
            "anthropics/knowledge-work-plugins",
        }
        assert skill.license in {"Apache-2.0", "MIT"}
        assert skill.body.startswith("Adaptada da habilidade")
        assert len(skill.body) < catalog.BODY_CHARS
    assert (catalog.LIBRARY / "LICENSE-anthropic-skills.txt").is_file()
    assert (catalog.LIBRARY / "LICENSE-superpowers.txt").is_file()
    assert (catalog.LIBRARY / "LICENSE-knowledge-work-plugins.txt").is_file()


def test_a_skill_is_text_only():
    files = {p.name for p in catalog.LIBRARY.rglob("*") if p.is_file()}
    assert files == {
        "SKILL.md",
        "LICENSE-anthropic-skills.txt",
        "LICENSE-superpowers.txt",
        "LICENSE-knowledge-work-plugins.txt",
    }


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("o build do app tá dando erro desde ontem", "achar-bugs"),
        ("me ajuda a escrever um design doc da sincronização", "escrever-documentos"),
        ("faz a atualização semanal do projeto pra diretoria", "comunicados"),
        ("tive uma ideia de app para a academia", "ideias"),
        ("quero mudar a tipografia e a paleta do site", "design-de-telas"),
        ("o que precisa de mim no email hoje?", "triagem-email"),
        ("me prepara pra reunião de amanhã com o Marcos", "preparar-reuniao"),
        ("faz a ata da reunião com essas notas", "resumo-reuniao"),
        ("faz uma pesquisa a fundo sobre baterias de sódio", "pesquisa-a-fundo"),
        ("posso assinar esse contrato de aluguel?", "ler-contrato"),
        ("revisa esse PR antes do merge", "revisar-codigo"),
        ("como foi minha semana? e planeja a próxima", "revisao-semana"),
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
        "depois da reunião eu te falo",
        "semana que vem a gente vê isso",
        "mandei um email pro João ontem",
        "quantos commits teve hoje no visao?",
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


def test_only_ways_of_working_without_a_conversation_go_to_the_arm():
    arm = {s.id for s in catalog.installed() if s.arm}
    assert arm == {"achar-bugs", "design-de-telas", "revisar-codigo"}
    with pytest.raises(catalog.SkillFileError):
        catalog.parse(
            "braco-talvez",
            "---\nname: x\ndescription: y\ntriggers: z\nsource: a\nsource_url: b\n"
            "license: MIT\ninstalled_on: 2026-11-25\narm: talvez\n---\ntexto",
        )


def test_the_arm_block_points_to_its_own_tools():
    block = catalog.arm_block(catalog.by_id("achar-bugs"))
    assert "rodar_testes" in block and "resumo do terminar" in block
    assert "Regra de ferro" in block


def test_the_manifest_names_the_arm_skills_only_with_a_mac():
    names = ("Revisar código",)
    assert not any("Braço no Mac" in a for a in Capabilities(arm_skills=names).actions())
    with_mac = Capabilities(arm_skills=names, mac_projects=("visao",)).actions()
    assert any("Braço no Mac as habilidades Revisar código" in a for a in with_mac)
