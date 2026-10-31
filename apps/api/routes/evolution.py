"""Code runner interface, authenticated separately from user login and cloud cron."""

import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from apps.api.deps import AppSettings, DbSession
from apps.api.llm import get_llm_provider
from core.autonomy.cycle import AutonomyBudget
from core.evolution import service
from core.policies.autonomy import is_paused


def code_access(
    settings: AppSettings, key: Annotated[str | None, Header(alias="X-Visao-Code-Key")] = None
):
    expected = settings.code_autonomy_key
    if not settings.code_autonomy_enabled or expected is None:
        raise HTTPException(404, "Não encontrado")
    if key is None or not secrets.compare_digest(key, expected.get_secret_value()):
        raise HTTPException(403, "Não autorizado")


router = APIRouter(
    prefix="/evolution", include_in_schema=False, dependencies=[Depends(code_access)]
)


class Source(BaseModel):
    content: str = Field(max_length=12_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProposalIn(BaseModel):
    base_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    files: dict[str, Source] = Field(max_length=2)


class ReportIn(BaseModel):
    id: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Literal["tested", "rejected", "published", "reverted"]
    commit: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    run_url: str | None = Field(
        default=None, pattern=(r"^https://github\.com/Allisonfreittass/visao/actions/runs/\d+$")
    )


@router.post("/propose")
def propose(body: ProposalIn, db: DbSession, settings: AppSettings):
    provider = get_llm_provider()
    if provider is None:
        raise HTTPException(503, "Provedor indisponível")
    budget = AutonomyBudget(
        llm_calls_per_day=settings.autonomy_llm_calls_per_day,
        tokens_per_day=settings.autonomy_tokens_per_day,
        max_actions_per_cycle=settings.autonomy_max_actions_per_cycle,
        max_seconds=settings.autonomy_max_seconds,
        research_per_day=settings.research_per_day,
        max_output_tokens=2048,
        daily_usd=settings.llm_daily_budget_usd,
    )
    try:
        return service.propose(
            db,
            provider=provider,
            budget=budget,
            base_sha=body.base_sha,
            files={p: s.model_dump() for p, s in body.files.items()},
        )
    except (ValueError, SyntaxError):
        raise HTTPException(422, "Código fora do escopo permitido") from None


@router.post("/report")
def report(body: ReportIn, db: DbSession):
    try:
        return service.report(db, body.id, body.status, body.commit, body.run_url)
    except ValueError:
        raise HTTPException(409, "Transição inválida") from None


@router.get("/permission")
def permission(db: DbSession):
    return {"enabled": not is_paused(db)}
