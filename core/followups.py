""" "Me cobra", "me lembra de": the follow-up is recorded before the reply, with its day and hour.

25/11/2026, in the Jarvis test: "me cobra: eu disse que ia terminar o painel de preços essa
semana" got "Combinado, vou te cobrar no fim da semana", and nothing was recorded; the follow-up
depended on the mind happening to remember. Here code reads the request and its time, records an
intention (core/mind/intentions.py, woken by the worker at that hour), and the reply says the day
and hour that were actually recorded.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core.memory.text import fold
from core.mind import intentions
from infrastructure.database.models import Intention, User

# Matched on fold()ed text.
_ASKS = re.compile(
    r"\bme cobr[ae]\b|\bcobra (?:de )?mim\b|\bme lembr[ae] (?:de|que|amanha|hoje|na|no|daqui)"
    r"|\bme avis[ae] (?:amanha|hoje|na|no|daqui|semana)\b"
)
_WEEKDAYS = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}
_THIS_WEEK = re.compile(
    r"\b(?:essa|esta|nessa|nesta) semana\b|\bfim (?:da|de) semana\b|\bate sexta\b"
)
MORNING = time(9, 0)
EVENING = time(18, 0)
END_OF_WEEK = time(17, 0)


@dataclass(frozen=True)
class Recorded:
    intention: Intention | None
    when_words: str  # "sexta 28/11 às 17:00"
    about: str
    refused: str = ""  # why nothing was recorded


def asks(text: str) -> bool:
    return len(text) <= 1000 and bool(_ASKS.search(fold(text)))


def when(text: str, now: datetime, timezone: str) -> datetime:
    """The hour the request means, on the owner's clock. Without one: tomorrow morning."""
    zone = _zone(timezone)
    here = now.astimezone(zone)
    folded = fold(text)
    today = here.date()

    def at(day, hour: time) -> datetime:
        return datetime.combine(day, hour, tzinfo=zone)

    later = re.search(r"\bdaqui a (\d{1,3}) (minutos?|horas?|dias?)\b", folded)
    if later:
        n, unit = int(later.group(1)), later.group(2)
        step = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}
        return here + step[unit[0]]
    if re.search(r"\bhoje\b|\bmais tarde\b|\bfim do dia\b", folded):
        evening = at(today, EVENING)
        return evening if evening > here + timedelta(minutes=30) else here + timedelta(hours=2)
    if re.search(r"\bamanha\b", folded):
        return at(today + timedelta(days=1), MORNING)
    if re.search(r"\bsemana que vem\b|\bproxima semana\b", folded):
        return at(today + timedelta(days=7 - here.weekday()), MORNING)
    if re.search(
        r"\b(?:essa|esta|nessa|nesta) semana\b|\bfim (?:da|de) semana\b|\bate sexta\b", folded
    ):
        friday = at(today + timedelta(days=(4 - here.weekday()) % 7), END_OF_WEEK)
        return friday if friday > here + timedelta(hours=1) else here + timedelta(days=1)
    for name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b(?:na|no|ate|ate a|ate o)?\s*{name}(?:-feira)?\b", folded):
            ahead = (weekday - here.weekday()) % 7 or 7
            return at(today + timedelta(days=ahead), MORNING)
    return at(today + timedelta(days=1), MORNING)


def record(session: Session, owner: User, text: str, now: datetime) -> Recorded:
    moment = when(text, now, owner.timezone or "UTC")
    about = (
        "O dono pediu para ser cobrado/lembrado, com estas palavras: "
        f"“{' '.join(text.split())[:300]}”. Na hora, cobre direto e pergunte como ficou."
    )
    intention = intentions.plan(session, owner, about=about, when=moment, now=now)
    words = _words(intention.due_at if intention else moment, owner.timezone or "UTC")
    if intention is None:
        busy = len(intentions.pending(session, owner.id)) >= intentions.MAX_PENDING
        why = "já há retomadas demais marcadas" if busy else "já estava marcado ou a hora não vale"
        return Recorded(None, words, text, refused=why)
    return Recorded(intention, words, text)


def block(done: Recorded) -> str:
    if done.intention is None:
        return (
            f"A pessoa pediu para ser cobrada, e não deu para registrar agora ({done.refused}). "
            "Diga isso numa frase; não prometa cobrar."
        )
    return (
        "A cobrança foi registrada agora pelo sistema (vale como feito): você vai puxar o assunto "
        f"{done.when_words}, no relógio dele. Diga isso numa frase, com esse dia e essa hora, e, "
        "se fizer sentido, uma pergunta curta sobre como está o que ele quer terminar."
    )


def _words(moment: datetime, timezone: str) -> str:
    local = moment.astimezone(_zone(timezone))
    return f"{intentions.WEEKDAYS[local.weekday()]} {local:%d/%m} às {local:%H:%M}"


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")
