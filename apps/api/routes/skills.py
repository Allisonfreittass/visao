"""Habilidades: the installed skills and the owner's switch for each (core/skills/catalog.py)."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.api.deps import CurrentUser, DbSession
from core.skills import catalog

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillOut(BaseModel):
    id: str
    name: str
    description: str
    # "instalada": read, adapted and committed with the code. Skills he proposes come later.
    origin: str
    source: str
    source_url: str
    license: str
    installed_on: date
    enabled: bool


class SkillsOut(BaseModel):
    skills: list[SkillOut]


class SkillIn(BaseModel):
    enabled: bool


def _out(skill: catalog.Skill, off: set[str]) -> SkillOut:
    return SkillOut(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        origin="instalada",
        source=skill.source,
        source_url=skill.source_url,
        license=skill.license,
        installed_on=skill.installed_on,
        enabled=skill.id not in off,
    )


@router.get("")
def list_skills(db: DbSession, user: CurrentUser) -> SkillsOut:
    off = catalog.switched_off(db)
    return SkillsOut(skills=[_out(s, off) for s in catalog.installed()])


@router.put("/{skill_id}")
def switch_skill(skill_id: str, body: SkillIn, db: DbSession, user: CurrentUser) -> SkillOut:
    skill = catalog.by_id(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Habilidade não encontrada")
    catalog.set_enabled(db, skill, body.enabled, actor_user_id=user.id)
    db.commit()
    return _out(skill, catalog.switched_off(db))
