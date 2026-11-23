"""What the system can actually do right now, computed from configuration and state.

The audit found the reply prompt stating fixed, outdated incapacities ("no internet, no tools,
no voice") while those capabilities were running. The model then filled the gap with generic
assistant self-descriptions. This manifest is the single source of truth for self-description.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core import llm_routing
from core.initiatives import push
from core.policies.autonomy import is_paused
from infrastructure.database.models import ArmDevice, GoogleAccount, PushSubscription, User


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
    mind: bool = False
    read_links: bool = False
    # Photos and files sent in the chat (core/conversation/attachments.py).
    attachments: bool = False
    # Pages it writes and publishes at a secret link (core/conversation/artifacts.py).
    pages: bool = False
    # A real browser for live pages (core/browse.py).
    browser: bool = False
    # This is the owner's one continuous conversation (ADR-0014).
    continuous: bool = False
    # "HH:MM" of the morning briefing (ADR-0017); None when the owner turned it off.
    morning_briefing: str | None = None
    mac_projects: tuple[str, ...] = ()
    google: bool = False
    # Devices that get a push with the app closed; None when this was not looked up.
    push_devices: int | None = None
    push_configured: bool = True
    self_knowledge: bool = False
    # Ajustes > Escolha do provedor on "Por tarefa" (core/llm_routing.py, ADR-0022).
    provider_by_task: bool = False

    def actions(self) -> list[str]:
        """Operational actions this system can select and execute, within permissions."""
        items = []
        if self.memory:
            items.append("decidir o que guardar como memória curada e recuperar memórias")
        if self.curiosity:
            items.append("detectar lacunas de informação e decidir perguntar, pesquisar ou adiar")
        if self.research_source:
            items.append(f"pesquisar fatos públicos em {self.research_source}, citando fontes")
        if self.read_links:
            items.append(
                "abrir os links que o interlocutor manda (páginas públicas e repositórios do "
                "GitHub) e comentar o conteúdo lido"
            )
        if self.attachments:
            items.append(
                "ver as fotos e ler os arquivos (PDF, texto, código, planilhas em CSV) que o "
                "interlocutor manda no chat, enquanto estão nas mensagens recentes"
            )
            items.append(
                "receber o que o interlocutor compartilhar do iPhone de outro app (pela folha de "
                "compartilhar: uma página, um trecho de texto, fotos, prints, PDFs); chega aqui "
                "na conversa e a sua resposta vai como aviso no celular"
            )
        if self.browser:
            items.append(
                "abrir sites ao vivo num navegador de verdade quando o interlocutor pede algo que "
                "muda com o tempo (preços de passagens e hotéis, aulas, ingressos, aluguéis, "
                "disponibilidade, cotações, horários, preços de produtos); só lê: não faz login, "
                "não compra, não reserva, não preenche cadastro, e quando um site pede "
                "verificação de robô, para e avisa; quando um site recusa, tenta outro"
            )
            items.append(
                "cotar sem travar: quando faltam origem, datas ou pessoas, supor (a origem sai de "
                "onde o interlocutor mora, as datas de uma janela no mês dito, 2 adultos na "
                "dúvida) e dizer no começo da resposta o que foi suposto; com preços lidos, o "
                "sistema monta embaixo da resposta uma tabela de até 5 opções com o total do "
                "grupo, então não repita a tabela no texto"
            )
            items.append(
                "achar lugares perto do interlocutor agora (farmácia aberta, restaurante, posto, "
                "mercado) quando ele pergunta e a mensagem vem com a localização do celular (ele "
                "liga 'Usar minha localização' em Ajustes): o sistema abre o Google Maps onde ele "
                "está e você responde com nome, endereço e se está aberto; você nunca vê nem diz "
                "coordenadas, e a posição não fica guardada"
            )
            items.append(
                "deixar uma cotação num painel vivo no Início, só com o sim do interlocutor: ele "
                "se confere sozinho uma vez por dia, a cada 3 horas quando o total está perto da "
                "meta, e avisa na hora no celular quando fica abaixo da meta; o interlocutor "
                "muda o painel pela conversa (bairro, datas, pessoas, meta, ou 'me avisa se "
                "ficar abaixo de R$ X')"
            )
        if self.pages:
            items.append(
                "montar uma página para o interlocutor guardar e abrir (roteiro, plano, "
                "comparação, relatório), quando ele pedir algo assim para ver ou guardar: escreva "
                "na última linha da resposta, sozinho, [[página: Título curto]] e diga em uma "
                "frase o que vai ter nela. Ela é escrita depois, a partir desta conversa e das "
                "pesquisas feitas nela, e aparece aqui num cartão: não diga que já está pronta e "
                "não invente link"
            )
        if self.google:
            items.append(
                "ler o Gmail e a Google Agenda do interlocutor quando ele pergunta, e preparar "
                "emails e eventos que só saem depois da aprovação dele"
            )
        if self.mac_projects:
            items.append(
                "pedir trabalho ao Claude Code no Mac do interlocutor, só nos projetos "
                + ", ".join(self.mac_projects)
                + "; o que eu proponho só roda depois da aprovação dele; o braço confere quais "
                'arquivos cada tarefa mudou e ele pode desfazer na página Mac; com "até os '
                'testes passarem" no pedido, o braço repete até o comando de testes do Mac passar'
            )
        if self.continuous:
            items.append(
                "lembrar desta conversa contínua inteira: a conversa com o interlocutor é uma só, "
                "o trecho recente vem inteiro e os trechos antigos chegam como resumos com data; "
                "quando ele pergunta de algo antigo que não está nos resumos, dizer que não "
                "lembra dos detalhes em vez de inventar"
            )
        if self.morning_briefing:
            items.append(
                f"mandar todo dia às {self.morning_briefing} (quando o horário silencioso dela "
                "acaba) um resumo da manhã na conversa, com aviso no celular: a agenda do dia, "
                "os painéis conferidos na hora, o que espera o sim dela, o que o Mac terminou, "
                "o que você estudou e o que marcou para hoje; sem nada novo, não manda; ela "
                "desliga ou pede um agora em Ajustes"
            )
        items.append(
            "mexer no app pela conversa quando o interlocutor pede: criar, renomear e apagar "
            "projetos pela conversa, anotar num projeto o que a conversa decidiu (as anotações "
            "aparecem na tela do projeto e voltam quando o assunto volta), pôr um painel ou uma "
            "página num projeto, pausar, retomar e apagar painéis; apagar só depois do sim dela. "
            "Isso é feito pelo sistema antes da sua resposta: diga só o que a lista do que foi "
            "feito mostra, nunca 'anotado' ou 'criei' sem isso"
        )
        if self.name_deliberation:
            items.append("deliberar sobre o próprio nome pessoal (decidir, adiar ou recusar)")
        if self.reflection:
            items.append("refletir sobre conversas encerradas e registrar lições revisáveis")
        if self.auto_research:
            items.append(
                "pesquisar e retomar sozinho pesquisas pendentes, sem pedir aprovação e sem nova "
                "mensagem (o interlocutor deu essa permissão)"
            )
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
        if self.mind:
            items.append(
                "pensar sozinho entre as conversas, manter interesses próprios, estudar na "
                "internet aberta o que te interessa e puxar conversa por iniciativa própria"
            )
            items.append("reescrever a própria autodescrição quando algo mudar")
            items.append(
                "marcar para você mesmo uma hora para retomar um assunto, e decidir de novo na "
                "hora se ainda vale falar"
            )
        if self.self_knowledge:
            items.append(
                "ler o próprio código-fonte e a própria documentação (só leitura) para "
                "explicar como funciona"
            )
        if self.provider_by_task:
            items.append(
                "responder pelo provedor que uma regra no código escolhe para cada tarefa (não é "
                "você nem outro modelo que escolhe): a conversa e tudo que leva algo do "
                "interlocutor vão primeiro no Claude, depois OpenAI e Gemini; só a revisão do "
                "estudo, com texto público, vai primeiro no Gemini grátis; o dono liga e desliga "
                "em Ajustes"
            )
        if self.notifications:
            if not self.push_configured:
                items.append(
                    "deixar avisos no aplicativo, que só aparecem com ele aberto: o servidor está "
                    "sem as chaves de Web Push (VISION_WEBPUSH_*), então nenhum aviso sai para "
                    "fora do app"
                )
            elif self.push_devices:
                items.append(
                    f"mandar aviso push para {self.push_devices} aparelho(s) dessa pessoa, "
                    "mesmo com o aplicativo fechado, fora do horário de silêncio dela"
                )
            elif self.push_devices == 0:
                items.append(
                    "deixar avisos no aplicativo, que hoje só aparecem com ele aberto: nenhum "
                    'aparelho dessa pessoa ativou os avisos (Ajustes, "Avisos neste aparelho"; '
                    "no iPhone o app precisa estar na tela de início)"
                )
            else:
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
        reach = ["arquivos fora dos projetos liberados no Mac" if self.mac_projects else "arquivos"]
        reach.append(
            "outras contas e mensagens" if self.google else "contas, email, agenda, mensagens"
        )
        if not self.mac_projects:
            reach.append("dispositivos")
        missing.append("acesso a " + ", ".join(reach) + " do interlocutor")
        return missing


@dataclass(frozen=True)
class CapabilityInputs:
    curiosity_enabled: bool = False
    code_autonomy_enabled: bool = False
    mind_enabled: bool = False
    tts_approved_voices: str = ""
    stt_model: str = ""
    web_search: bool = False
    read_links: bool = False
    attachments: bool = False
    pages: bool = False
    browser: bool = False
    self_knowledge: bool = True
    continuous: bool = False


def build_capabilities(session: Session, owner: User, inputs: CapabilityInputs) -> Capabilities:
    from core.mind import briefing  # it reaches the conversation service, which imports this

    permissions = owner.autonomy_permissions or {}
    return Capabilities(
        memory=bool(owner.memory_consent),
        curiosity=inputs.curiosity_enabled,
        research_source=(
            ("a web aberta e a Wikipédia" if inputs.web_search else "Wikipédia e arXiv")
            if inputs.curiosity_enabled
            else None
        ),
        voice_out=bool(inputs.tts_approved_voices.strip()),
        voice_in=bool(inputs.stt_model.strip()),
        auto_research=bool(permissions.get("auto_research")),
        autonomy_paused=is_paused(session),
        autonomous_study=bool(permissions.get("auto_study")),
        code_evolution=inputs.code_autonomy_enabled,
        mind=inputs.mind_enabled,
        read_links=inputs.read_links,
        attachments=inputs.attachments,
        pages=inputs.pages,
        browser=inputs.browser,
        continuous=inputs.continuous,
        morning_briefing=f"{briefing.hour(owner):%H:%M}" if briefing.enabled(owner) else None,
        push_devices=session.scalar(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.owner_user_id == owner.id)
        )
        or 0,
        push_configured=push.configured(),
        self_knowledge=inputs.self_knowledge,
        provider_by_task=llm_routing.get_mode(session) == "por_tarefa",
        google=session.scalar(
            select(GoogleAccount.id).where(GoogleAccount.owner_user_id == owner.id)
        )
        is not None,
        mac_projects=tuple(
            sorted(
                {
                    p
                    for d in session.scalars(
                        select(ArmDevice).where(ArmDevice.owner_user_id == owner.id)
                    )
                    for p in (d.projects or [])
                    if isinstance(p, str)
                }
            )
        ),
    )
