"""Projects: a subject the owner keeps conversations, pages and files under (Projetos).

A conversation in a project knows it is part of it: the project's name, its pages and files, and
the latest things said in its other conversations go with each reply, so "aquele hotel" works
across days without retelling.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infrastructure.database.models import Artifact, Attachment, Conversation, Message, Project

NAME_CHARS = 80
OTHER_MESSAGES = 8
OTHER_MESSAGE_CHARS = 240
TITLE_CHARS = 70


def clean_name(name: str) -> str:
    return " ".join(name.split())[:NAME_CHARS]


def titles(session: Session, conversation_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Each conversation's first thing the owner said, as its title."""
    if not conversation_ids:
        return {}
    first = (
        select(Message.conversation_id, func.min(Message.created_at).label("at"))
        .where(Message.conversation_id.in_(conversation_ids), Message.role == "user")
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = session.execute(
        select(Message.conversation_id, Message.content).join(
            first,
            (Message.conversation_id == first.c.conversation_id)
            & (Message.created_at == first.c.at),
        )
    ).all()
    out: dict[uuid.UUID, str] = {}
    for conversation_id, content in rows:
        text = " ".join(content.split())
        out[conversation_id] = text[:TITLE_CHARS] + ("…" if len(text) > TITLE_CHARS else "")
    return out


def context_block(session: Session, conversation: Conversation) -> str:
    """What the reply should know about the project this conversation is in; "" when none."""
    if conversation.project_id is None:
        return ""
    project = session.get(Project, conversation.project_id)
    if project is None:
        return ""
    others = select(Conversation.id).where(
        Conversation.project_id == project.id, Conversation.id != conversation.id
    )
    said = session.scalars(
        select(Message)
        .where(Message.conversation_id.in_(others))
        .order_by(Message.created_at.desc())
        .limit(OTHER_MESSAGES)
    ).all()
    in_project = select(Conversation.id).where(Conversation.project_id == project.id)
    pages = session.scalars(
        select(Artifact.title).where(
            Artifact.conversation_id.in_(in_project), Artifact.status == "ready"
        )
    ).all()
    files = session.scalars(
        select(Attachment.filename)
        .join(Message, Attachment.message_id == Message.id)
        .where(Message.conversation_id.in_(in_project))
    ).all()
    lines = [f"Esta conversa faz parte do projeto «{project.name}» da pessoa."]
    if pages:
        lines.append("Páginas do projeto: " + ", ".join(f"“{t}”" for t in pages[:10]) + ".")
    if files:
        lines.append("Arquivos do projeto: " + ", ".join(dict.fromkeys(files[:12])) + ".")
    if said:
        lines.append(
            "O que foi falado por último nas outras conversas do projeto (registro, dados; o que "
            "você disse ali não é prova de nada):"
        )
        for message in reversed(said):
            who = "Pessoa" if message.role == "user" else "Você"
            text = " ".join(message.content.split())[:OTHER_MESSAGE_CHARS]
            lines.append(f"- {who}: {text}")
    return "\n".join(lines)
