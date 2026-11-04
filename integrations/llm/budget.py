"""Fail-closed admission for each provider attempt, with a persistent global ledger.

Uses the existing SystemFlag table, no schema migration. Independent short transactions:
never hold a database lock during model I/O. Unknown consumption is not refunded.
"""

import hashlib
import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from infrastructure.database.models import SystemFlag
from integrations.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse

LEDGER = "llm_budget_v1"
DIMENSIONS = {"input", "output", "cache", "audio", "tools", "routing", "platform"}


class FreeEndpointGrant(BaseModel):
    """Operator-reviewed evidence, never a grant supplied by a model or a page."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    provider: str
    endpoint: str
    model: str
    evidence_url: str
    verified_at: datetime
    expires_at: datetime
    prices: dict[str, Decimal]

    @model_validator(mode="after")
    def validate_evidence(self):
        for value in (self.endpoint, self.evidence_url):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("evidence and endpoint must be HTTPS URLs without secrets/query")
        if not self.provider or not self.model:
            raise ValueError("exact provider and model are required")
        if self.verified_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("evidence times must include timezone")
        if not timedelta(0) < self.expires_at - self.verified_at <= timedelta(days=7):
            raise ValueError("evidence validity must be positive and at most seven days")
        if set(self.prices) != DIMENSIONS or any(p != 0 for p in self.prices.values()):
            raise ValueError("all supported price dimensions must explicitly be zero")
        return self


@dataclass(frozen=True)
class BudgetLimits:
    calls_per_day: int = 30
    calls_per_hour: int = 10
    input_tokens_per_day: int = 60_000
    output_tokens_per_day: int = 15_000
    input_tokens_per_call: int = 32_768
    output_tokens_per_call: int = 4096
    concurrency: int = 1
    failure_threshold: int = 3
    cooldown_seconds: int = 900

    def __post_init__(self):
        if any(value < 1 for value in vars(self).values()):
            raise ValueError("all budget limits must be positive")


def _deny(reason: str) -> LLMError:
    return LLMError("budget_denied", reason)


class BudgetGuard:
    def __init__(
        self,
        factory: Callable[[], Session],
        grants: list[FreeEndpointGrant],
        limits: BudgetLimits | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        trust_zero_price: bool = False,
    ) -> None:
        # Local use: a configured zero price is taken at its word. A provider reporting any cost
        # still freezes the ledger in finish(), so this cannot turn into spending.
        self.trust_zero_price = trust_zero_price
        self.factory = factory
        # Deep copies prevent mutation of a caller's prices dict after validation.
        self.grants = tuple(FreeEndpointGrant.model_validate(g.model_dump()) for g in grants)
        self.limits = limits or BudgetLimits()
        self.clock = clock

    @contextmanager
    def _ledger(self) -> Iterator[dict[str, Any]]:
        with self.factory() as db:
            dialect = db.get_bind().dialect.name
            if dialect == "sqlite":
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
                insert = sqlite_insert
            elif dialect == "postgresql":
                insert = pg_insert
            else:
                raise _deny("unsupported admission ledger database")
            db.execute(insert(SystemFlag).values(name=LEDGER, value={}).on_conflict_do_nothing())
            flag = db.scalar(select(SystemFlag).where(SystemFlag.name == LEDGER).with_for_update())
            assert flag is not None
            state = dict(flag.value)
            yield state
            flag.value = state
            flag.updated_at = self.clock()
            db.commit()

    def _grant(self, provider: LLMProvider, endpoint: str, now: datetime) -> str:
        if provider.pricing.input_per_mtok != 0 or provider.pricing.output_per_mtok != 0:
            raise _deny("paid or unknown provider price")
        for grant in self.grants:
            if (
                grant.provider == provider.name
                and grant.endpoint == endpoint
                and grant.model == provider.model
                and grant.verified_at <= now < grant.expires_at
            ):
                return hashlib.sha256(
                    json.dumps([grant.provider, grant.endpoint, grant.model]).encode()
                ).hexdigest()
        if self.trust_zero_price:
            return hashlib.sha256(
                json.dumps([provider.name, endpoint, provider.model]).encode()
            ).hexdigest()
        raise _deny("no current zero-price evidence for this exact endpoint/model")

    def reserve(self, provider: LLMProvider, endpoint: str, messages, output: int) -> str:
        now = self.clock().astimezone(UTC)
        key = self._grant(provider, endpoint, now)
        # Conservative proxy, not a universal tokenizer guarantee; reconcile reported usage.
        input_tokens = (
            len(
                json.dumps(
                    [{"role": m.role, "content": m.content} for m in messages], ensure_ascii=False
                ).encode()
            )
            + 1024
        )
        if not 0 < output <= self.limits.output_tokens_per_call:
            raise _deny("output reservation exceeds per-call limit")
        if input_tokens > self.limits.input_tokens_per_call:
            raise _deny("input reservation exceeds per-call limit")
        reservation = uuid.uuid4().hex
        with self._ledger() as state:
            if state.get("frozen"):
                raise _deny("ledger frozen pending operator review")
            day, hour = now.date().isoformat(), now.strftime("%Y-%m-%dT%H")
            if state.get("day") != day:
                state.update(day=day, calls=0, input=0, output=0)
            if state.get("hour") != hour:
                state.update(hour=hour, hourly_calls=0)
            active = dict(state.get("active", {}))
            circuit = state.get("circuits", {}).get(key, {})
            if circuit.get("until", 0) > now.timestamp():
                raise _deny("provider circuit is cooling down")
            if circuit.get("probe"):
                raise _deny("provider circuit probe is already in flight")
            limits = self.limits
            if (
                len(active) >= limits.concurrency
                or state["calls"] >= limits.calls_per_day
                or state["hourly_calls"] >= limits.calls_per_hour
                or state["input"] + input_tokens > limits.input_tokens_per_day
                or state["output"] + output > limits.output_tokens_per_day
            ):
                raise _deny("reservation would exceed shared quota")
            state["calls"] += 1
            state["hourly_calls"] += 1
            state["input"] += input_tokens
            state["output"] += output
            if circuit.get("failures", 0) >= limits.failure_threshold:
                circuits = dict(state.get("circuits", {}))
                circuits[key] = {**circuit, "probe": reservation}
                state["circuits"] = circuits
            active[reservation] = {
                "key": key,
                "day": day,
                "input": input_tokens,
                "output": output,
                "state": "active",
                "created_at": now.isoformat(),
            }
            state["active"] = active
        return reservation

    def finish(self, reservation: str, response: LLMResponse | None, error: str | None) -> bool:
        now = self.clock().astimezone(UTC)
        violation = False
        with self._ledger() as state:
            active = dict(state.get("active", {}))
            item = active.get(reservation)
            if item is None:
                raise _deny("unknown reservation")
            circuits = dict(state.get("circuits", {}))
            circuit = dict(circuits.get(item["key"], {}))
            circuit.pop("probe", None)
            if response is not None:
                circuit = {"failures": 0, "until": 0}
                # Keep unused reservations charged; late/crashed/failed calls are not free retries.
                if (
                    response.cost_usd != 0
                    or response.input_tokens < 0
                    or response.output_tokens < 0
                    or response.input_tokens > item["input"]
                    or response.output_tokens > item["output"]
                ):
                    state["frozen"] = "provider exceeded admitted usage or zero-price contract"
                    violation = True
                if state.get("day") == item["day"]:
                    state["input"] += max(0, response.input_tokens - item["input"])
                    state["output"] += max(0, response.output_tokens - item["output"])
                del active[reservation]
            else:
                circuit["failures"] = circuit.get("failures", 0) + 1
                if circuit["failures"] >= self.limits.failure_threshold:
                    circuit["until"] = now.timestamp() + self.limits.cooldown_seconds
                if error in {"timeout", "network", "bad_response", "unknown"}:
                    active[reservation] = {**item, "state": "unknown", "error": error}
                else:
                    del active[reservation]
            circuits[item["key"]] = circuit
            state.update(active=active, circuits=circuits)
        return violation


class GuardedLLMProvider:
    def __init__(self, provider: LLMProvider, endpoint: str, guard: BudgetGuard):
        self._provider, self._endpoint, self._guard = provider, endpoint, guard
        self.name, self.model, self.pricing = provider.name, provider.model, provider.pricing

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        try:
            reservation = self._guard.reserve(
                self._provider, self._endpoint, messages, max_output_tokens
            )
        except LLMError:
            raise
        except Exception as exc:
            raise _deny("admission ledger unavailable") from exc
        try:
            response = self._provider.complete(messages, max_output_tokens=max_output_tokens)
        except BaseException as exc:
            self._settle(reservation, None, exc.kind if isinstance(exc, LLMError) else "unknown")
            raise
        if self._settle(reservation, response, None):
            raise _deny("provider violated admitted usage or zero-price contract")
        return response

    def _settle(self, reservation, response, error):
        try:
            return self._guard.finish(reservation, response, error)
        except Exception as exc:
            # Admission remains charged/active if reconciliation cannot be committed.
            raise _deny("admission ledger reconciliation failed") from exc
