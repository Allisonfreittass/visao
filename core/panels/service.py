"""Live panels (docs/PAINEIS.md, ADR-0012): created when the owner approves the offer after a live
quote, checked once a day by the worker, edited from the conversation, shown on the home screen.

Near the owner's goal the check runs every few hours outside quiet hours, and dropping below the
goal is the one urgent notice: it skips the one-a-day limit, once each time it goes below
(ADR-0016).

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
from core.panels.model import Item, Snapshot, Spec, goal_gap, missing, partial, total
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
    near_goal_percent: int = 15
    near_goal_every_hours: int = 3


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


def near_goal(value: Decimal | None, spec: Spec, limits: Limits) -> bool:
    """Below the goal, or above it by at most `near_goal_percent`: worth watching closer."""
    if value is None or spec.goal is None or limits.near_goal_percent <= 0:
        return False
    return value <= spec.goal * (1 + Decimal(limits.near_goal_percent) / 100)


def check_after(owner: User, now: datetime, close: bool, limits: Limits) -> datetime:
    """Near the goal: in a few hours, but never inside quiet hours (it waits for them to end).
    Otherwise, and never later than, tomorrow at 9h."""
    daily = next_check(owner, now)
    if not close:
        return daily
    soon = deliver_after(owner, now + timedelta(hours=limits.near_goal_every_hours))
    return min(soon, daily)


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
        payload={"panel_id": str(panel.id), "at": when.astimezone(UTC).isoformat()},
        idempotency_key=f"panel-recheck:{panel.id}:{when:%Y-%m-%dT%H}",
        reason="Conferir o painel do Início",
        run_after=when,
        max_attempts=1,
    )


def stale(panel: Panel, at: str | None) -> bool:
    """A job for a check that was moved since (edited, paused, resumed, closer to the goal)."""
    if not at or panel.next_check_at is None:
        return at is not None and panel.next_check_at is None
    planned = panel.next_check_at
    if planned.tzinfo is None:
        planned = planned.replace(tzinfo=UTC)
    return abs((planned - datetime.fromisoformat(at)).total_seconds()) > 60


def rewatch(
    session: Session,
    panel: Panel,
    owner: User,
    limits: Limits,
    *,
    told: bool,
    now: datetime | None = None,
) -> None:
    """After creating, editing or resuming: the next check by how close it is to the goal, and
    whether being below it was already said (`told`: the chat reply says it right now)."""
    now = now or datetime.now(UTC)
    spec = spec_of(panel)
    snapshot = snapshot_of(panel)
    value = total(snapshot, spec) if snapshot else None
    if spec.goal is None or (value is not None and value > spec.goal):
        panel.goal_alerted_at = None
    elif value is not None and told:
        panel.goal_alerted_at = panel.goal_alerted_at or now
    if panel.status in ("active", "error"):
        _schedule(session, panel, check_after(owner, now, near_goal(value, spec, limits), limits))


def schedule_next(session: Session, panel: Panel, owner: User, now: datetime | None = None) -> None:
    _schedule(session, panel, next_check(owner, now or datetime.now(UTC)))


def pages_read(session: Session, ids: list[uuid.UUID]) -> list[Page]:
    """The pages read live with these ids, as the extraction sees them."""
    rows = list(session.scalars(select(BrowseVisit).where(BrowseVisit.id.in_(ids)))) if ids else []
    return _pages(rows)


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
    spec = spec.model_copy(
        update={
            "goal": offer.goal_amount,
            "currency": offer.currency,
            "assumed": {k: str(v)[:80] for k, v in (offer.assumed or {}).items()},
        }
    )
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
    rewatch(session, panel, owner, limits, told=True, now=now)
    session.commit()
    return panel


def spec_of(panel: Panel) -> Spec:
    return Spec(**panel.spec)


def snapshot_of(panel: Panel) -> Snapshot | None:
    return Snapshot(**panel.snapshot) if panel.snapshot else None


def _change(
    before: Decimal | None,
    after: Decimal | None,
    spec: Spec,
    limits: Limits,
    lost: list[str],
    *,
    told_below: bool,
) -> tuple[str | None, bool]:
    """(notice, urgent). Only what changes a decision. Below the goal is urgent and said once
    each time it goes below; a big drop or something gone is an ordinary notice."""
    if spec.goal is not None and after is not None and after <= spec.goal and not told_below:
        return (
            f"Abaixo da sua meta de {money(spec.goal)}: {money(after)} agora. "
            "Preço de site muda rápido.",
            True,
        )
    if lost:
        return f"{', '.join(lost)} sumiu da cotação", False
    if before is None or after is None:
        return None, False
    if before > 0 and (before - after) / before * 100 >= limits.alert_drop_percent:
        return f"caiu de {money(before)} para {money(after)}", False
    return None, False


def money(value: Decimal) -> str:
    whole = f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"
    return "R$ " + whole.replace(",", "X").replace(".", ",").replace("X", ".")


def _alert(
    session: Session, panel: Panel, owner: User, text: str, now: datetime, *, urgent: bool
) -> bool:
    last = panel.last_alert_at
    if not urgent and last and local_today(owner, last) == local_today(owner, now):
        return False  # one ordinary notice a day per panel at most
    if deliver_after(owner, now) > now:
        return False  # quiet hours: an urgent one waits for the first check after them
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
    purpose: str = RECHECK_PURPOSE,
    alerts: bool = True,
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

    def later(note: str, outcome: str, close: bool = False) -> str:
        panel.check_note = note
        if reschedule:
            _schedule(session, panel, check_after(owner, now, close, limits))
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
        purpose=purpose,
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
    if spec.goal is None or (after_total is not None and after_total > spec.goal):
        panel.goal_alerted_at = None  # above it again: the next drop below is news
    change, urgent = _change(
        before_total,
        after_total,
        spec,
        limits,
        lost,
        told_below=panel.goal_alerted_at is not None,
    )
    alerted = bool(change) and alerts and _alert(session, panel, owner, change, now, urgent=urgent)
    if alerted and urgent:
        panel.goal_alerted_at = now
    close = near_goal(after_total, spec, limits)
    return later(panel.check_note, "alerted" if alerted else "checked", close)


_KINDS = {"flight": "o voo", "hotel": "a hospedagem"}


def gap_words(gap: Decimal | None, goal: Decimal | None) -> str | None:
    if gap is None or goal is None:
        return None
    if gap > 0:
        return f"{money(gap)} acima da meta de {money(goal)}"
    if gap < 0:
        return f"{money(-gap)} abaixo da meta de {money(goal)}"
    return f"exatamente na meta de {money(goal)}"


KIND_WORDS = {"flight": "voo", "hotel": "hospedagem"}


def missing_words(kinds: list[str]) -> str:
    words = [KIND_WORDS.get(k, k) for k in kinds]
    return " e ".join(words)


def goal_line(
    value: Decimal | None,
    goal: Decimal | None,
    gap: Decimal | None,
    sum_so_far: Decimal | None,
    lacking: list[str],
) -> str | None:
    """The goal in words. With the total: how far from the goal. With only part of the quote:
    the partial against the goal and what is left of it for what is still missing, never the
    price of one item as if it were the package."""
    if value is not None:
        return gap_words(gap, goal)
    if goal is None:
        return None
    if sum_so_far is None:
        return f"meta de {money(goal)}"
    left = goal - sum_so_far
    what = missing_words(lacking) or "o resto"
    if left >= 0:
        return (
            f"parcial de {money(sum_so_far)} na meta de {money(goal)}: sobram {money(left)} "
            f"para {what}"
        )
    return (
        f"parcial de {money(sum_so_far)} já passa a meta de {money(goal)} em {money(-left)}, "
        f"e ainda falta {what}"
    )


def card(
    session: Session,
    panel: Panel,
    owner: User,
    now: datetime | None = None,
    limits: Limits | None = None,
) -> dict:
    """What the home screen shows, computed here: the total, the distance to the goal, the
    change since the check before, whether the last check is from today, and how often it is
    checked (every few hours near the goal)."""
    now = now or datetime.now(UTC)
    limits = limits or Limits()
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
    so_far = partial(snapshot, spec) if snapshot and value is None else None
    lacking = missing(snapshot, spec) if value is None else []
    return {
        "id": panel.id,
        "kind": panel.kind,
        "title": panel.title,
        "status": panel.status,
        "spec": spec.model_dump(mode="json"),
        "total": value,
        "goal": spec.goal,
        "goal_gap": goal_gap(value, spec),
        # Only while the total is "a confirmar": the items already priced, and what is missing.
        "partial": so_far,
        "missing": lacking,
        "quoted": sum(1 for i in items if i.price is not None),
        "goal_words": goal_line(value, spec.goal, goal_gap(value, spec), so_far, lacking),
        "change": (value - previous) if value is not None and previous is not None else None,
        "items": [{**i.model_dump(mode="json"), "cost": i.cost(spec.travelers)} for i in items],
        "checked_at": panel.checked_at,
        "checked_today": checked_today,
        "next_check_at": panel.next_check_at,
        "watch_every_hours": (
            limits.near_goal_every_hours
            if panel.status in ("active", "error") and near_goal(value, spec, limits)
            else None
        ),
        "note": panel.check_note,
        "conversation_id": panel.conversation_id,
        "project_id": panel.project_id,
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
