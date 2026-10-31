"""One conversation turn, end to end (Phase 9 §11), shared by the API route and experiments.

Message -> capabilities -> curiosity (memory-aware) -> continuity -> identity events -> reply
(expression, told only what was executed) -> persisted decision. Each step runs only when it
applies: trivial turns skip curiosity, continuity costs no model call, name deliberation is queued
for the worker instead of delaying the reply.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.autonomy import continuity
from core.conversation.service import Budgets, TurnResult, reply
from core.curiosity.engine import (
    ASK_USER,
    DEFER,
    NO_OUTCOME,
    WEB_RESEARCH,
    CuriosityLimits,
    CuriosityOutcome,
    consider,
)
from core.decision.turn import TurnPlan
from core.identity import name_deliberation
from core.identity.capabilities import CapabilityInputs, build_capabilities
from core.initiatives.followup import IDLE_BEFORE_FOLLOWUP
from core.policies.autonomy import is_paused
from core.study.service import related_context
from infrastructure.database.models import AgentIdentity, Conversation, Decision, User
from infrastructure.jobs import queue
from integrations.llm.base import LLMProvider
from integrations.search.base import SearchProvider


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


@dataclass(frozen=True)
class TurnOutcome:
    result: TurnResult
    curiosity: CuriosityOutcome
    plan: TurnPlan
    decision: Decision


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
) -> TurnOutcome:
    plan = TurnPlan()
    blocks: list[str] = []
    capabilities = build_capabilities(
        session,
        owner,
        CapabilityInputs(
            curiosity_enabled=config.curiosity_enabled,
            tts_approved_voices=config.tts_approved_voices,
            stt_model=config.stt_model,
        ),
    )

    outcome = NO_OUTCOME
    if config.curiosity_enabled:
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
            )
        if outcome.system_context:
            blocks.append(outcome.system_context)

    related = (
        continuity.related(session, owner.id, text, exclude_conversation_id=conversation.id)
        if owner.memory_consent
        else []
    )
    if related:
        plan.add("continuity", executed=True, reason="related_investigations", count=len(related))
        blocks.append(continuity.context_block(related) or "")

    study_context = related_context(session, owner.id, text)
    if study_context:
        blocks.append(study_context)
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

    blocks.append(plan.facts())
    result = reply(
        session,
        conversation=conversation,
        identity=identity,
        owner=owner,
        user_text=text,
        provider=provider,
        budgets=config.budgets,
        max_output_tokens=config.reply_max_tokens,
        context_char_budget=config.context_char_budget,
        extra_system="\n\n".join(b for b in blocks if b),
        capabilities=capabilities,
        modality=modality,
        name_history_summary=name_deliberation.history_summary(session, identity),
    )
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
    plan.add(
        "recall_memory",
        executed=bool(result.recalled),
        reason="lexical_recall",
        count=len(result.recalled),
    )
    decision = plan.persist(
        session,
        owner_id=owner.id,
        conversation_id=conversation.id,
        message_id=result.assistant_message.id,
    )
    session.commit()
    return TurnOutcome(result=result, curiosity=outcome, plan=plan, decision=decision)
