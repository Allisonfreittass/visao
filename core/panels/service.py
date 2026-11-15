"""Live panels (docs/PAINEIS.md, ADR-0012): created when the owner approves the offer after a live
quote, checked once a day by the worker, edited from the conversation, shown on the home screen.

Creating one is approving its daily check (recorded in the audit log). The check respects the
global pause and the autonomy budget; without them the card keeps its last check, with its hour,
and never shows an old price as today's. A site that asks to prove you are human is reported on
the card and tried again the next day, never worked around.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.conversation.service import conversation_history
from core.initiatives import push
from core.initiatives.notify import deliver_after
from core.panels import urls
from core.panels.extract import RECHECK_PURPOSE, Page, extract
from core.panels.model import Item, Snapshot, Spec, goal_gap, total
from core.policies.autonomy import is_paused
from infrastructure.database.audit import record_audit
from infrastructure.database.models import (
    BrowseVisit,
    Conversation,
    Panel,
    PanelOffer,
    PanelSnapshot,
    PanelVersion,
    User,
)
from infrastructure.jobs import queue
from integrations.browser.base import Browser
from integrations.llm.base import LLMProvider

JOB_KIND = "panel_recheck"
CHECK_HOUR = 9
ROBOT = "verificação"


class LimitReached(Exception):
    """Already as many active panels as the configured limit."""


@dataclass(frozen=True)
class Limits:
    max_active: int = 3
    max_pages: int = 2
    alert_drop_percent: int = 10


def _zone(owner: User) -> ZoneInfo:
    try:
        return ZoneInfo(owner.timezone or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def local_today(owner: User, now: datetime) -> date:
    return now.astimezone(_zone(owner)).date()


def next_check(owner: User, now: datetime) -> datetime:
    """Tomorrow at 9h in the owner's own clock."""
    zone = _zone(owner)
    tomorrow = now.astimezone(zone).date() + timedelta(days=1)
    return datetime.combine(tomorrow, time(CHECK_HOUR), tzinfo=zone).astimezone(UTC)


def active_count(session: Session, owner_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Panel)
            .where(Panel.owner_user_id == owner_id, Panel.status.in_(("active", "error")))
        )
        or 0
    )


def _schedule(session: Session, panel: Panel, when: datetime) -> None:
    panel.next_check_at = when
    queue.enqueue(
        session,
        kind=JOB_KIND,
        owner_user_id=panel.owner_user_id,
        payload={"panel_id": str(panel.id)},
        idempotency_key=f"panel-recheck:{panel.id}:{when:%Y-%m-%dT%H}",
        reason="Conferir o painel do Início uma vez por dia",
        run_after=when,
        max_attempts=1,
    )


def _pages(rows: list[BrowseVisit]) -> list[Page]:
    return [
        Page(visit_id=r.id, url=r.url, title=r.title, text=r.text, read_at=r.created_at)
        for r in rows
        if r.ok
    ]


def _save_snapshot(session: Session, panel: Panel, snapshot: Snapshot, spec: Spec) -> None:
    value = total(snapshot, spec)
    panel.snapshot = snapshot.model_dump(mode="json")
    panel.checked_at = snapshot.checked_at
    session.add(
        PanelSnapshot(
            panel_id=panel.id,
            snapshot=panel.snapshot,
            total=value,
            checked_at=snapshot.checked_at,
        )
    )


def create_from_offer(
    session: Session,
    *,
    offer: PanelOffer,
    owner: User,
    conversation: Conversation,
    provider: LLMProvider,
    limits: Limits,
    via: str,
    now: datetime | None = None,
) -> Panel:
    """The panel from the same pages the quote read. Raises LimitReached."""
    now = now or datetime.now(UTC)
    if active_count(session, owner.id) >= limits.max_active:
        raise LimitReached()
    ids = [uuid.UUID(v) for v in offer.visit_ids]
    rows = list(session.scalars(select(BrowseVisit).where(BrowseVisit.id.in_(ids)))) if ids else []
    pages = _pages(rows)
    talk = "\n".join(
        f"{m.role}: {m.content[:600]}" for m in conversation_history(session, conversation)[-8:]
    )
    found = extract(
        session,
        provider,
        pages,
        today=local_today(owner, now),
        conversation=talk,
        conversation_id=conversation.id,
    )
    spec = (found.spec if found and found.spec else None) or Spec(destination=offer.title)
    spec = spec.model_copy(update={"goal": offer.goal_amount, "currency": offer.currency})
    panel = Panel(
        owner_user_id=owner.id,
        conversation_id=conversation.id,
        project_id=conversation.project_id,
        offer_id=offer.id,
        title=offer.title,
        spec=spec.model_dump(mode="json"),
        status="active",
        check_note="" if found else "não deu para ler os preços agora; confiro amanhã",
    )
    session.add(panel)
    session.flush()
    if found is not None:
        read = min((p.read_at for p in pages), default=now)
        _save_snapshot(session, panel, Snapshot(items=found.items, checked_at=read), spec)
    offer.status, offer.decided_at = "accepted", now
    record_audit(
        session,
        "panel.create",
        "success",
        actor_user_id=owner.id,
        details={"via": via, "panel_id": str(panel.id), "recurring_check": "daily"},
    )
    _schedule(session, panel, next_check(owner, now))
    session.commit()
    return panel


def spec_of(panel: Panel) -> Spec:
    return Spec(**panel.spec)


def snapshot_of(panel: Panel) -> Snapshot | None:
    return Snapshot(**panel.snapshot) if panel.snapshot else None


def _drop_alert(
    before: Decimal | None, after: Decimal | None, spec: Spec, limits: Limits, lost: list[str]
) -> str | None:
    """Only what changes a decision: below the goal now, a big drop, or something gone."""
    if lost:
        return f"{', '.join(lost)} sumiu da cotação"
    if before is None or after is None:
        return None
    if spec.goal is not None and after <= spec.goal < before:
        return f"ficou abaixo da meta: {money(after)}"
    if before > 0 and (before - after) / before * 100 >= limits.alert_drop_percent:
        return f"caiu de {money(before)} para {money(after)}"
    return None


def money(value: Decimal) -> str:
    whole = f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"
    return "R$ " + whole.replace(",", "X").replace(".", ",").replace("X", ".")


def _alert(session: Session, panel: Panel, owner: User, text: str, now: datetime) -> bool:
    if panel.last_alert_at and local_today(owner, panel.last_alert_at) == local_today(owner, now):
        return False  # one a day per panel at most
    if deliver_after(owner, now) > now:
        return False  # quiet hours
    push.send_to_owner(
        session,
        owner.id,
        title=panel.title,
        body=text[:180],
        url="/?inicio=1",
        tag=f"visao-panel-{panel.id}",
        now=now,
    )
    panel.last_alert_at = now
    return True


def recheck(
    session: Session,
    panel: Panel,
    *,
    owner: User,
    browser: Browser | None,
    provider: LLMProvider | None,
    limits: Limits,
    has_room: Callable[[], bool],
    now: datetime | None = None,
    reschedule: bool = True,
) -> str:
    """One check. Returns what happened (for the job result and the tests)."""
    now = now or datetime.now(UTC)
    if panel.status not in ("active", "error"):
        return "not_active"
    spec = spec_of(panel)
    if spec.ended(local_today(owner, now)):
        panel.status, panel.next_check_at = "expired", None
        session.commit()
        return "expired"

    def later(note: str, outcome: str) -> str:
        panel.check_note = note
        if reschedule:
            _schedule(session, panel, next_check(owner, now))
        session.commit()
        return outcome

    if is_paused(session):
        return later("não conferido hoje: a autonomia está pausada", "paused")
    if browser is None or provider is None:
        return later("não conferido hoje: o navegador não está ligado", "no_browser")
    if not has_room():
        return later("não conferido hoje: o orçamento do dia acabou", "no_budget")
    addresses = urls.for_spec(spec, limits.max_pages)
    if not addresses:
        return later("faltam as datas ou a origem para conferir", "incomplete")
    visits = browser.visit(addresses)
    rows = []
    for visit in visits:
        row = BrowseVisit(
            id=uuid.uuid4(),
            owner_user_id=owner.id,
            conversation_id=panel.conversation_id,
            url=visit.final_url or visit.url,
            title=visit.title[:200],
            ok=visit.ok,
            text=visit.text,
            failure=visit.failure[:200],
        )
        session.add(row)
        rows.append(row)
    session.flush()
    pages = _pages(rows)
    if not pages:
        robot = any(ROBOT in v.failure or "robô" in v.failure for v in visits)
        reason = "o site pediu verificação de robô" if robot else "o site não abriu"
        return later(f"não consegui conferir hoje: {reason}; tento amanhã", "failed")
    found = extract(
        session,
        provider,
        pages,
        today=local_today(owner, now),
        spec=spec,
        conversation_id=panel.conversation_id,
        purpose=RECHECK_PURPOSE,
    )
    if found is None:
        return later("não conferido hoje: não deu para ler os preços", "no_extract")
    before = snapshot_of(panel)
    before_total = total(before, spec) if before else None
    snapshot = Snapshot(items=found.items, checked_at=min(p.read_at for p in pages))
    after_total = total(snapshot, spec)
    lost = sorted(
        {_KINDS[i.kind] for i in (before.items if before else [])}
        - {_KINDS[i.kind] for i in found.items}
    )
    _save_snapshot(session, panel, snapshot, spec)
    panel.status = "active"
    panel.check_note = "" if after_total is not None else "alguns preços a confirmar"
    change = _drop_alert(before_total, after_total, spec, limits, lost)
    alerted = _alert(session, panel, owner, change, now) if change else False
    return later(panel.check_note, "alerted" if alerted else "checked")


_KINDS = {"flight": "o voo", "hotel": "a hospedagem"}


def card(session: Session, panel: Panel, owner: User, now: datetime | None = None) -> dict:
    """What the home screen shows, computed here: the total, the distance to the goal, the
    change since the check before, and whether the last check is from today."""
    now = now or datetime.now(UTC)
    spec = spec_of(panel)
    snapshot = snapshot_of(panel)
    value = total(snapshot, spec) if snapshot else None
    previous = session.scalars(
        select(PanelSnapshot.total)
        .where(PanelSnapshot.panel_id == panel.id)
        .order_by(PanelSnapshot.checked_at.desc())
        .offset(1)
        .limit(1)
    ).first()
    checked_today = panel.checked_at is not None and local_today(
        owner, panel.checked_at
    ) == local_today(owner, now)
    items: list[Item] = snapshot.items if snapshot else []
    return {
        "id": panel.id,
        "kind": panel.kind,
        "title": panel.title,
        "status": panel.status,
        "spec": spec.model_dump(mode="json"),
        "total": value,
        "goal": spec.goal,
        "goal_gap": goal_gap(value, spec),
        "change": (value - previous) if value is not None and previous is not None else None,
        "items": [{**i.model_dump(mode="json"), "cost": i.cost(spec.travelers)} for i in items],
        "checked_at": panel.checked_at,
        "checked_today": checked_today,
        "next_check_at": panel.next_check_at,
        "note": panel.check_note,
        "conversation_id": panel.conversation_id,
        "created_at": panel.created_at,
    }


def history(session: Session, panel: Panel, limit: int = 30) -> list[dict]:
    return [
        {"total": s.total, "checked_at": s.checked_at}
        for s in session.scalars(
            select(PanelSnapshot)
            .where(PanelSnapshot.panel_id == panel.id)
            .order_by(PanelSnapshot.checked_at.desc())
            .limit(limit)
        )
    ]


def edit(
    session: Session, panel: Panel, *, changes: dict, title: str | None, reason: str
) -> list[str]:
    """Applies a validated change to the same panel, keeping the version before. Returns what
    changed, in the owner's words, for the reply."""
    old = spec_of(panel)
    merged = Spec(**{**old.model_dump(), **changes})
    said: list[str] = []
    labels = {
        "goal": "a meta",
        "hotel_area": "o bairro do hotel",
        "depart": "a ida",
        "back": "a volta",
        "travelers": "o número de pessoas",
        "preferences": "as preferências",
        "origin": "a origem",
        "destination": "o destino",
        "include": "o que entra na cotação",
    }
    for key, label in labels.items():
        if getattr(merged, key) != getattr(old, key):
            said.append(label)
    new_title = (title or "").strip()[:60]
    if new_title and new_title != panel.title:
        said.append("o título")
    if not said:
        return []
    session.add(
        PanelVersion(
            panel_id=panel.id,
            version=panel.version,
            title=panel.title,
            spec=panel.spec,
            reason=reason[:300],
        )
    )
    panel.spec = merged.model_dump(mode="json")
    if new_title:
        panel.title = new_title
    panel.version += 1
    panel.updated_at = datetime.now(UTC)
    session.commit()
    return said


SEARCH_FIELDS = {
    "o bairro do hotel",
    "a ida",
    "a volta",
    "o número de pessoas",
    "a origem",
    "o destino",
    "as preferências",
    "o que entra na cotação",
}
