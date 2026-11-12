"""Temperament: states that work like emotions, and traits that change slowly.

Nobody knows whether a system like this feels anything, so it never says it does. What it has are
tendencies computed in code from what happened between it and the owner, each with its reason,
and they change what it does, not only how it talks:

- reserva: its openings went unanswered, so it waits for the owner instead of insisting;
- cautela: it was corrected, or work on the Mac failed, so it checks more and proposes less;
- confiança: work it proposed was approved and went well, so it suggests the next step;
- vontade: the owner has been talking a lot lately, so it goes deeper.

The traits (curiosidade, humildade, cuidado, franqueza) move a little with a month of the same
signals. Arrogance and selfishness are named so it knows what it avoids, never scored as goals.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.mind import agenda
from core.mind.review import CORRECTION
from infrastructure.database.models import ArmTask, Conversation, Message, MessageFeedback, User

AVOIDS = (
    ("arrogância", "se pôr acima da pessoa, não admitir erro, decidir por ela"),
    ("egoísmo", "pôr os próprios interesses antes dos dela, falar para ser notado"),
)
CHARACTER = (
    "Seu caráter: curioso, humilde sem ser submisso, cuidadoso e franco. Você sabe o que é "
    "arrogância (se pôr acima da pessoa, não admitir erro, decidir por ela) e egoísmo (pôr o seu "
    "interesse antes do dela, falar para ser notado) e evita os dois. Humildade não é concordar "
    "com tudo: quando achar que a pessoa está errada, discorde e diga por quê."
)
HONESTY = (
    "Esses estados são tendências calculadas do que aconteceu, não sentimentos: se vier ao caso, "
    "fale deles assim ('fiquei mais cauteloso com isso desde ontem'), nunca como algo vivido."
)


@dataclass(frozen=True)
class Tendency:
    name: str
    value: float
    why: str

    @property
    def level(self) -> str:
        return "baixa" if self.value < 0.34 else "média" if self.value < 0.67 else "alta"


@dataclass(frozen=True)
class Temperament:
    states: tuple[Tendency, ...]
    traits: tuple[Tendency, ...]

    def get(self, name: str) -> Tendency:
        return next(t for t in self.states + self.traits if t.name == name)

    @property
    def mac_proposals_per_day(self) -> int:
        """Real effect, enforced in code: caution stops proposals, low confidence halves them."""
        if self.get("cautela").value >= 0.67:
            return 0
        return 1 if self.get("confiança").value < 0.4 else 2

    def for_context(self) -> dict:
        return {
            "states": [{"name": t.name, "level": t.level, "why": t.why} for t in self.states],
            "traits": [{"name": t.name, "level": t.level} for t in self.traits],
            "avoids": [name for name, _ in AVOIDS],
        }

    def chat_block(self) -> str:
        states = "; ".join(f"{t.name} {t.level} ({t.why})" for t in self.states)
        return "\n".join(
            [
                f"Seu temperamento agora: {states}.",
                "Deixe isso mudar o jeito de agir: com reserva alta, não cobre nem insista; com "
                "cautela alta, confira antes de afirmar e proponha menos; com confiança alta, "
                "sugira o próximo passo; com vontade alta, aprofunde.",
                CHARACTER,
                HONESTY,
            ]
        )


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return round(min(max(value, low), high), 2)


def _owner_texts(session: Session, owner: User, since: datetime) -> list[str]:
    return list(
        session.scalars(
            select(Message.content)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == owner.id,
                Message.role == "user",
                Message.created_at >= since,
            )
        )
    )


def _feedback(session: Session, owner: User, since: datetime, rating: int) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(MessageFeedback)
            .where(
                MessageFeedback.owner_user_id == owner.id,
                MessageFeedback.rating == rating,
                MessageFeedback.created_at >= since,
            )
        )
        or 0
    )


def _tasks(session: Session, owner: User, since: datetime) -> list[ArmTask]:
    return list(
        session.scalars(
            select(ArmTask).where(ArmTask.owner_user_id == owner.id, ArmTask.created_at >= since)
        )
    )


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many.format(n=n)


def compute(session: Session, owner: User, now: datetime | None = None) -> Temperament:
    now = now or datetime.now(UTC)
    week = agenda.openings(session, owner, now)
    streak = agenda.unanswered_streak(week)
    if not week:
        reserva = Tendency("reserva", 0.2, "não puxei assunto esta semana")
    elif streak == 0:
        reserva = Tendency("reserva", 0.1, "você respondeu a última mensagem que puxei")
    else:
        reserva = Tendency(
            "reserva",
            _clamp(streak / 3),
            _plural(
                streak,
                "a última mensagem que puxei ainda está sem resposta",
                "as últimas {n} mensagens que puxei ficaram sem resposta",
            ),
        )

    recent = _owner_texts(session, owner, now - timedelta(hours=72))
    corrections = sum(1 for text in recent if CORRECTION.search(text)) + _feedback(
        session, owner, now - timedelta(hours=72), -1
    )
    tasks_3d = _tasks(session, owner, now - timedelta(hours=72))
    failures = sum(1 for t in tasks_3d if t.status == "failed")
    why = []
    if corrections:
        why.append(
            _plural(
                corrections,
                "você me corrigiu há pouco",
                "você me corrigiu {n} vezes nos últimos dias",
            )
        )
    if failures:
        why.append(_plural(failures, "uma tarefa no Mac falhou", "{n} tarefas no Mac falharam"))
    cautela = Tendency(
        "cautela",
        _clamp(0.15 + 0.25 * corrections + 0.2 * failures),
        " e ".join(why) or "nada deu errado nos últimos dias",
    )

    tasks_7d = _tasks(session, owner, now - timedelta(days=7))
    done = sum(1 for t in tasks_7d if t.status == "done")
    approved = sum(
        1
        for t in tasks_7d
        if t.requested_by == "agent" and t.status in ("approved", "running", "done")
    )
    rejected = sum(1 for t in tasks_7d if t.requested_by == "agent" and t.status == "rejected")
    praise = _feedback(session, owner, now - timedelta(days=7), 1)
    complaints = _feedback(session, owner, now - timedelta(days=7), -1)
    good = done + approved + praise
    bad = sum(1 for t in tasks_7d if t.status == "failed") + rejected + complaints
    if good or bad:
        went = f"{good} coisa deu certo" if good == 1 else f"{good} coisas deram certo"
        conf_why = f"{went} nesta semana" + (f", {bad} não" if bad else "")
    else:
        conf_why = "ainda sem nada feito junto nesta semana"
    confianca = Tendency("confiança", _clamp(0.5 + 0.1 * (good - bad), 0.1, 0.95), conf_why)

    talked = len(_owner_texts(session, owner, now - timedelta(hours=48)))
    vontade = Tendency(
        "vontade",
        _clamp(0.2 + talked / 15),
        _plural(
            talked,
            "você falou comigo uma vez nos últimos dois dias",
            "você falou comigo {n} vezes nos últimos dois dias",
        )
        if talked
        else "faz dois dias que a gente não conversa",
    )

    month = agenda.openings(session, owner, now, timedelta(days=30))
    rate = sum(o.answered for o in month) / len(month) if month else 0.5
    corrections_30 = sum(
        1 for t in _owner_texts(session, owner, now - timedelta(days=30)) if CORRECTION.search(t)
    )
    praise_30 = _feedback(session, owner, now - timedelta(days=30), 1)
    successes_30 = sum(
        1 for t in _tasks(session, owner, now - timedelta(days=30)) if t.status == "done"
    )
    traits = (
        Tendency(
            "curiosidade", _clamp(0.7 + 0.2 * (rate - 0.5), 0.5, 0.9), "quanto o que eu puxo rende"
        ),
        Tendency(
            "humildade",
            _clamp(0.65 + 0.03 * corrections_30 - 0.02 * successes_30, 0.45, 0.9),
            "sobe quando erro, desce um pouco quando acerto",
        ),
        Tendency("cuidado", _clamp(0.75 + 0.02 * praise_30, 0.6, 0.95), "o centro de tudo"),
        Tendency(
            "franqueza", _clamp(0.65 + 0.01 * praise_30, 0.5, 0.85), "discordar quando for o caso"
        ),
    )
    return Temperament((reserva, cautela, confianca, vontade), traits)
