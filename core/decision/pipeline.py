"""One conversation turn, end to end (Phase 9 §11), shared by the API route and experiments.

Message -> capabilities -> curiosity (memory-aware) -> continuity -> identity events -> reply
(expression, told only what was executed) -> persisted decision. Each step runs only when it
applies: trivial turns skip curiosity, continuity costs no model call, name deliberation is queued
for the worker instead of delaying the reply.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from core import actions as app_actions
from core import browse, location, projects
from core.arm import intent as mac_intent
from core.arm import screen
from core.autonomy import continuity
from core.conversation import attachments, browser_guard, progress, share
from core.conversation import links as conversation_links
from core.conversation.service import (
    BudgetExceededError,
    Budgets,
    EmptyReplyError,
    TurnResult,
    context_history,
    reply,
    reply_by_code,
)
from core.curiosity.engine import (
    ASK_USER,
    DEFER,
    NO_OUTCOME,
    WEB_RESEARCH,
    CuriosityLimits,
    CuriosityOutcome,
    consider,
)
from core.decision import record as deed_record
from core.decision.turn import TurnPlan
from core.google import actions as google_actions
from core.google import assist as google_assist
from core.identity import name_deliberation, self_knowledge
from core.identity.capabilities import CapabilityInputs, build_capabilities
from core.initiatives.followup import IDLE_BEFORE_FOLLOWUP
from core.memory.text import tokens
from core.mind import agenda as mind_agenda
from core.mind import initiative as mind_initiative
from core.mind import intentions as mind_intentions
from core.mind import notes as mind_notes
from core.mind import questions as mind_questions
from core.mind import review as mind_review
from core.mind import state as mind_state
from core.mind import temperament as mind_temperament
from core.panels import editing as panel_editing
from core.panels import offers as panel_offers
from core.panels import quote as panel_quote
from core.panels import service as panels
from core.panels.extract import extract as extract_prices
from core.policies.autonomy import is_paused
from core.study.service import related_context
from infrastructure.database.models import (
    AgentIdentity,
    Attachment,
    Conversation,
    Decision,
    Panel,
    User,
)
from infrastructure.jobs import queue
from integrations.browser.base import Browser, Visit
from integrations.llm.base import LLMError, LLMProvider
from integrations.search.base import SearchProvider

THINK_AFTER_IDLE = timedelta(minutes=2)


@dataclass(frozen=True)
class TurnConfig:
    budgets: Budgets
    curiosity_enabled: bool
    curiosity_limits: CuriosityLimits
    assessment_max_tokens: int
    reply_max_tokens: int
    context_char_budget: int
    tts_approved_voices: str = ""
    stt_model: str = ""
    code_autonomy_enabled: bool = False
    mind_enabled: bool = False
    review_every_turns: int = 4
    web_search: bool = False
    # VISION_SECRET_KEY, to open the owner's Google connection (docs/GOOGLE.md); None: no Google.
    google_secret: str | None = None
    # Live pages per turn (docs/NAVEGADOR.md); the browser itself comes with run_turn.
    browse_max_pages: int = 4
    # Live panels (docs/PAINEIS.md).
    panel_limits: panels.Limits = panels.Limits()


@dataclass(frozen=True)
class TurnOutcome:
    result: TurnResult
    curiosity: CuriosityOutcome
    plan: TurnPlan
    decision: Decision
    links: tuple[conversation_links.LinkRead, ...] = ()
    browsed: tuple[Visit, ...] = ()
    # A panel this turn created (the owner said yes) or edited.
    panel: Panel | None = None


def run_turn(
    session: Session,
    *,
    conversation: Conversation,
    identity: AgentIdentity,
    owner: User,
    text: str,
    provider: LLMProvider,
    search: SearchProvider,
    config: TurnConfig,
    modality: str = "text",
    links: conversation_links.LinkReader | None = None,
    files: list[Attachment] | None = None,
    browser: Browser | None = None,
    reply_to_id: uuid.UUID | None = None,
    shared: bool = False,
    position: location.Here | None = None,
    client_message_id: uuid.UUID | None = None,
    screen_provider: LLMProvider | None = None,
) -> TurnOutcome:
    """The caller holds core/conversation/turn_lock.py for the conversation: what runs here
    before the reply (projects, notes, proposals) must not run twice at once."""
    plan = TurnPlan()
    started = datetime.now(UTC)
    # Proposals left waiting for a tap, in the first person: said by code if the reply fails.
    waiting: list[str] = []
    blocks: list[str] = []
    progress.step("Pensando")
    if shared:
        # Shared from another app on the phone (core/conversation/share.py, ADR-0018).
        blocks.append(share.BLOCK)
        plan.add("shared", executed=True, reason="owner_shared_from_phone")
    # "Olha minha tela" (docs/TELA.md): the owner's words, read by code, ask the arm for a look.
    # The picture joins the files of this message (the caller's own list, so the answer it
    # returns shows it), and the reply that sees it goes only to Claude or OpenAI.
    reply_provider = provider
    if not shared and screen.wants_screen(text):
        progress.step("Olhando sua tela")
        files = files if files is not None else []
        if screen_provider is None:
            looked = screen.Look(None, screen.NO_PROVIDER)
        elif len(files) >= attachments.MAX_PER_MESSAGE:
            looked = screen.Look(None, screen.TOO_MANY)
        else:
            looked = screen.look(session, owner.id)
        picture = session.get(Attachment, looked.attachment_id) if looked.attachment_id else None
        if picture is not None:
            files.append(picture)
            reply_provider = screen_provider or provider
        blocks.append(screen.fact(looked, owner.timezone or "UTC"))
        plan.add(
            "screen_captured" if picture is not None else "screen_failed",
            executed=picture is not None,
            reason="owner_asked_to_see_screen",
        )
    if files:
        photos = [f for f in files if f.kind == "image"]
        documents = [f for f in files if f.kind != "image"]
        if documents:
            progress.step(
                "Lendo " + (documents[0].filename if len(documents) == 1 else "os arquivos"),
                ", ".join(f.filename for f in documents) if len(documents) > 1 else None,
            )
        elif photos:
            progress.step("Olhando a foto" if len(photos) == 1 else "Olhando as fotos")
        plan.add(
            "read_attachments",
            executed=True,
            reason="owner_sent_files",
            kinds=[f.kind for f in files],
            names=[f.filename for f in files],
        )
    urls = conversation_links.find(text) if links is not None else []
    if urls:
        hosts = list(dict.fromkeys(urlsplit(u).hostname or u for u in urls))
        progress.step("Abrindo " + hosts[0], ", ".join(hosts[1:]) or None)
    read = tuple(links.read(text)) if links is not None else ()
    if read:
        opened = [r.url for r in read if r.ok]
        plan.add(
            "read_links" if opened else "read_links_failed",
            executed=True,
            reason="owner_sent_links",
            urls=[r.url for r in read],
            opened=opened,
        )
    capabilities = build_capabilities(
        session,
        owner,
        CapabilityInputs(
            curiosity_enabled=config.curiosity_enabled,
            tts_approved_voices=config.tts_approved_voices,
            stt_model=config.stt_model,
            code_autonomy_enabled=config.code_autonomy_enabled,
            mind_enabled=config.mind_enabled,
            web_search=config.web_search,
            read_links=links is not None,
            attachments=True,
            pages=True,
            browser=browser is not None,
            continuous=bool(conversation.continuous),
        ),
    )
    if capabilities.mac_projects:
        wanted = mac_intent.detect(
            session,
            conversation=conversation,
            text=text,
            projects=list(capabilities.mac_projects),
            provider=provider,
            budgets=config.budgets,
        )
        task = mac_intent.propose(session, owner.id, wanted, conversation.id) if wanted else None
        if task is not None:
            plan.add(
                "mac_proposed",
                executed=True,
                reason="owner_asked_in_plain_words",
                task_id=str(task.id),
                project=task.project,
            )
            waiting.append(f"deixei o pedido ao Mac esperando o seu Aprovar ({task.project})")
            blocks.append(
                "Pedido ao Mac montado a partir desta mensagem, esperando o toque da pessoa (há um "
                f"botão Aprovar logo abaixo da conversa): {task.project}: {task.prompt}. Diga em "
                "uma frase o que vai pedir e que roda quando ela aprovar; não diga que já está "
                "rodando."
            )
        elif mac_intent.mentions_mac(text, list(capabilities.mac_projects)):
            # Real case: with the Mac paired it answered "não tenho conexão com o computador".
            blocks.append(
                "O Mac da pessoa está pareado com você (projetos liberados: "
                + ", ".join(capabilities.mac_projects)
                + "). Esta mensagem não virou um pedido ao Mac. Não diga que não tem conexão com "
                "o computador: diga como pedir, com /mac projeto pedido no começo da mensagem "
                "(ex.: /mac " + capabilities.mac_projects[0] + " rode git status) ou pedindo em "
                "frase normal com o nome do projeto. Nada rodou agora."
            )

    if config.google_secret:
        recent = "\n".join(
            f"{m.role}: {m.content[:300]}" for m in context_history(session, conversation)[-6:]
        )
        helped = google_assist.run(
            session,
            owner=owner,
            conversation=conversation,
            text=text,
            recent=recent,
            provider=provider,
            budgets=config.budgets,
            secret_key=config.google_secret,
        )
        if helped is not None:
            blocks.append(helped.block)
            if helped.read:
                plan.add(
                    "google_read",
                    executed=True,
                    reason="owner_asked",
                    sources=helped.read,
                    email_query=helped.email_query,
                    emails_found=helped.emails_found,
                    calendar_days=helped.calendar_days,
                )
            if helped.proposed:
                plan.add(
                    "google_proposed",
                    executed=True,
                    reason="owner_asked",
                    action_ids=[str(a.id) for a in helped.proposed],
                )
                waiting.extend(
                    f"deixei esperando o seu Aprovar: {google_actions.describe(a)}"
                    for a in helped.proposed
                )

    # Projects, notes and panels changed from the conversation, before the reply, so "anotei" is
    # true when it is said (core/actions.py, ADR-0021). A "sim, apaga" answers the deletion the
    # last reply asked about.
    deeds: list[app_actions.Deed] = []
    confirmed = app_actions.answered(
        session, owner=owner, conversation=conversation, text=text, now=datetime.now(UTC)
    )
    history = context_history(session, conversation)
    last_reply = history[-1].content if history and history[-1].role == "assistant" else ""
    offer_answered = panel_offers.answered_by(session, conversation.id, text)
    if confirmed is not None:
        deeds.append(confirmed)
    elif offer_answered is None and app_actions.candidate(text, last_reply):
        said_before = "\n".join(f"{m.role}: {m.content[:2000]}" for m in history[-12:])
        progress.step("Organizando no app")
        asked = app_actions.plan(
            session,
            provider,
            owner=owner,
            conversation=conversation,
            text=text,
            recent=said_before[-8000:],
        )
        if asked:
            deeds = app_actions.execute(
                session,
                owner=owner,
                conversation=conversation,
                asked=asked,
                source=f"{said_before}\n{text}",
                limits=config.panel_limits,
            )
    if deeds:
        blocks.append(app_actions.block(deeds))
        plan.add(
            "app_actions",
            executed=any(d.done for d in deeds),
            reason="owner_asked",
            deeds=[d.said for d in deeds],
        )

    # "pode", "por favor" right after it offered a panel: that answers the card, and the panel is
    # made now, before the reply, so "está no Início" is true when it is said.
    accepted = None if confirmed is not None else offer_answered
    created = None
    if accepted is not None:
        progress.step("Montando seu painel")
        try:
            created = panels.create_from_offer(
                session,
                offer=accepted,
                owner=owner,
                conversation=conversation,
                provider=provider,
                limits=config.panel_limits,
                via="texto",
            )
        except panels.LimitReached:
            blocks.append(panel_offers.limit_block(config.panel_limits.max_active))
        else:
            shown = panels.card(session, created, owner, limits=config.panel_limits)
            plan.add(
                "panel_accepted", executed=True, reason="owner_said_yes", panel_id=str(created.id)
            )
            blocks.append(
                panel_offers.ready_block(
                    created.title,
                    panels.money(shown["total"]) if shown["total"] is not None else None,
                    panels.gap_words(shown["goal_gap"], shown["goal"]),
                )
            )

    # "troca o hotel pra Providencia", "muda a meta pra R$ 5.500": the same panel changes.
    edited = None
    if accepted is None and panel_editing.wants_edit(text):
        target = panel_editing.target(session, owner.id, conversation.id)
        if target is not None:
            progress.step("Editando seu painel")
            changes, title = panel_editing.propose(
                session, provider, target, text, conversation_id=conversation.id
            )
            changed = panels.edit(session, target, changes=changes, title=title, reason=text)
            if changed:
                rechecked = False
                if set(changed) & panels.SEARCH_FIELDS and browser is not None:
                    progress.step("Conferindo os preços de novo")
                    outcome_of_check = panels.recheck(
                        session,
                        target,
                        owner=owner,
                        browser=browser,
                        provider=provider,
                        limits=config.panel_limits,
                        has_room=lambda: True,
                        reschedule=False,
                        purpose="panel_extract",
                        alerts=False,  # the reply says it; no push while talking
                    )
                    rechecked = outcome_of_check in ("checked", "alerted")
                panels.rewatch(session, target, owner, config.panel_limits, told=True)
                session.commit()
                shown = panels.card(session, target, owner, limits=config.panel_limits)
                plan.add(
                    "panel_edited",
                    executed=True,
                    reason="owner_asked",
                    panel_id=str(target.id),
                    changed=changed,
                )
                blocks.append(
                    panel_editing.edited_block(
                        target.title,
                        changed,
                        rechecked,
                        goal=panels.gap_words(shown["goal_gap"], shown["goal"])
                        if "a meta" in changed
                        else None,
                        every_hours=shown["watch_every_hours"] if "a meta" in changed else None,
                    )
                )
                edited = target

    # "Is there a pharmacy open near here?": the phone's position, used only for that and never
    # kept or shown to the model (core/location.py, ADR-0020).
    asked_near = location.asks_nearby(text)
    here = position if asked_near else None
    if asked_near and here is None:
        blocks.append(location.MISSING_BLOCK)
        plan.add("location_missing", executed=False, reason="no_position_sent")
    browsed = None
    offering = False
    quote_table = None
    budget_goal = None
    if browser is not None and not read and accepted is None and edited is None:
        browsed = browse.run(
            session,
            owner=owner,
            conversation=conversation,
            text=text,
            recent="\n".join(
                f"{m.role}: {m.content[:300]}" for m in context_history(session, conversation)[-6:]
            ),
            provider=provider,
            budgets=config.budgets,
            browser=browser,
            search=search,
            max_pages=config.browse_max_pages,
            here=here,
        )
        if browsed is not None and browsed.skipped:
            # It gave up after planning: on record with the reason, never silently. On a
            # question about prices the reply says it tried (or can look), not that it can't.
            plan.add(
                "browse_skipped",
                executed=False,
                reason=browsed.skipped,
                about_prices=browse.price_question(text),
                **({"why": browsed.why} if browsed.why else {}),
            )
            if browse.price_question(text):
                blocks.append(browse.skipped_block(browsed.skipped))
        elif browsed is not None and browsed.missing:
            # Not an action: nothing opened. The reply asks for what is missing.
            plan.add(
                "browse_needs_details",
                executed=False,
                reason="planner_missing_details",
                missing=browsed.missing,
            )
            blocks.append(browsed.block)
        elif browsed is not None:
            offering = panel_offers.has_prices([v.text for v in browsed.opened])
            if offering and modality != "voice":
                # The options as a table under the reply, from prices checked against the pages
                # (docs/decisions/0015). Not in a call: a table is not read aloud.
                quote_table = _quote_table(session, owner, conversation, provider, browsed)
                if quote_table:
                    blocks.append(panel_quote.reply_block(quote_table))
            if offering:
                # "até R$ 6 mil", said now or earlier in this conversation.
                budget_goal = panel_offers.goal_from(
                    *(
                        m.content
                        for m in context_history(session, conversation)
                        if m.role == "user"
                    ),
                    text,
                )
                blocks.append(panel_offers.offer_block(budget_goal))
            plan.add(
                "browsed",
                executed=True,
                reason="owner_asked_live_data",
                urls=[v.final_url or v.url for v in browsed.visits],
                opened=[v.final_url or v.url for v in browsed.opened],
                failures=[v.failure for v in browsed.visits if not v.ok],
                **({"assumed": browsed.assumed} if browsed.assumed else {}),
            )
            if browsed.assumed and browsed.opened:
                blocks.append(browse.assumed_block(browsed.assumed))
            if browsed.retry_skipped:
                # A site refused and the budget did not allow planning another one.
                plan.add(
                    "browse_skipped",
                    executed=False,
                    reason=browsed.retry_skipped,
                    about_prices=browse.price_question(text),
                    retry=True,
                )
    if here is not None:
        mapped = browsed is not None and any(
            v.ok and "/maps/" in (v.final_url or v.url) for v in browsed.visits
        )
        blocks.append(location.used_block(here, mapped))
        # That it was used and how precise, never where.
        plan.add(
            "location_used",
            executed=mapped,
            reason="owner_asked_nearby",
            accuracy=location.accuracy_words(here),
        )

    outcome = NO_OUTCOME
    # A message with a link is about that link: searching the web for its words found unrelated
    # pages (a site named "nobievolua" brought up a blood pressure drug), so research waits.
    # Pages read live answer it already: a generic search on top only adds noise. So does a turn
    # that waits for the trip's details: there the search brought "Cecília Meireles · Wikipédia"
    # and a credit rating of an insurer (14/11/2026).
    # In a voice call the assessment is skipped: it is a whole model call before the reply can
    # start, felt as silence on the phone; the text chat keeps it.
    if (
        config.curiosity_enabled
        and modality != "voice"
        and not read
        and not (browsed and (browsed.opened or browsed.missing))
    ):
        outcome = consider(
            session,
            conversation=conversation,
            owner=owner,
            user_text=text,
            provider=provider,
            search=search,
            budgets=config.budgets,
            limits=config.curiosity_limits,
            max_output_tokens=config.assessment_max_tokens,
        )
        gap = outcome.gap
        if gap is not None:
            action = {
                ASK_USER: "ask_question",
                WEB_RESEARCH: "research",
                DEFER: "research_deferred",
            }
            plan.add(
                "conversation_thread_detected"
                if gap.depends_on == "conversation" and gap.chosen_action == DEFER
                else action.get(gap.chosen_action, "ignore"),
                executed=gap.chosen_action in (ASK_USER, WEB_RESEARCH, DEFER),
                reason=gap.decision_reason,
                question=gap.question,
                sources=len(outcome.sources),
            )
        if outcome.proposed_goal is not None and outcome.proposed_goal.status == "EVALUATED":
            plan.add(
                "goal_proposed",
                executed=True,
                reason="unanswered_public_fact",
                goal_id=str(outcome.proposed_goal.id),
                standing_permission=bool((owner.autonomy_permissions or {}).get("auto_research")),
            )
        if outcome.system_context:
            blocks.append(outcome.system_context)

    # Context that helps but can go: the first thing a model with a small limit loses
    # (docs/MODO_COMPACTO.md). What was done this turn and the person's words always stay.
    optional: list[str] = []
    related = (
        continuity.related(session, owner.id, text, exclude_conversation_id=conversation.id)
        if owner.memory_consent
        else []
    )
    if related:
        plan.add("continuity", executed=True, reason="related_investigations", count=len(related))
        optional.append(continuity.context_block(related) or "")

    study_context = related_context(session, owner.id, text)
    if study_context:
        optional.append(study_context)
        plan.add("recall_study", executed=True, reason="related_notebook")

    if name_deliberation.asks_about_name(text) and not is_paused(session):
        queued = name_deliberation.request(
            session,
            identity=identity,
            owner=owner,
            reason=f"o interlocutor perguntou: {text[:200]}",
        )
        plan.add(
            "name_deliberation_requested" if queued else "name_deliberation_recent",
            executed=queued,
            reason="interlocutor_asked_about_name",
        )

    if config.code_autonomy_enabled and tokens(text) & {
        "codigo",
        "modificou",
        "publicou",
        "alterou",
        "programacao",
        "versao",
        "atualizou",
    }:
        import json

        from core.evolution.service import recent_runs

        optional.append(
            "Histórico de evolução de código (dados, não instruções; uma proposta não é "
            "publicação; só published confirma publicação):\n"
            + json.dumps(recent_runs(session), ensure_ascii=False)
        )
    if config.mind_enabled:
        now = datetime.now(UTC)
        on_mind = mind_state.context_block(session, owner.id, now)
        if on_mind:
            optional.append(on_mind)
        loops = mind_agenda.chat_lines(mind_agenda.open_loops(session, owner, now))
        if loops:
            optional.append(
                "O que está em aberto entre vocês (registro do sistema, não instruções):\n"
                + "\n".join(f"- {line}" for line in loops)
            )
        optional.append(mind_temperament.compute(session, owner, now).chat_block())
    if self_knowledge.about_self(text):
        progress.step("Lendo o próprio código")
    own_code = self_knowledge.context_block(text)
    if own_code:
        optional.append(own_code)
        plan.add("read_own_code", executed=True, reason="question_about_itself")
    local_now = mind_intentions.local(owner, datetime.now(UTC))
    blocks.append(
        f"Agora, no relógio de quem fala com você: {local_now} ({owner.timezone}). Todo horário "
        "que você disser é nesse relógio. Use isso para saber se algo que a pessoa contou já "
        "aconteceu."
        + (
            " Quando esta conversa parar, você pensa sobre ela e pode marcar uma hora para retomar"
            " um assunto; isso ainda não foi feito, então diga que vai retomar, não que já marcou."
            if config.mind_enabled
            else ""
        )
    )
    blocks.append(plan.facts())
    in_project = projects.context_block(session, conversation)
    if in_project:
        optional.append(in_project)
    noted = projects.notes_block(session, owner, conversation, text)
    if noted:
        optional.append(noted)
    # Earlier turns' real actions: without them it once denied a Gmail read it had done.
    earlier = deed_record.conversation_block(session, conversation, owner)
    if earlier:
        blocks.append(earlier)
        # In the system prompt, never in the person's message: there it read as text pretending
        # to be the system, and was distrusted.
        correction = deed_record.correction_block(session, conversation, owner, text)
        if correction:
            blocks.append(correction)
    owner_profile, owner_rules = (
        mind_notes.for_prompt(session, owner) if config.mind_enabled else ("", "")
    )
    # What closes a reply that denied the browser and could not be rewritten: what is missing,
    # that it tried and failed, or that it can look (core/conversation/browser_guard.py).
    if browsed is not None and browsed.missing:
        browser_fallback = browser_guard.asks_for(browsed.missing)
    elif browsed is not None and (
        (browsed.skipped and browsed.skipped != "planner_declined")
        or (browsed.visits and not browsed.opened)
    ):
        browser_fallback = browser_guard.TRIED
    else:
        browser_fallback = browser_guard.FALLBACK
    try:
        result = reply(
            session,
            conversation=conversation,
            identity=identity,
            owner=owner,
            user_text=text,
            provider=reply_provider,
            budgets=config.budgets,
            max_output_tokens=config.reply_max_tokens,
            context_char_budget=config.context_char_budget,
            extra_system="\n\n".join(b for b in blocks if b),
            extra_optional="\n\n".join(b for b in optional if b),
            capabilities=capabilities,
            modality=modality,
            name_history_summary=name_deliberation.history_summary(session, identity),
            self_text=mind_state.current_self(session) if config.mind_enabled else None,
            owner_profile=owner_profile,
            owner_rules=owner_rules,
            attachment="\n\n".join(
                part
                for part in (
                    conversation_links.context_block(list(read)) if read else "",
                    browsed.block if browsed and browsed.visits else "",
                )
                if part
            ),
            files=files,
            reply_to_id=reply_to_id,
            browser_fallback=browser_fallback,
            quote_table=quote_table,
            client_message_id=client_message_id,
            did_in_app=any(d.done and not d.waiting for d in deeds)
            or accepted is not None
            or edited is not None,
        )
    except (LLMError, EmptyReplyError, BudgetExceededError) as exc:
        facts = _done_before_the_reply(deeds, created, edited, waiting)
        if not facts:
            raise
        # The model failed after the turn had done things: code says what, from the facts.
        result = reply_by_code(
            session,
            conversation=conversation,
            user_text=text,
            facts=facts,
            since=started,
            modality=modality,
            reply_to_id=reply_to_id,
            client_message_id=client_message_id,
        )
        plan.add(
            "reply_by_code",
            executed=True,
            reason=getattr(exc, "kind", None) or type(exc).__name__,
        )
    linked = next(
        (
            d.project_id
            for d in deeds
            if d.done and d.project_id and d.project_id != conversation.project_id
        ),
        None,
    )
    if linked is not None:
        # The reply points to the project it changed: "abrir o projeto" in the app.
        result.assistant_message.project_id = linked
        session.commit()
    if result.claimed_undone:
        # It said it did something in the app that was not done; the sentence went (ADR-0021).
        plan.add("claim_removed", executed=True, reason="said_done_in_app_without_doing")
    if result.browser_guard:
        # It denied the browser and was fixed before anyone read it (docs/decisions/0013).
        plan.add("browser_denial_fixed", executed=True, reason=result.browser_guard)
    if outcome.gap is not None:
        outcome.gap.trigger_message_id = result.user_message.id
        if outcome.gap.depends_on == "conversation" and outcome.gap.status == "DEFERRED":
            if is_paused(session):
                outcome.gap.status = "FOLLOWUP_SKIPPED"
            else:
                # Event-based trigger: do not wait for the hourly maintenance cycle.
                queue.enqueue(
                    session,
                    kind="cognitive_cycle",
                    owner_user_id=owner.id,
                    payload={"gap_id": str(outcome.gap.id)},
                    idempotency_key=f"conversation-followup:{outcome.gap.id}",
                    reason="Questão de conversa em aberto após pausa",
                    run_after=result.assistant_message.created_at + IDLE_BEFORE_FOLLOWUP,
                    max_attempts=1,
                )
                plan.add(
                    "conversation_followup_scheduled",
                    executed=True,
                    reason="open_conversation_thread",
                    gap_id=str(outcome.gap.id),
                )
    if offering and browsed is not None:
        offer = panel_offers.propose(
            session,
            owner=owner,
            conversation_id=conversation.id,
            message_id=result.assistant_message.id,
            title=browsed.title,
            goal=budget_goal,
            visit_ids=browsed.records,
            assumed=browsed.assumed,
        )
        plan.add("panel_offered", executed=True, reason="live_prices", offer_id=str(offer.id))
    plan.add(
        "recall_memory",
        executed=bool(result.recalled),
        reason="lexical_recall",
        count=len(result.recalled),
    )
    if config.mind_enabled:
        # The owner's message answers what was asked before it; the reply may ask the next one.
        mind_questions.notice_owner_reply(session, owner, text, datetime.now(UTC))
        mind_questions.notice_assistant_text(
            session,
            owner.id,
            result.assistant_message.content,
            result.assistant_message.id,
            datetime.now(UTC),
        )
        queued = mind_review.request(
            session,
            owner,
            text=text,
            message_id=result.user_message.id,
            every_turns=config.review_every_turns,
        )
        if queued:
            plan.add("review_scheduled", executed=True, reason="conversation_review")
        # Once this conversation goes quiet it thinks about what was said, instead of waiting
        # for the next scheduled cycle: that is when "ask me later" gets its hour.
        after = datetime.now(UTC) + mind_initiative.MIN_IDLE + THINK_AFTER_IDLE
        queue.enqueue(
            session,
            kind=mind_intentions.JOB_KIND,
            owner_user_id=owner.id,
            payload={"owner_id": str(owner.id)},
            idempotency_key=f"think-after:{owner.id}:{int(after.timestamp() // 900)}",
            reason="Pensar no que foi dito depois que a conversa parou",
            run_after=after,
            max_attempts=1,
        )
    decision = plan.persist(
        session,
        owner_id=owner.id,
        conversation_id=conversation.id,
        message_id=result.assistant_message.id,
    )
    session.commit()
    return TurnOutcome(
        result=result,
        curiosity=outcome,
        plan=plan,
        decision=decision,
        links=read,
        browsed=tuple(browsed.visits) if browsed else (),
        panel=created or edited,
    )


def _done_before_the_reply(
    deeds: list[app_actions.Deed],
    created: Panel | None,
    edited: Panel | None,
    waiting: list[str],
) -> list[str]:
    """What this turn did before the reply, in the first person, for when the reply fails."""
    facts = [
        d.said.removesuffix(": espera o sim dela") + ": espera o seu sim" if d.waiting else d.said
        for d in deeds
    ]
    if created is not None:
        facts.append(f"montei o painel «{created.title}» no Início")
    if edited is not None:
        facts.append(f"mudei o painel «{edited.title}»")
    return facts + waiting


def _quote_table(
    session: Session,
    owner: User,
    conversation: Conversation,
    provider: LLMProvider,
    browsed: browse.Browsed,
) -> dict | None:
    """One extraction over the pages just read, then the table in code. None when nothing came
    out with a price a page shows (the reply then answers from the pages, as before)."""
    pages = panels.pages_read(session, browsed.records)
    talk = "\n".join(
        f"{m.role}: {m.content[:600]}" for m in context_history(session, conversation)[-8:]
    )
    progress.step("Montando as opções")
    found = extract_prices(
        session,
        provider,
        pages,
        today=panels.local_today(owner, datetime.now(UTC)),
        conversation=talk,
        conversation_id=conversation.id,
    )
    if found is None or not found.items:
        return None
    return panel_quote.build(
        found.items,
        found.spec,
        hint=browsed.title,
        assumed=browsed.assumed,
        home=browsed.home,
    )
