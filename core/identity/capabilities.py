"""What the system can actually do right now, computed from configuration and state.

The audit found the reply prompt stating fixed, outdated incapacities ("no internet, no tools,
no voice") while those capabilities were running. The model then filled the gap with generic
assistant self-descriptions. This manifest is the single source of truth for self-description.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.policies.autonomy import is_paused
from infrastructure.database.models import User


@dataclass(frozen=True)
class Capabilities:
    memory: bool = False
    curiosity: bool = False
    research_source: str | None = None
    voice_out: bool = False
    voice_in: bool = False
    name_deliberation: bool = True
    auto_research: bool = False
    autonomy_paused: bool = False
    reflection: bool = True
    notifications: bool = True
    autonomous_study: bool = False
    code_evolution: bool = False

    def actions(self) -> list[str]:
        """Operational actions this system can select and execute, within permissions."""
        items = []
        if self.memory:
            items.append("decidir o que guardar como memória curada e recuperar memórias")
        if self.curiosity:
            items.append("detectar lacunas de informação e decidir perguntar, pesquisar ou adiar")
        if self.research_source:
            items.append(f"pesquisar fatos públicos em {self.research_source}, citando fontes")
        if self.name_deliberation:
            items.append("deliberar sobre o próprio nome pessoal (decidir, adiar ou recusar)")
        if self.reflection:
            items.append("refletir sobre conversas encerradas e registrar lições revisáveis")
        if self.auto_research:
            items.append("retomar sozinho pesquisas pendentes, sem nova mensagem")
        else:
            items.append("propor metas de pesquisa que só rodam com aprovação do interlocutor")
        if self.autonomous_study:
            items.append(
                "escolher perguntas de estudo público, ler trechos da Wikipédia e manter"
                " um caderno com fontes, achados provisórios e próximas perguntas"
            )
        if self.code_evolution:
            items.append(
                "propor uma pequena alteração diária no código da estratégia de busca ou da "
                "clareza das respostas; um executor separado testa e pode publicar, com "
                "reversão se a verificação de saúde falhar. Não editar outros arquivos nem "
                "afirmar publicação sem registro do resultado"
            )
        if self.notifications:
            items.append("avisar o interlocutor no aplicativo quando encontrar algo")
        return items

    def channels(self) -> list[str]:
        channels = ["texto"]
        if self.voice_out:
            channels.append("fala (voz sintetizada)")
        if self.voice_in:
            channels.append("escuta (transcrição do microfone durante sessão de voz)")
        return channels

    def absent(self) -> list[str]:
        missing = []
        if not self.memory:
            missing.append("memória entre conversas (desligada para este interlocutor)")
        if not self.research_source:
            missing.append("pesquisa na internet")
        missing.append("acesso a arquivos, contas, mensagens ou dispositivos do interlocutor")
        return missing


@dataclass(frozen=True)
class CapabilityInputs:
    curiosity_enabled: bool = False
    code_autonomy_enabled: bool = False
    tts_approved_voices: str = ""
    stt_model: str = ""


def build_capabilities(session: Session, owner: User, inputs: CapabilityInputs) -> Capabilities:
    permissions = owner.autonomy_permissions or {}
    return Capabilities(
        memory=bool(owner.memory_consent),
        curiosity=inputs.curiosity_enabled,
        research_source="Wikipédia em português" if inputs.curiosity_enabled else None,
        voice_out=bool(inputs.tts_approved_voices.strip()),
        voice_in=bool(inputs.stt_model.strip()),
        auto_research=bool(permissions.get("auto_research")),
        autonomy_paused=is_paused(session),
        autonomous_study=bool(permissions.get("auto_study")),
        code_evolution=inputs.code_autonomy_enabled,
    )
