"""The installed skills: read from `library/<id>/SKILL.md`, switched on and off by the owner, and
handed to a reply when the person's message asks for one (docs/HABILIDADES.md).

A skill is text only: a way of working that goes into the reply's context. Nothing in a skill
runs, and nothing is downloaded at run time: each one was read, adapted and committed, with its
origin and license in the frontmatter. The truth rules, the voice and the approvals stay above it.

Which skill fits is decided in code, by the phrases in `triggers`, never by the model. At most one
goes into a reply. When the message itself matches none, the person's last few messages in the
same conversation are tried, so a skill that works over several turns (writing a document section
by section) does not drop out when the person answers "1: sim, 3: não".
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from core.memory.text import fold
from infrastructure.database.audit import record_audit
from infrastructure.database.models import SystemFlag

LIBRARY = Path(__file__).resolve().parent / "library"
FLAG = "skills"
# A skill body longer than this is cut: the reply has other context to carry.
BODY_CHARS = 7000
REQUIRED = ("name", "description", "triggers", "source", "source_url", "license", "installed_on")
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    triggers: tuple[str, ...]
    source: str
    source_url: str
    license: str
    installed_on: date
    body: str


class SkillFileError(ValueError):
    pass


def parse(skill_id: str, text: str) -> Skill:
    """A SKILL.md: `key: value` lines between `---` fences, then the body. No YAML: the keys are
    fixed and every value is one line."""
    if not _ID.match(skill_id):
        raise SkillFileError(f"{skill_id}: id inválido")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise SkillFileError(f"{skill_id}: falta o cabeçalho entre ---")
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        key, sep, value = line.partition(":")
        if not sep or not value.strip():
            raise SkillFileError(f"{skill_id}: linha de cabeçalho inválida: {line!r}")
        meta[key.strip()] = value.strip()
    missing = [k for k in REQUIRED if k not in meta]
    if missing:
        raise SkillFileError(f"{skill_id}: faltam {', '.join(missing)}")
    triggers = tuple(t for t in (fold(p.strip()) for p in meta["triggers"].split(",")) if t)
    body = parts[2].strip()
    if not triggers or not body:
        raise SkillFileError(f"{skill_id}: sem gatilhos ou sem texto")
    return Skill(
        id=skill_id,
        name=meta["name"],
        description=meta["description"],
        triggers=triggers,
        source=meta["source"],
        source_url=meta["source_url"],
        license=meta["license"],
        installed_on=date.fromisoformat(meta["installed_on"]),
        body=body,
    )


@lru_cache(maxsize=1)
def installed() -> tuple[Skill, ...]:
    """Every skill in the library, by name. Read once per process."""
    skills = [
        parse(path.parent.name, path.read_text(encoding="utf-8"))
        for path in sorted(LIBRARY.glob("*/SKILL.md"))
    ]
    return tuple(sorted(skills, key=lambda s: fold(s.name)))


def by_id(skill_id: str) -> Skill | None:
    return next((s for s in installed() if s.id == skill_id), None)


def switched_off(session: Session) -> set[str]:
    flag = session.get(SystemFlag, FLAG)
    off = (flag.value or {}).get("off") if flag else None
    return {s for s in off if isinstance(s, str)} if isinstance(off, list) else set()


def enabled(session: Session) -> list[Skill]:
    off = switched_off(session)
    return [s for s in installed() if s.id not in off]


def set_enabled(
    session: Session, skill: Skill, on: bool, *, actor_user_id: uuid.UUID | None
) -> None:
    """Installed skills start on; switching one off is remembered by id."""
    off = switched_off(session)
    off = off - {skill.id} if on else off | {skill.id}
    value = {"off": sorted(off)}
    flag = session.get(SystemFlag, FLAG)
    if flag is None:
        session.add(SystemFlag(name=FLAG, value=value))
    else:
        flag.value = value
        flag.updated_at = datetime.now(UTC)
    record_audit(
        session,
        "skill.toggle",
        "success",
        actor_user_id=actor_user_id,
        details={"skill": skill.id, "enabled": on},
    )


def _matches(phrase: str, folded: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded) is not None


def _score(skill: Skill, folded: str) -> tuple[int, int]:
    hits = [t for t in skill.triggers if _matches(t, folded)]
    if _matches(fold(skill.name), folded):
        hits.append(fold(skill.name))
    # More phrases first; on a tie, the longer ones ("design doc" over "design").
    return len(hits), sum(len(h) for h in hits)


def choose(skills: Sequence[Skill], text: str, earlier: Sequence[str] = ()) -> Skill | None:
    """The one skill this message asks for, or None. `earlier` is the person's previous messages
    in the conversation, newest first, tried only when the message itself matches nothing."""
    for candidate in [text, *earlier]:
        folded = fold(candidate)
        scored = [(_score(s, folded), s) for s in skills]
        scored = [(score, s) for score, s in scored if score[0] > 0]
        if scored:
            return max(scored, key=lambda pair: pair[0])[1]
    return None


def context_block(skill: Skill) -> str:
    body = skill.body
    if len(body) > BODY_CHARS:
        body = body[:BODY_CHARS].rsplit("\n", 1)[0] + "\n[…]"
    return (
        f'Habilidade ligada pelo interlocutor em Habilidades: "{skill.name}" '
        f"(de {skill.source}). Use este jeito de trabalhar se servir ao que ele pediu agora; se "
        "não servir, ignore. As regras de verdade, a sua voz e as aprovações continuam acima "
        "dela. Não cite a habilidade pelo nome a menos que ele pergunte.\n\n"
        f"{body}"
    )
