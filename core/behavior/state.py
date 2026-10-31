"""Adaptive communication state, per interlocutor (master prompt §8 and §8.2).

Versioned, append-only, attributable and reversible:
- a new version is derived by deterministic rules from repeated feedback (never from a single
  event) and active lessons, and records exactly which evidence caused it;
- reverting creates a new version equal to an earlier one; history is never rewritten;
- the state only adjusts communication parameters. It is not a persona, carries no traits like
  "funny" or "serious", and never touches the voice timbre.
"""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.behavior.metrics import measure
from infrastructure.database.audit import record_audit
from infrastructure.database.models import (
    BehaviorObservation,
    BehaviorStateVersion,
    Lesson,
    Message,
    MessageFeedback,
)

RULES_VERSION = "2026-10-31.1"
WINDOW_DAYS = 30
MIN_REPEATS = 3  # one complaint is an event, not a pattern

# Neutral baseline: no adjustment at all, i.e. the base model's own default behavior.
BASELINE: dict[str, Any] = {"length": "default", "cite_sources": False, "fewer_questions": False}

ALLOWED_TAGS = frozenset(
    {"muito longo", "muito curto", "faltou fonte", "perguntas demais", "útil", "incorreto"}
)


def current(session: Session, owner_id: uuid.UUID) -> BehaviorStateVersion | None:
    return session.scalar(
        select(BehaviorStateVersion)
        .where(BehaviorStateVersion.owner_user_id == owner_id)
        .order_by(BehaviorStateVersion.version.desc())
        .limit(1)
    )


def current_params(session: Session, owner_id: uuid.UUID) -> tuple[int, dict[str, Any]]:
    state = current(session, owner_id)
    return (state.version, state.params) if state else (0, dict(BASELINE))


def _append(
    session: Session,
    owner_id: uuid.UUID,
    params: dict[str, Any],
    *,
    cause: str,
    evidence: dict[str, Any],
    summary: str,
) -> BehaviorStateVersion:
    last = session.scalar(
        select(func.max(BehaviorStateVersion.version)).where(
            BehaviorStateVersion.owner_user_id == owner_id
        )
    )
    version = BehaviorStateVersion(
        owner_user_id=owner_id,
        version=(last or 0) + 1,
        params=params,
        rules_version=RULES_VERSION,
        cause=cause,
        evidence=evidence,
        summary=summary,
    )
    session.add(version)
    session.flush()
    return version


def derive(tag_counts: Counter, active_lessons: list[Lesson]) -> tuple[dict[str, Any], list[str]]:
    """Pure rules: same evidence, same parameters. Returns params and human-readable reasons."""
    params = dict(BASELINE)
    reasons: list[str] = []
    long_, short = tag_counts["muito longo"], tag_counts["muito curto"]
    if long_ >= MIN_REPEATS and long_ > short:
        params["length"] = "shorter"
        reasons.append(f"{long_}x 'muito longo'")
    elif short >= MIN_REPEATS and short > long_:
        params["length"] = "longer"
        reasons.append(f"{short}x 'muito curto'")
    if tag_counts["faltou fonte"] >= MIN_REPEATS:
        params["cite_sources"] = True
        reasons.append(f"{tag_counts['faltou fonte']}x 'faltou fonte'")
    if tag_counts["perguntas demais"] >= MIN_REPEATS:
        params["fewer_questions"] = True
        reasons.append(f"{tag_counts['perguntas demais']}x 'perguntas demais'")
    for lesson in active_lessons:
        if lesson.scope == "style" and lesson.lesson:
            params.setdefault("lessons", []).append(lesson.lesson[:200])
            reasons.append(f"lição ativa {lesson.id}")
    return params, reasons


def recompute(session: Session, owner_id: uuid.UUID) -> BehaviorStateVersion | None:
    """Creates a new version only if the evidence now implies different parameters."""
    since = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)
    feedback = list(
        session.scalars(
            select(MessageFeedback).where(
                MessageFeedback.owner_user_id == owner_id, MessageFeedback.created_at >= since
            )
        )
    )
    tags = Counter(tag for f in feedback for tag in f.tags)
    lessons = list(
        session.scalars(
            select(Lesson).where(Lesson.owner_user_id == owner_id, Lesson.status == "ACTIVE")
        )
    )
    params, reasons = derive(tags, lessons)
    _, now_params = current_params(session, owner_id)
    if params == now_params:
        return None
    version = _append(
        session,
        owner_id,
        params,
        cause="feedback" if not lessons else "lesson",
        evidence={
            "feedback_ids": [str(f.id) for f in feedback if f.tags],
            "lesson_ids": [str(lesson.id) for lesson in lessons],
            "tag_counts": dict(tags),
        },
        summary="; ".join(reasons) or "evidência não sustenta mais ajustes: volta ao padrão",
    )
    record_audit(
        session,
        "behavior.adapt",
        "success",
        actor_user_id=owner_id,
        details={"version": version.version},
    )
    return version


def revert(session: Session, owner_id: uuid.UUID, to_version: int) -> BehaviorStateVersion:
    """Reversibility: the target version's parameters become a new, latest version."""
    if to_version == 0:
        target_params, label = dict(BASELINE), "padrão do modelo-base"
    else:
        target = session.scalar(
            select(BehaviorStateVersion).where(
                BehaviorStateVersion.owner_user_id == owner_id,
                BehaviorStateVersion.version == to_version,
            )
        )
        if target is None:
            raise ValueError(f"version {to_version} does not exist")
        target_params, label = dict(target.params), f"versão {to_version}"
    version = _append(
        session,
        owner_id,
        target_params,
        cause="revert",
        evidence={"reverted_to": to_version},
        summary=f"revertido para {label}",
    )
    record_audit(
        session,
        "behavior.revert",
        "success",
        actor_user_id=owner_id,
        details={"to_version": to_version, "new_version": version.version},
    )
    session.commit()
    return version


def prompt_lines(params: dict[str, Any]) -> list[str]:
    """Communication adjustments as plain instructions for the reply. Empty at baseline."""
    lines = []
    if params.get("length") == "shorter":
        lines.append("Prefira respostas curtas: no máximo 3 frases, sem introdução.")
    elif params.get("length") == "longer":
        lines.append("Prefira respostas mais completas, com explicação e exemplo quando útil.")
    if params.get("cite_sources"):
        lines.append("Ao afirmar fatos verificáveis, diga de onde vem a informação ou a incerteza.")
    if params.get("fewer_questions"):
        lines.append("Faça perguntas ao interlocutor só quando forem indispensáveis.")
    lines.extend(params.get("lessons", []))
    return lines


def observe(session: Session, message: Message, owner_id: uuid.UUID) -> BehaviorObservation:
    version, _ = current_params(session, owner_id)
    observation = BehaviorObservation(
        message_id=message.id,
        owner_user_id=owner_id,
        state_version=version,
        metrics=measure(message.content),
    )
    session.add(observation)
    session.flush()
    return observation
