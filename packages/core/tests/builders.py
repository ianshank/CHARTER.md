"""Shared test builders for the engine test suite.

Constructing a valid `Charter`, ledger event, or `ResolvedEvent` by hand is
verbose enough (constraint text over the 24-character floor, tuple ratifiers,
provenance) that every engine test file would otherwise reinvent it slightly
differently. These builders are the one place that boilerplate lives, so a
model change (a new required field) is a one-file fix instead of a
grep-and-fix across a dozen test files.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import TypeAdapter

from charter_core.ids import LedgerPath
from charter_core.models.charter import Charter
from charter_core.models.events import LedgerEvent
from charter_core.models.state import ResolvedEvent
from charter_core.ports import Provenance

AT: datetime = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def T(n: int) -> datetime:  # noqa: N802 -- deliberately short; used at every call site
    """A timestamp ``n`` days after :data:`AT`.

    Total order breaks same-instant ties by commit SHA, which the builders
    below set to opaque per-kind strings -- adequate for testing tie-breaking
    itself, but wrong for a narrative where one event must precede another
    (a review closes after it opens, a carve-out is retired after it is
    ratified). Give causally related events distinct ``at=T(n)`` values rather
    than leaving them to default to the same instant.
    """
    return AT + timedelta(days=n)


ACTOR: dict[str, str] = {"identity": "maintainer", "role": "maintainer"}

VALID_CONSTRAINTS: dict[str, str] = {
    "bounding": "Applies only to read paths under /export; no write surface.",
    "mechanism": "Feature-flagged behind export.v2, owned by the platform team.",
    "safety": "No PII leaves the region; verified by the residency test suite.",
    "sequencing": "Expires when the covering review closes, or on 2027-01-01.",
}

_EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(LedgerEvent)
_CHARTER_ADAPTER: TypeAdapter[Any] = TypeAdapter(Charter)


def non_goal(ng_id: str = "NG-1", *, budget: int | None = None, status: str = "active") -> dict:
    doc: dict[str, Any] = {
        "id": ng_id,
        "text": f"The system does not do the thing {ng_id} names.",
        "rationale": "A boundary exists because scope must stay bounded.",
        "status": status,
    }
    if budget is not None:
        doc["budget"] = budget
    return doc


def charter(
    *,
    non_goals: list[dict] | None = None,
    status: str = "ratified",
    profile: str = "standard",
    adopted_at: datetime | None = None,
    config: dict | None = None,
    charter_version: str = "1.0.0",
) -> Charter:
    """A valid Charter, with sane defaults overridable per test."""
    doc: dict[str, Any] = {
        "spec_version": "0.1.0",
        "charter_version": charter_version,
        "status": status,
        "profile": profile,
        "non_goals": non_goals or [non_goal("NG-1", budget=2)],
    }
    if adopted_at is not None:
        doc["adopted_at"] = adopted_at.isoformat()
    if config is not None:
        doc["config"] = config
    return _CHARTER_ADAPTER.validate_python(doc)


def provenance(*, at: datetime = AT, sha: str = "abc123", provisional: bool = False) -> Provenance:
    return Provenance(commit_sha=sha, committed_at=at, first_parent=True, provisional=provisional)


def _resolve(path: str, payload: dict, *, at: datetime, sha: str) -> ResolvedEvent:
    event = _EVENT_ADAPTER.validate_python(payload)
    return ResolvedEvent(path=LedgerPath(path), event=event, provenance=provenance(at=at, sha=sha))


def ratified(
    co_id: str = "CO-1",
    non_goal_id: str = "NG-1",
    *,
    at: datetime = AT,
    sha: str | None = None,
    self_ratified: bool = False,
    expires_at: datetime | None = None,
) -> ResolvedEvent:
    payload: dict[str, Any] = {
        "event_type": "carveout.ratified",
        "id": co_id,
        "non_goal": non_goal_id,
        "title": f"Carve-out {co_id}",
        "constraints": VALID_CONSTRAINTS,
        "actor": ACTOR,
        "ratifiers": [ACTOR],
        "self_ratified": self_ratified,
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()
    return _resolve(
        f"ledger/{co_id}.ratified.yaml", payload, at=at, sha=sha or f"sha-{co_id}-ratified"
    )


def retired(co_id: str = "CO-1", *, at: datetime = AT, sha: str | None = None) -> ResolvedEvent:
    payload = {
        "event_type": "carveout.retired",
        "id": co_id,
        "reason": "Superseded by a later design; no longer needed.",
        "actor": ACTOR,
    }
    return _resolve(
        f"ledger/{co_id}.retired.yaml", payload, at=at, sha=sha or f"sha-{co_id}-retired"
    )


def expired(
    co_id: str = "CO-1",
    *,
    at: datetime = AT,
    sha: str | None = None,
    basis: str = "condition_met",
) -> ResolvedEvent:
    payload = {
        "event_type": "carveout.expired",
        "id": co_id,
        "basis": basis,
        "reason": "The declared expiry condition was attested as met.",
        "actor": ACTOR,
    }
    return _resolve(
        f"ledger/{co_id}.expired.yaml", payload, at=at, sha=sha or f"sha-{co_id}-expired"
    )


def review_opened(
    rv_id: str = "RV-1",
    *,
    at: datetime = AT,
    sha: str | None = None,
    trigger: str = "voluntary",
    scope_global: bool = True,
    scope_non_goals: tuple[str, ...] = (),
) -> ResolvedEvent:
    payload: dict[str, Any] = {
        "event_type": "review.opened",
        "id": rv_id,
        "trigger": trigger,
        "scope": {"global": scope_global, "non_goals": list(scope_non_goals)},
        "artifact": f"reviews/{rv_id.lower()}.md",
        "actor": ACTOR,
    }
    return _resolve(f"ledger/{rv_id}.opened.yaml", payload, at=at, sha=sha or f"sha-{rv_id}-opened")


def review_closed(
    rv_id: str = "RV-1",
    *,
    at: datetime = AT,
    sha: str | None = None,
    outcome: str = "upheld",
) -> ResolvedEvent:
    payload = {
        "event_type": "review.closed",
        "id": rv_id,
        "outcome": outcome,
        "closed_by": [ACTOR],
        "artifact": f"reviews/{rv_id.lower()}.md",
        "actor": ACTOR,
    }
    return _resolve(f"ledger/{rv_id}.closed.yaml", payload, at=at, sha=sha or f"sha-{rv_id}-closed")


def correction(
    cr_id: str = "CR-1",
    *,
    target: str = "CO-1.ratified",
    at: datetime = AT,
    sha: str | None = None,
    kind: str = "annotate",
) -> ResolvedEvent:
    payload = {
        "event_type": "correction",
        "id": cr_id,
        "corrects": {"event_key": target},
        "kind": kind,
        "reason": "The original event referenced the wrong test module.",
        "actor": ACTOR,
    }
    return _resolve(f"ledger/{cr_id}.correction.yaml", payload, at=at, sha=sha or f"sha-{cr_id}")
