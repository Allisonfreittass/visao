"""Projects: a subject the owner keeps conversations, pages and files under (Projetos).

A conversation in a project knows it is part of it: the project's name, its pages and files, and
the latest things said in its other conversations go with each reply, so "aquele hotel" works
across days without retelling.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.memory.text import fold, tokens
from infrastructure.database.models import (
    Artifact,
    Attachment,
    Conversation,
    Message,
    Project,
    User,
)

NAME_CHARS = 80
OTHER_MESSAGES = 8
OTHER_MESSAGE_CHARS = 240
TITLE_CHARS = 70
NOTES_IN_REPLY = 1500
PROJECTS_IN_REPLY = 2
MAX_NAMES = 20


def clean_name(name: str) -> str:
    return " ".join(name.split())[:NAME_CHARS]


def same_name(
    owned: list[Project], name: str, *, other_than: uuid.UUID | None = None
) -> Project | None:
    """The owner's project already called this, ignoring case, accents and extra spaces. When
    renaming, `other_than` is the project itself, so a change of case is not a clash."""
    wanted = fold(clean_name(name))
    return next((p for p in owned if p.id != other_than and fold(p.name) == wanted), None)


def owned(session: Session, owner_id: uuid.UUID) -> list[Project]:
    return list(
        session.scalars(
            select(Project).where(Project.owner_user_id == owner_id).order_by(Project.created_at)
        )
    )


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


def notes_block(session: Session, owner: User, conversation: Conversation, text: str) -> str:
    """The owner's projects by name, and the notes of those the message is about (the one this
    conversation is in, or up to 2 whose name or notes share words with it), so "e o voo da
    JetSMART?" in the continuous conversation finds what was noted (ADR-0021)."""
    rows = list(
        session.scalars(
            select(Project).where(Project.owner_user_id == owner.id).order_by(Project.created_at)
        )
    )
    if not rows:
        return ""
    said = tokens(text)
    chosen = [p for p in rows if p.id == conversation.project_id and p.notes.strip()]
    scored = sorted(
        (
            (len(said & tokens(p.name)) * 3 + len(said & tokens(p.notes)), p)
            for p in rows
            if p.notes.strip() and p not in chosen
        ),
        key=lambda pair: -pair[0],
    )
    chosen += [p for score, p in scored if score >= 2][: PROJECTS_IN_REPLY - len(chosen)]
    lines = [
        "Projetos da pessoa no app: "
        + ", ".join(f"«{p.name}»" for p in rows[-MAX_NAMES:])
        + ". Você cria, renomeia, anota e apaga projetos pela conversa quando ela pede."
    ]
    for project in chosen:
        lines.append(
            f"Anotações do projeto «{project.name}» (escritas por você a pedido dela; dados):\n"
            + project.notes[-NOTES_IN_REPLY:]
        )
    return "\n".join(lines)


def chat_for(session: Session, owner: User, project: Project) -> Conversation:
    """The project's own chat: its latest conversation, made the first time with an opening
    message of its own saying what the project holds (like the first page of a notebook)."""
    found = session.scalar(
        select(Conversation)
        .where(Conversation.user_id == owner.id, Conversation.project_id == project.id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    if found is not None:
        return found
    from core.identity.genesis import get_identity

    identity = get_identity(session)
    if identity is None:
        raise LookupError("no identity yet")
    found = Conversation(user_id=owner.id, identity_id=identity.id, project_id=project.id)
    session.add(found)
    session.flush()
    # The notes live in the card on top of this chat; repeating them here showed them twice.
    lines = sum(1 for line in project.notes.splitlines() if line.strip())
    opening = (
        f"Aqui fica tudo de «{project.name}». "
        + (
            f"{'A anotação' if lines == 1 else f'As {lines} anotações'} até agora "
            f"{'fica' if lines == 1 else 'ficam'} no cartão aqui em cima. "
            if lines
            else ""
        )
        + "Pode me pedir aqui o que quiser cotar, acompanhar ou anotar."
    )
    session.add(
        Message(conversation_id=found.id, role="assistant", content=opening, origin="project")
    )
    session.flush()
    return found


def log_in_chat(session: Session, owner: User, project: Project, text: str) -> None:
    """What it did to the project from elsewhere, said in the project's own chat, so the chat is
    the project's record (the notes card shows the same)."""
    chat = chat_for(session, owner, project)
    session.add(Message(conversation_id=chat.id, role="assistant", content=text, origin="project"))
    session.flush()
