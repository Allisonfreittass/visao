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
    "Isto aconteceu de verdade. Quando uma resposta sua anterior traz dados (emails, eventos, "
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


# A reply that says it did not do something. Real case, 2026-11-13: the Gmail was read at 09:58,
# and at 12:51 and 14:18 it said "não tenho acesso", "não veio de uma leitura minha"; the record in
# the system prompt lost to its own earlier replies, so the correction goes with the message.
_DENIAL = re.compile(
    r"n[ãa]o (?:tenho|tive|tinha) (?:como )?acess|n[ãa]o (?:li|lia|leio|abri|vi|pesquisei|fiz)\b|"
    r"n[ãa]o consegui (?:ler|abrir|ver|acessar)|n[ãa]o (?:veio|vem) de uma leitura|"
    r"n[ãa]o foi uma leitura|n[ãa]o sei de onde|sem ter (?:lido|acesso)|"
    r"n[ãa]o (?:fiz|foi) (?:essa|uma) leitura",
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


def correction_block(
    session: Session, conversation: Conversation, owner: User, user_text: str
) -> str:
    """Goes with the person's message, the last thing the model reads: what it really did, and
    every later reply of its own that denied it. "" when there is nothing to say."""
    recent = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(RECORD_MESSAGES)
    ).all()
    recent = list(reversed(recent))
    if not recent:
        return ""
    decisions = {
        d.message_id: d
        for d in session.scalars(
            select(Decision).where(Decision.message_id.in_([m.id for m in recent]))
        )
    }
    events: list[tuple[Message, str, str]] = []  # (reply, action, words)
    contradictions: list[str] = []
    for message in recent:
        for action in decisions[message.id].actions if message.id in decisions else []:
            name = action.get("action", "")
            if action.get("executed") and name in _TOPIC:
                words = deeds([action])
                if words:
                    events.append((message, name, words[0]))
        if not _DENIAL.search(message.content):
            continue
        for done, name, words in events:
            if done.created_at < message.created_at and _TOPIC[name].search(message.content):
                contradictions.append(
                    f"- Às {_local(owner, message.created_at)} você disse que não tinha feito isso,"
                    f" mas às {_local(owner, done.created_at)} {words} de verdade. Aquela negação"
                    " estava errada."
                )
                break
    asked = bool(_ASKS.search(user_text))
    if not contradictions and not (asked and events):
        return ""
    lines = [
        "[Registro do sistema, não escrito pela pessoa] O que você fez de verdade nesta conversa,"
        " tirado do banco (não do que você disse):"
    ]
    lines += [f"- Às {_local(owner, m.created_at)}: {w}" for m, _, w in events[-6:]]
    if contradictions:
        lines.append("Depois disso você negou ter feito:")
        lines += contradictions[-4:]
        lines.append(
            "Corrija agora, com clareza e sem rodeio: diga que fez de verdade, que os dados da"
            " sua resposta vieram dali, e peça desculpas por ter negado. Não volte a negar."
        )
    else:
        lines.append(
            "Se a pessoa pergunta sobre isso, confirme: os dados das suas respostas vieram dessas"
            " ações."
        )
    return "\n".join(lines)


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
