"""Where the owner leaves from, when they did not say (docs/decisions/0015).

A quote with a declared assumption beats a reply that stops to ask. The origin comes from where
the owner lives, found in their own words kept with consent (the profile notes and the curated
memory), never guessed by the model. The airports for each place come from this table, also
never from the model: the planner only picks the first one and says so.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.memory.text import fold
from core.mind import notes as mind_notes
from infrastructure.database.models import MemoryRecord, User


@dataclass(frozen=True)
class Home:
    # How the reply names it ("sul de Minas", "Belo Horizonte").
    label: str
    # Practical airports from there, the usual first (IATA codes).
    airports: tuple[str, ...]


# (label, places that belong to it, airports). Folded text (no accents, lower case).
_REGIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "sul de Minas",
        r"sul de minas|pouso alegre|varginha|pocos de caldas|lavras|tres coracoes|itajuba|"
        r"alfenas|sao lourenco|extrema|santa rita do sapucai|cambui|tres pontas|guaxupe|"
        r"caxambu|campanha|machado|boa esperanca|ouro fino|borda da mata",
        ("GRU", "VCP", "CNF"),
    ),
    ("Belo Horizonte", r"belo horizonte|\bbh\b|contagem|betim|nova lima", ("CNF", "PLU")),
    (
        "Campinas",
        r"campinas|jundiai|sumare|valinhos|vinhedo|indaiatuba|americana",
        ("VCP", "GRU"),
    ),
    (
        "São Paulo",
        r"sao paulo|\bsp\b|guarulhos|osasco|santo andre|sao bernardo|sao caetano",
        ("GRU", "CGH", "VCP"),
    ),
    ("Rio de Janeiro", r"rio de janeiro|niteroi", ("GIG", "SDU")),
    ("Curitiba", r"curitiba|sao jose dos pinhais", ("CWB",)),
    ("Porto Alegre", r"porto alegre|canoas", ("POA",)),
    ("Florianópolis", r"florianopolis|sao jose \(sc\)|palhoca", ("FLN",)),
    ("Brasília", r"brasilia|\bdf\b", ("BSB",)),
    ("Goiânia", r"goiania", ("GYN",)),
    ("Vitória", r"\bvitoria\b|vila velha", ("VIX",)),
    ("Salvador", r"salvador", ("SSA",)),
    ("Recife", r"recife|olinda", ("REC",)),
    ("Fortaleza", r"fortaleza", ("FOR",)),
    ("Belém", r"\bbelem\b", ("BEL",)),
    ("Manaus", r"manaus", ("MAO",)),
)
# Where someone lives, said in their own words: "moro em", "mora em", "sou de", "vivo em".
_LIVES = (
    r"\b(?:moro|mora|moramos|moram|vivo|vive|vivemos|resido|reside|"
    r"sou de|somos de|natural de)"
)
_NEAR = r"(?:\W+\w+){0,5}?\W+"
MEMORY_ROWS = 200


def _found(text: str) -> Home | None:
    folded = fold(text)
    for label, places, airports in _REGIONS:
        if re.search(rf"{_LIVES}{_NEAR}(?:{places})", folded):
            return Home(label, airports)
    return None


def home(session: Session, owner: User) -> Home | None:
    """Where the owner lives, from what they told and agreed to keep. None without consent or
    without a clear "moro em…": then the origin is asked, never guessed."""
    if not owner.memory_consent:
        return None
    profile, _ = mind_notes.for_prompt(session, owner)
    found = _found(profile) if profile else None
    if found is not None:
        return found
    rows = session.scalars(
        select(MemoryRecord.content)
        .where(
            MemoryRecord.owner_user_id == owner.id,
            or_(MemoryRecord.valid_until.is_(None), MemoryRecord.valid_until > datetime.now(UTC)),
        )
        .order_by(MemoryRecord.created_at.desc())
        .limit(MEMORY_ROWS)
    )
    for content in rows:
        found = _found(content)
        if found is not None:
            return found
    return None
