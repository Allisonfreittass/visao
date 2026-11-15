"""Up to 3 suggestions for the home screen when nothing waits and there are no panels yet
(docs/PAINEIS.md): taken in code from what is already in the owner's recent conversations and
projects, never from a model, and never about a sensitive subject (the same categories the memory
policy refuses: health, religion, sexuality, politics, personal finances, documents)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.browse import _TOPIC
from core.memory.text import fold
from infrastructure.database.models import Conversation, Project, User

MAX = 3
RECENT = timedelta(days=30)
_SENSITIVE = (
    "saude medic remedio doenc terapi psic hospital exame gravid cancer diagnost "
    "religi igreja deus sexual gay lesbica trans politic eleic partido voto "
    "divida salario emprestimo banco cartao fatura imposto cpf rg passaporte senha document"
).split()


def sensitive(text: str) -> bool:
    folded = fold(text)
    return any(word in folded for word in _SENSITIVE)


def suggestions(session: Session, owner: User, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    found: list[dict] = []
    seen: set[str] = set()
    titled = session.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == owner.id,
            Conversation.title.is_not(None),
            Conversation.created_at >= now - RECENT,
        )
        .order_by(Conversation.created_at.desc())
        .limit(20)
    )
    for conversation in titled:
        title = (conversation.title or "").strip()
        if not title or sensitive(title) or not _TOPIC.search(title) or fold(title) in seen:
            continue
        seen.add(fold(title))
        found.append(
            {
                "text": f"Acompanhar o preço: {title}",
                "draft": f"Quero acompanhar o preço de {title[0].lower()}{title[1:]}",
            }
        )
        if len(found) >= MAX:
            return found
    for project in session.scalars(
        select(Project).where(Project.owner_user_id == owner.id).order_by(Project.created_at.desc())
    ):
        if sensitive(project.name) or fold(project.name) in seen:
            continue
        seen.add(fold(project.name))
        found.append(
            {
                "text": f"Retomar o projeto {project.name}",
                "draft": f"Vamos retomar o projeto {project.name}: em que pé está?",
            }
        )
        if len(found) >= MAX:
            break
    return found
