"""Text conversation turn: history within one conversation, budget check, LLM call, usage log.

Raw history comes only from the current conversation. The only cross-conversation context is
curated memory of the same owner, and only when that owner opted in.

With learned rules, the finished reply goes through one short check that may rewrite it. The check
fails open: whatever goes wrong there, the original reply stands and the turn succeeds.
"""

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.arm.service import work_record
from core.behavior import state as behavior_state
from core.conversation import attachments, progress
from core.identity.capabilities import Capabilities
from core.identity.system_prompt import (
    RULE_CHECK_INSTRUCTIONS,
    build_system_prompt,
    learned_rules_block,
)
from core.memory.retrieval import ScoredMemory, retrieve
from core.memory.text import fold, tokens
from infrastructure.database.models import (
    AgentIdentity,
    Attachment,
    Conversation,
    MemoryRetrieval,
    Message,
    ModelUsage,
    User,
)
from integrations.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse, drafting

if TYPE_CHECKING:
    from core.conversation.artifacts import Request as PageRequest

logger = logging.getLogger(__name__)

PURPOSE_CHAT = "chat_reply"
PURPOSE_RULE_CHECK = "rule_check"
TRUNCATION_NOTICE = "[resposta interrompida pelo limite de tamanho]"

# Below this a reply is a thanks or a goodbye; a question is still worth checking.
TRIVIAL_REPLY_CHARS = 40
RULE_CHECK_DEADLINE_SECONDS = 4.0
RECENT_ENDINGS = 3
ENDING_CHARS = 120
_URL = re.compile(r"https?://[^\s)\]>]+|www\.[^\s)\]>]+", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"\w+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?:\n])\s+")
# First-person past: what the truth rules forbid claiming without a record.
_CLAIMED_ACTIONS = frozenset(
    """
    abri agendei anotei busquei chequei confirmei consultei encontrei enviei estudei executei fiz
    guardei lembrei li mandei olhei pesquisei procurei publiquei rodei salvei testei verifiquei vi
    """.split()
)


class BudgetExceededError(Exception):
    def __init__(self, scope: str, spent: Decimal, limit: Decimal) -> None:
        super().__init__(f"{scope} LLM budget exhausted: {spent} of {limit} USD")
        self.scope = scope


class EmptyReplyError(Exception):
    pass


@dataclass(frozen=True)
class Budgets:
    daily_usd: Decimal
    conversation_usd: Decimal


@dataclass(frozen=True)
class TurnResult:
    user_message: Message
    assistant_message: Message
    usage: ModelUsage
    recalled: list[ScoredMemory]
    # The reply asked for a page (core/conversation/artifacts.py); the route records it.
    page: "PageRequest | None" = None


def _spent(session: Session, *conditions: object) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(ModelUsage.cost_usd), 0)).where(*conditions)
    )
    return Decimal(str(total))


def check_budgets(session: Session, conversation: Conversation, budgets: Budgets) -> None:
    """Pre-call check. A single call can overshoot by at most one reply (bounded by max tokens)."""
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    daily = _spent(session, ModelUsage.created_at >= start_of_day)
    if daily >= budgets.daily_usd:
        raise BudgetExceededError("daily", daily, budgets.daily_usd)
    per_conversation = _spent(session, ModelUsage.conversation_id == conversation.id)
    if per_conversation >= budgets.conversation_usd:
        raise BudgetExceededError("conversation", per_conversation, budgets.conversation_usd)


def conversation_history(session: Session, conversation: Conversation) -> list[Message]:
    return list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        )
    )


def build_context(
    history: list[Message],
    char_budget: int,
    files: dict[uuid.UUID, list[Attachment]] | None = None,
    redacted: dict[uuid.UUID, str] | None = None,
) -> list[ChatMessage]:
    """Most recent messages that fit the budget, oldest first. The latest one is always kept.

    Photos and file text go with the latest messages only; older ones just name their files."""
    files = files or {}
    by_id = {m.id: m for m in history}
    allowance = attachments.ContextAllowance()
    selected: list[ChatMessage] = []
    used = 0
    for position, message in enumerate(reversed(history)):
        if selected and used + len(message.content) > char_budget:
            break
        content, images = message.content, ()
        if redacted and message.id in redacted:
            # A reply of its own that denied something it really did: the model reads a note,
            # the person still sees the reply (core/decision/record.py).
            content = redacted[message.id]
        quoted = by_id.get(message.reply_to_id) if message.reply_to_id else None
        if quoted is not None:
            # She tapped Responder on an earlier message: say which, so "isso" has a referent.
            who = "sua" if quoted.role == "assistant" else "dela"
            excerpt = " ".join(quoted.content.split())[:QUOTE_CHARS]
            content = f"[Respondendo a esta mensagem {who}: «{excerpt}»]\n{content}"
        block, images = attachments.render(
            files.get(message.id, []), allowance, recent=position < attachments.RECENT_MESSAGES
        )
        if block:
            content = f"{content}\n\n{block}" if content.strip() else block
        selected.append(ChatMessage(role=message.role, content=content, images=images))  # type: ignore[arg-type]
        used += len(message.content)
    selected.reverse()
    return selected


QUOTE_CHARS = 300
# What a provider answers when the request itself is not acceptable (e.g. images to a text model).
REJECTED_INPUT = {"http_400", "http_413", "http_415", "http_422"}
NO_VISION_NOTE = (
    "[Sistema] O modelo de agora não recebe imagens: as fotos desta conversa não chegaram até "
    "você. Diga isso à pessoa em uma frase e responda ao resto; não descreva foto nenhuma."
)


def without_images(prompt: list[ChatMessage]) -> list[ChatMessage]:
    return [
        replace(m, images=(), content=f"{m.content}\n\n{NO_VISION_NOTE}") if m.images else m
        for m in prompt
    ]


def reply(
    session: Session,
    *,
    conversation: Conversation,
    identity: AgentIdentity,
    owner: User,
    user_text: str,
    provider: LLMProvider,
    budgets: Budgets,
    max_output_tokens: int,
    context_char_budget: int,
    extra_system: str | None = None,
    capabilities: Capabilities | None = None,
    modality: str = "text",
    name_history_summary: str | None = None,
    self_text: str | None = None,
    owner_profile: str = "",
    owner_rules: str = "",
    attachment: str = "",
    files: list[Attachment] | None = None,
    reply_to_id: uuid.UUID | None = None,
) -> TurnResult:
    check_budgets(session, conversation, budgets)

    user_message = Message(
        conversation_id=conversation.id, role="user", content=user_text, reply_to_id=reply_to_id
    )
    session.add(user_message)
    session.flush()
    attachments.claim(files or [], user_message)

    # Memory is recalled only for owners who opted in, and only from their own records.
    recalled = retrieve(session, owner.id, user_text) if owner.memory_consent else []
    for item in recalled:
        session.add(
            MemoryRetrieval(message_id=user_message.id, record_id=item.record.id, score=item.score)
        )
    session.commit()

    system_prompt = build_system_prompt(
        identity,
        memory_enabled=owner.memory_consent,
        memories=[item.record for item in recalled],
        capabilities=capabilities,
        name_history_summary=name_history_summary,
        modality=modality,
        self_text=self_text,
        owner_profile=owner_profile,
        owner_rules=owner_rules,
        arm_record=work_record(session, owner.id, owner.timezone or "UTC"),
    )
    version, params = behavior_state.current_params(session, owner.id)
    adjustments = behavior_state.prompt_lines(params)
    if adjustments:
        system_prompt += (
            f"\n\nAjustes de comunicação aprendidos com o retorno deste interlocutor "
            f"(versão {version}, revertíveis):\n" + "\n".join(f"- {a}" for a in adjustments)
        )
    if extra_system:
        # Per-turn context from the curiosity pipeline (a question to ask, or sources).
        system_prompt += f"\n\nContexto desta resposta:\n{extra_system}"
    if owner_rules:
        system_prompt += "\n\n" + learned_rules_block(owner_rules)
    prompt = [ChatMessage(role="system", content=system_prompt)]
    from core.decision import record as deed_record

    history = conversation_history(session, conversation)
    prompt += build_context(
        history,
        context_char_budget,
        attachments.for_messages(
            session, [m.id for m in history[-attachments.RECENT_MESSAGES * 4 :]]
        ),
        deed_record.false_denials(session, conversation, owner),
    )
    if attachment and prompt[-1].role == "user":
        # What came with this message (a page it opened) goes with the message itself, the last
        # thing read: in the system prompt it lost to earlier replies saying the opposite.
        prompt[-1] = replace(prompt[-1], content=f"{prompt[-1].content}\n\n{attachment}")

    progress.step("Escrevendo a resposta")
    try:
        response = _write(provider, prompt, max_output_tokens, modality)
    except LLMError as exc:
        _record_failure(session, conversation, provider, exc.kind)
        if exc.kind not in REJECTED_INPUT or not any(m.images for m in prompt):
            raise
        # The model in use does not take pictures: answer without them, and say so, instead of
        # failing every message that has a photo.
        prompt = without_images(prompt)
        try:
            response = _write(provider, prompt, max_output_tokens, modality)
        except LLMError as again:
            _record_failure(session, conversation, provider, again.kind)
            raise

    usage = ModelUsage(
        conversation_id=conversation.id,
        purpose=PURPOSE_CHAT,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
        outcome="success" if response.text.strip() else "empty",
    )
    truncated = response.finish_reason == "length"
    if truncated and response.text.strip():
        # Real case (2026-10-31): a reasoning model spent the output budget thinking and the
        # reply stopped mid-sentence. Never present a cut reply as complete.
        usage.outcome = "truncated"
    session.add(usage)
    if progress.cancelled():
        # Parar while it was writing: the call is paid for and recorded, the reply is not kept.
        session.commit()
        raise progress.TurnCancelled()
    if not response.text.strip():
        session.commit()
        raise EmptyReplyError("provider returned an empty reply")

    from core.conversation.artifacts import take_marker  # artifacts builds on this module

    content, page = take_marker(response.text)
    if page is not None and not content.strip():
        content = f"Vou montar a página “{page.title}”. Ela aparece aqui quando ficar pronta."
    if owner_rules and not truncated and modality != "voice":
        # Not in a voice call: the check is a second model call before anything can be spoken
        # (up to RULE_CHECK_DEADLINE_SECONDS), and the rules already ride in the system prompt.
        # Committed first: the call's admission ledger needs the write lock this session would hold.
        session.commit()
        progress.step("Conferindo as suas regras")
        content = _obey_rules(
            session,
            conversation=conversation,
            provider=provider,
            budgets=budgets,
            rules=owner_rules,
            prompt=prompt,
            draft=content,
            max_output_tokens=max_output_tokens,
        )
    if truncated:
        content = content.rstrip() + f"\n\n{TRUNCATION_NOTICE}"
    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=content)
    session.add(assistant_message)
    session.flush()
    assistant_message.model_usage_id = usage.id
    # Observable behavior, measured in code, tagged with the state version in force.
    behavior_state.observe(session, assistant_message, owner.id)
    session.commit()
    return TurnResult(user_message, assistant_message, usage, recalled, page)


def _write(
    provider: LLMProvider, prompt: list[ChatMessage], max_output_tokens: int, modality: str
) -> LLMResponse:
    """The reply. In a voice call it streams into the turn's progress, so the phone can start
    speaking the first sentence while the rest is written (a provider that cannot stream answers
    whole, as before)."""
    if modality != "voice":
        return provider.complete(prompt, max_output_tokens=max_output_tokens)
    with drafting(progress.draft):
        return provider.complete(prompt, max_output_tokens=max_output_tokens)


def _obey_rules(
    session: Session,
    *,
    conversation: Conversation,
    provider: LLMProvider,
    budgets: Budgets,
    rules: str,
    prompt: list[ChatMessage],
    draft: str,
    max_output_tokens: int,
) -> str:
    """The reply to send: `draft`, or its rewrite when it broke a rule and the rewrite is safe."""
    if len(draft.strip()) < TRIVIAL_REPLY_CHARS and "?" not in draft:
        return draft
    try:
        check_budgets(session, conversation, budgets)
    except BudgetExceededError:
        return draft

    user_text = prompt[-1].content
    endings = [m.content[-ENDING_CHARS:] for m in prompt if m.role == "assistant"]
    payload = {
        "regras": rules,
        "mensagem": user_text,
        "respostas_anteriores": endings[-RECENT_ENDINGS:],
        "resposta": draft,
    }
    messages = [
        ChatMessage(role="system", content=RULE_CHECK_INSTRUCTIONS),
        ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]
    # Reservations stay charged to the daily budget, so this asks only for what a rewrite can use.
    limit = min(max_output_tokens, len(draft) // 2 + 200)
    try:
        response = _complete_within_deadline(provider, messages, limit)
    except Exception as exc:
        # Fail open on anything, not only LLMError: this step must never cost the owner the reply.
        kind = exc.kind if isinstance(exc, LLMError) else type(exc).__name__
        logger.warning(f"rule check skipped: {kind}", extra={"event": "rule_check_failed"})
        _record_failure(session, conversation, provider, kind, purpose=PURPOSE_RULE_CHECK)
        return draft

    usage = ModelUsage(
        conversation_id=conversation.id,
        purpose=PURPOSE_RULE_CHECK,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
        outcome="success",
    )
    session.add(usage)
    if response.finish_reason == "length":
        usage.outcome = "truncated"
        return draft
    verdict = _parse_verdict(response.text)
    if verdict is None:
        usage.outcome = "bad_output"
        return draft
    if verdict is True or verdict == draft.strip():
        return draft
    refused = _refuse_rewrite(draft, verdict, context=f"{rules}\n{user_text}")
    if refused:
        usage.outcome, usage.error_kind = "refused", refused
        return draft
    usage.outcome = "rewritten"
    return verdict


def _complete_within_deadline(
    provider: LLMProvider, messages: list[ChatMessage], limit: int
) -> LLMResponse:
    """The provider timeout is 60 s, too long to hold a reply that is already done. A call past the
    deadline finishes on its thread, where the budget guard still settles it."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rule-check")
    try:
        future = pool.submit(provider.complete, messages, max_output_tokens=limit)
        try:
            return future.result(timeout=RULE_CHECK_DEADLINE_SECONDS)
        except FutureTimeoutError:
            raise LLMError("deadline", "rule check over its deadline") from None
    finally:
        pool.shutdown(wait=False)


def _parse_verdict(text: str) -> bool | str | None:
    """True when the reply obeys, the rewrite when it does not, None when the answer is unusable."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        # strict=False: models often put raw line breaks inside the rewrite.
        data = json.loads(match.group(0), strict=False) if match else None
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("obeys") is True:
        return True
    rewrite = data.get("rewrite")
    if data.get("obeys") is False and isinstance(rewrite, str) and rewrite.strip():
        return rewrite.strip()
    return None


def _names(text: str) -> set[str]:
    """Capitalized words past the first of each sentence, where a capital means a name."""
    found: set[str] = set()
    for sentence in _SENTENCE_BREAK.split(text):
        found |= {w for w in _WORD.findall(sentence)[1:] if w[0].isupper()}
    return {fold(name) for name in found}


def _words(sentence: str) -> list[str]:
    return _WORD.findall(fold(sentence))


def _asserts_a_question(draft: str, rewrite: str) -> bool:
    """Real case: "O churrasco rolou?" came back as "O churrasco rolou.", which states a fact."""
    asked = [_words(s) for s in _SENTENCE_BREAK.split(draft) if s.rstrip().endswith("?")]
    stated = [_words(s) for s in _SENTENCE_BREAK.split(rewrite) if not s.rstrip().endswith("?")]
    return any(sentence in stated for sentence in asked)


def _refuse_rewrite(draft: str, rewrite: str, *, context: str) -> str | None:
    """Why this rewrite cannot replace the reply, or None. Checked in code, not left to the model:
    the rules may reshape what was said, never add to it. Names may also come from `context`,
    which holds the owner's words ("me chame de Ali")."""
    if len(rewrite) > len(draft) * 1.2 + 40:
        return "longer"
    if set(_URL.findall(rewrite)) - set(_URL.findall(draft)):
        return "new_url"
    if set(_NUMBER.findall(rewrite)) - set(_NUMBER.findall(draft)):
        return "new_number"
    known = set(_words(f"{draft}\n{context}"))
    if _names(rewrite) - known:
        return "new_name"
    if (set(_words(rewrite)) & _CLAIMED_ACTIONS) - set(_words(draft)):
        return "new_action"
    if _asserts_a_question(draft, rewrite):
        return "question_as_statement"
    # A rewrite trims what is there. Mostly new words means another reply took its place.
    new_words = tokens(rewrite) - tokens(draft)
    if len(new_words) > max(3, len(tokens(rewrite)) * 0.4):
        return "new_words"
    return None


def _record_failure(
    session: Session,
    conversation: Conversation,
    provider: LLMProvider,
    error_kind: str,
    *,
    purpose: str = PURPOSE_CHAT,
) -> None:
    session.add(
        ModelUsage(
            conversation_id=conversation.id,
            purpose=purpose,
            provider=provider.name,
            model=provider.model,
            outcome="error",
            error_kind=error_kind[:50],
        )
    )
    session.commit()
