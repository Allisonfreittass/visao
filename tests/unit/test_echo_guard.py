"""A reply that only hands the question back is caught in code; the prompt says to act."""

from core.conversation.echo_guard import echoes
from core.identity.system_prompt import ACT_RULES, QUESTION_RULE


def test_a_reworded_question_is_an_echo():
    asked = "Quantos commits foram feitos hoje no repositório Visao?"
    assert echoes(asked, "Você quer saber quantos commits foram feitos hoje no repositório Visao?")
    assert echoes("quantos commits teve hoje no visao?", "Quantos commits teve hoje no visao?")


def test_an_answer_or_a_real_question_is_not():
    asked = "quantos commits teve hoje no visao?"
    assert not echoes(asked, "Hoje foram 5 commits no visao.")
    assert not echoes(asked, "Foram 5. Quer que eu liste as mensagens?")
    assert not echoes("manda um email pro João", "Mando do seu Gmail ou do trabalho?")


def test_the_prompt_tells_it_to_act_and_ask_only_when_a_mistake_is_costly():
    rules = " ".join(ACT_RULES)
    assert "faça na hora" in rules
    assert "ambiguidade real" in rules and "errar custa caro" in rules
    assert "Proibido devolver a pergunta" in rules
    assert "nunca pesquise na web" in rules
    assert "Pedido não leva pergunta" in QUESTION_RULE


def test_facts_guard_reads_denials_and_leaves_true_replies_alone():
    from core.conversation import facts_guard

    assert facts_guard.github_contradicted("Não abri o GitHub ainda.", ["42"])
    assert facts_guard.github_contradicted("Teve bastante coisa hoje!", ["42"])
    assert not facts_guard.github_contradicted("Hoje foram 42 commits.", ["42"])
    assert not facts_guard.github_contradicted("Foram 142 linhas e 42 commits.", ["42"])
    assert facts_guard.fix_mac_off("Tudo certo. Seu Mac está ligado agora.") is None
    assert facts_guard.fix_mac_off("Não estou conectado no momento ao seu Mac.") is not None
