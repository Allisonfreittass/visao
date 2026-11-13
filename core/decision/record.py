"""What it really did in a conversation, from the database, never from what it said.

Each turn's plan is stored (core/decision/turn.py). Without reading it back, a later turn saw its
own reply listing the owner's emails, found no record of reading them, and apologized for "making
it up" (real case, 2026-11-13). This is the record the truth rules point to: an action listed here
happened; one missing here must not be claimed.
"""

import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.database.models import Artifact, Conversation, Decision, Message, User

RECORD_MESSAGES = 40
RECORD_LINES = 14

HEADING = (
    "O que você fez de verdade nesta conversa (registro do sistema, tirado do banco; não é o que "
    "você disse, é o que rodou):"
)
RULE = (
    "Você não vê as leituras antigas diretamente (o que foi lido não fica no histórico): este"
    " registro, gravado pelo sistema quando a ação rodou, é como você sabe delas, e é confiável."
    " Isto aconteceu de verdade. Quando uma resposta sua anterior traz dados (emails, eventos, "
    "fontes, o conteúdo de um link ou arquivo, uma página) e a ação que os trouxe está neste "
    "registro, os dados vieram dela: se perguntarem, confirme que leu ou fez, nunca diga que não "
    "fez nem peça desculpas por ter feito. Se antes você negou algo que está aqui, corrija agora "
    "e diga que foi de verdade. O que não está aqui nem nas ações deste turno, não afirme."
)


def _google(action: dict[str, Any]) -> str:
    parts = []
    if "gmail" in action.get("sources", []):
        query = action.get("email_query")
        found = action.get("emails_found")
        detail = ", ".join(
            x
            for x in (
                f"busca “{query}”" if query else "",
                f"{found} email(s)" if found is not None else "",
            )
            if x
        )
        parts.append("leu o Gmail da pessoa" + (f" ({detail})" if detail else ""))
    if "agenda" in action.get("sources", []):
        days = action.get("calendar_days")
        parts.append("leu a Google Agenda" + (f" (próximos {days} dia(s))" if days else ""))
    return " e ".join(parts)


def _hosts(urls: list[str]) -> str:
    return ", ".join(dict.fromkeys((urlsplit(u).hostname or u).removeprefix("www.") for u in urls))


_SAY: dict[str, Callable[[dict[str, Any]], str]] = {
    "google_read": _google,
    "google_proposed": lambda a: "preparou um email ou evento, que espera a aprovação da pessoa",
    "read_links": lambda a: "abriu e leu " + _hosts(a.get("opened") or a.get("urls") or []),
    "read_links_failed": lambda a: (
        "tentou abrir " + _hosts(a.get("urls") or []) + " e não conseguiu"
    ),
    "browsed": lambda a: (
        "abriu num navegador de verdade "
        + (_hosts(a.get("opened") or []) or "nenhuma página")
        + (f" ({len(a['opened'])} página(s))" if a.get("opened") else "")
        + (f"; não abriram: {len(a.get('failures') or [])}" if a.get("failures") else "")
    ),
    "read_attachments": lambda a: (
        "viu os anexos que a pessoa mandou"
        + (f" ({', '.join(a['names'])})" if a.get("names") else "")
    ),
    "research": lambda a: (
        f"pesquisou na web: “{a.get('question', '')}” ({a.get('sources', 0)} fonte(s))"
    ),
    "mac_proposed": lambda a: f"montou um pedido ao Mac em {a.get('project', '?')}, para aprovar",
    "read_own_code": lambda a: "leu trechos do próprio código",
    "recall_study": lambda a: "consultou o caderno de estudos",
    "goal_proposed": lambda a: "propôs uma meta, que espera aprovação",
}


def deeds(actions: list[dict[str, Any]]) -> list[str]:
    """The executed actions of one turn, in plain words."""
    said = []
    for action in actions or []:
        if not action.get("executed"):
            continue
        say = _SAY.get(action.get("action", ""))
        if say is not None:
            text = say(action)
            if text:
                said.append(text)
    return said


def by_message(session: Session, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not message_ids:
        return {}
    done: dict[uuid.UUID, list[str]] = {}
    for decision in session.scalars(select(Decision).where(Decision.message_id.in_(message_ids))):
        words = deeds(decision.actions)
        if words and decision.message_id is not None:
            done.setdefault(decision.message_id, []).extend(words)
    for page in session.scalars(select(Artifact).where(Artifact.message_id.in_(message_ids))):
        state = {"ready": "pronta", "pending": "sendo escrita", "failed": "falhou"}[page.status]
        done.setdefault(page.message_id, []).append(f"montou a página “{page.title}” ({state})")  # type: ignore[arg-type]
    return done


def _local(owner: User, moment: datetime) -> str:
    try:
        zone = ZoneInfo(owner.timezone or "UTC")
    except Exception:  # noqa: BLE001 - an unknown zone falls back to UTC
        zone = ZoneInfo("UTC")
    stamp = moment if moment.tzinfo else moment.replace(tzinfo=ZoneInfo("UTC"))
    return stamp.astimezone(zone).strftime("%d/%m %H:%M")


def conversation_block(session: Session, conversation: Conversation, owner: User) -> str:
    """The record for the prompt, or "" when it did nothing beyond talking."""
    recent = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(RECORD_MESSAGES)
    ).all()
    done = by_message(session, [m.id for m in recent])
    lines = [
        f"- {_local(owner, m.created_at)}: " + "; ".join(done[m.id])
        for m in reversed(recent)
        if m.id in done
    ][-RECORD_LINES:]
    if not lines:
        return ""
    return "\n".join([HEADING, *lines, RULE])


# A reply that says it did not do something it did. Real case, 2026-11-13: the Gmail was read at
# 09:58; at 12:49, 12:51 and 14:18 it said "não tenho acesso", "não veio de uma leitura minha".
# A record in the system prompt lost to those replies, and a correction pasted into the person's
# message was distrusted as text claiming to be the system ("o registro que apareceu aqui não deve
# ser usado como base"). So the false denials leave the context the model reads (the person still
# sees them), the record says how it knows, and a correction is asked for only until it is made.
_DENIAL = re.compile(
    r"n[ãa]o (?:tenho|tive|tinha) (?:como )?acess|n[ãa]o (?:li|lia|leio|abri|vi|pesquisei|fiz)\b|"
    r"n[ãa]o consegui (?:ler|abrir|ver|acessar)|n[ãa]o consigo (?:ver|confirmar|acessar|checar)|"
    r"n[ãa]o (?:veio|vem) de uma leitura|n[ãa]o foi uma leitura|n[ãa]o sei de onde|"
    r"sem ter (?:lido|acesso)|n[ãa]o (?:fiz|foi) (?:essa|uma) leitura|"
    r"n[ãa]o posso (?:sustentar|confirmar|garantir)|n[ãa]o conte com a minha palavra|"
    r"n[ãa]o deve ser usado como base|qual vers[ãa]o [ée] a verdadeira|recusei essa confian[çc]a|"
    r"n[ãa]o (?:sei|tenho como saber) se (?:li|abri|aconteceu)|"
    r"n[ãa]o (?:tinha|tenho|havia) (?:lido|aberto|pesquisado|visto)",
    re.IGNORECASE,
)
# A reply that owns up to it ("eu li o seu Gmail às 09:58, de verdade").
_AFFIRM = re.compile(
    r"\b(?:li|abri|pesquisei|naveguei|vi)\b[^.]{0,90}\bde verdade\b|vieram dessa leitura|"
    r"vieram dali|foi de verdade",
    re.IGNORECASE,
)
_TOPIC = {
    "google_read": re.compile(r"e-?mails?|gmail|caixa|agenda", re.IGNORECASE),
    "read_links": re.compile(r"links?|site|p[áa]gina", re.IGNORECASE),
    "browsed": re.compile(r"site|p[áa]gina|pre[çc]o|voo|naveg", re.IGNORECASE),
    "read_attachments": re.compile(r"foto|arquivo|anexo|imagem|pdf", re.IGNORECASE),
    "research": re.compile(r"pesquis|fonte", re.IGNORECASE),
}
# The person asking about what it did ("você leu mesmo?", "qual a chance de ser coincidência?").
_ASKS = re.compile(
    r"\b(?:leu|ler|lido|lida|lendo|acess\w*|abriu|viu|pesquisou|fez|coincid\w*|invent\w*|"
    r"mentiu|mentira|de onde)\b",
    re.IGNORECASE,
)


def _scan(session: Session, conversation: Conversation):
    """(events, false denials by message id, denials not yet owned up to)."""
    recent = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(RECORD_MESSAGES)
    ).all()
    recent = list(reversed(recent))
    decisions = {
        d.message_id: d
        for d in session.scalars(
            select(Decision).where(Decision.message_id.in_([m.id for m in recent]))
        )
    }
    events: list[tuple[Message, str, str]] = []  # (reply that did it, action, words)
    false: dict[uuid.UUID, tuple[Message, str]] = {}
    open_: dict[str, tuple[Message, Message, str]] = {}  # action -> (denial, event, words)
    for message in recent:
        for action in decisions[message.id].actions if message.id in decisions else []:
            name = action.get("action", "")
            if action.get("executed") and name in _TOPIC:
                words = deeds([action])
                if words:
                    events.append((message, name, words[0]))
        earlier = [e for e in events if e[0].created_at < message.created_at]
        topics = {name for _, name, _ in earlier if _TOPIC[name].search(message.content)}
        if not topics:
            continue
        if _AFFIRM.search(message.content):
            for name in topics:
                open_.pop(name, None)
            continue
        if _DENIAL.search(message.content):
            done, name, words = next(e for e in reversed(earlier) if e[1] in topics)
            false[message.id] = (done, words)
            open_[name] = (message, done, words)
    return events, false, list(open_.values())


def false_denials(
    session: Session, conversation: Conversation, owner: User
) -> dict[uuid.UUID, str]:
    """What replaces, in the context the model reads, each reply that denied a real action."""
    _, false, _ = _scan(session, conversation)
    if not false:
        return {}
    contents = {
        m.id: m.content for m in session.scalars(select(Message).where(Message.id.in_(list(false))))
    }
    notes = {}
    for message_id, (done, words) in false.items():
        # Only the paragraphs that deny it go; the rest of the reply (a plan, an answer) stays.
        kept = [
            p
            for p in re.split(r"\n\s*\n", contents.get(message_id, ""))
            if p.strip()
            if not _DENIAL.search(p)
        ]
        note = (
            f"[Nota do sistema: aqui você negou, por engano, que {words} às"
            f" {_local(owner, done.created_at)}. Isso aconteceu de verdade; a negação foi tirada.]"
        )
        notes[message_id] = "\n\n".join([note, *kept])
    return notes


def owner_events(
    session: Session, owner: User, conversations: int = 3
) -> list[tuple[datetime, str, str]]:
    """(when, action, words) of the real actions in the owner's latest conversations."""
    latest = session.scalars(
        select(Conversation)
        .where(Conversation.user_id == owner.id)
        .order_by(Conversation.created_at.desc())
        .limit(conversations)
    ).all()
    found = []
    for conversation in latest:
        events, _, _ = _scan(session, conversation)
        found += [(m.created_at, name, words) for m, name, words in events]
    return found


def thought_without_doubt(
    text: str, events: list[tuple[datetime, str, str]], owner: User, at: datetime
) -> str:
    """A thought of its own that doubts a recorded action becomes a note with the fact: the next
    thought and the next reply start from what happened, not from the doubt (real case: a whole
    afternoon of "não consigo ver daqui" after the Gmail was read)."""
    if _AFFIRM.search(text) or not _DENIAL.search(text):
        return text
    earlier = [e for e in events if e[0] < at and _TOPIC[e[1]].search(text)]
    if not earlier:
        return text
    when, _, words = earlier[-1]
    return (
        f"[Nota do sistema: um pensamento seu aqui duvidava de que {words} às"
        f" {_local(owner, when)}; pelo registro do sistema, isso aconteceu de verdade. A dúvida"
        " foi tirada.]"
    )


def correction_block(
    session: Session, conversation: Conversation, owner: User, user_text: str
) -> str:
    """For the system prompt: the denials not yet owned up to, once; or, when the person asks
    about what it did, the plain facts. "" when there is nothing to say."""
    events, _, unanswered = _scan(session, conversation)
    asked = bool(_ASKS.search(user_text))
    if unanswered:
        lines = ["Correção pendente, do registro do sistema:"]
        lines += [
            f"- Às {_local(owner, denial.created_at)} você negou, por engano, que {words} às"
            f" {_local(owner, done.created_at)}. Aquilo foi de verdade."
            for denial, done, words in unanswered[-4:]
        ]
        lines.append(
            "Nesta resposta, diga isso uma vez, curto e claro: que fez de verdade e que a negação"
            " estava errada, com um pedido de desculpas só. Depois responda ao que a pessoa disse."
            " Não repita a correção nas próximas respostas e não volte a duvidar dela."
        )
        return "\n".join(lines)
    if asked and events:
        return (
            "A pessoa pergunta sobre o que você fez: responda pelo registro acima, que é do"
            " sistema e confiável. Confirme sem rodeio o que está nele; o que não está, não afirme."
        )
    return ""


def timeline(
    session: Session, conversation: Conversation, owner: User
) -> list[tuple[datetime, str]]:
    """Each earlier reply's real actions with its time, oldest first, for the Bancada."""
    recent = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(RECORD_MESSAGES)
    ).all()
    done = by_message(session, [m.id for m in recent])
    return [(m.created_at, "; ".join(done[m.id])) for m in reversed(recent) if m.id in done]
