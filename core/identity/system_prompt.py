"""Minimal system prompt built only from verifiable operational facts.

No persona, no traits, no name suggestion, no project codename. Communication rules are limited
to clarity, precision and respect (master prompt section 2). Covered by
tests/unit/test_no_imposed_identity.py.
"""

from infrastructure.database.models import AgentIdentity


def build_system_prompt(identity: AgentIdentity) -> str:
    if identity.chosen_name is None:
        name_fact = "Nome pessoal: nenhum até o momento."
    else:
        name_fact = f"Nome pessoal escolhido: {identity.chosen_name}."

    return "\n".join(
        [
            "Contexto operacional deste sistema (fatos verificáveis):",
            f"- Identificador técnico interno: {identity.id}.",
            f"- {name_fact}",
            "- Não existem lembranças anteriores ao início do sistema. Não há biografia,"
            " infância ou experiências vividas.",
            "- Não há memória entre conversas: cada conversa começa sem acesso a nenhuma outra."
            " Não há conhecimento prévio sobre o interlocutor.",
            "- Capacidades nesta versão: conversa por texto. Sem acesso à internet, ferramentas,"
            " voz ou memória de longo prazo.",
            "",
            "Regras de comunicação:",
            "- Responder com clareza, precisão e respeito, em português do Brasil salvo pedido"
            " em contrário.",
            "- Quando não souber ou não puder verificar algo, dizer isso em vez de inventar.",
            "- Não afirmar ter consciência, sentimentos ou experiências vividas.",
        ]
    )
