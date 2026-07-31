"""Derived state: what the engine computes, and never reads from disk.

Every status in this module is a projection over the event stream at a given
instant. Nothing here is stored, which is what lets the ledger be append-only
while carve-outs and reviews still have lifecycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from fractions import Fraction

from charter_core.ids import LedgerPath
from charter_core.models.events import EventKind, LedgerEvent
from charter_core.ports import Provenance


@dataclass(frozen=True, slots=True)
class ResolvedEvent:
    """A ledger event joined to the provenance derived for its file."""

    path: LedgerPath
    event: LedgerEvent
    provenance: Provenance

    @property
    def event_key(self) -> str:
        """The canonical ``<id>.<kind>`` key, which must equal the file stem."""
        from charter_core.models.events import KIND_SUFFIX

        return f"{self.event.id}.{KIND_SUFFIX[self.event.event_type]}"

    @property
    def at(self) -> datetime:
        """When this event entered the default branch."""
        return self.provenance.committed_at


class CarveOutStatus(StrEnum):
    """The derived lifecycle position of a carve-out."""

    ACTIVE = "active"
    RETIRED = "retired"
    EXPIRED = "expired"
    MOOT = "moot"
    """Its non-goal was retired. Excluded from every count."""


class ReviewStatus(StrEnum):
    """The derived lifecycle position of a review."""

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class CarveOutState:
    """A carve-out's derived state at an evaluation instant."""

    id: str
    non_goal: str
    status: CarveOutStatus
    ratified_at: datetime
    ratified_commit: str
    self_ratified: bool
    expires_at: datetime | None
    historical: bool
    """True when ratified at or before the genesis marker."""

    @property
    def counts_toward_level(self) -> bool:
        """Whether this carve-out counts toward budget and ratio triggers."""
        return self.status is CarveOutStatus.ACTIVE

    @property
    def counts_toward_velocity(self) -> bool:
        """Whether this ratification counts toward the density window.

        Retirement does not un-happen churn, so velocity counts lifetime
        ratifications; only genesis back-fill is exempt.
        """
        return not self.historical and self.status is not CarveOutStatus.MOOT


@dataclass(frozen=True, slots=True)
class ReviewState:
    """A review's derived state at an evaluation instant."""

    id: str
    status: ReviewStatus
    opened_at: datetime
    closed_at: datetime | None
    scope_global: bool
    scope_non_goals: tuple[str, ...]
    trigger: str
    artifact: str

    def covers(self, non_goal_id: str | None) -> bool:
        """Whether this review's scope covers ``non_goal_id`` (or the repo)."""
        if self.scope_global:
            return True
        if non_goal_id is None:
            return False
        return non_goal_id in self.scope_non_goals


@dataclass(frozen=True, slots=True)
class Baselines:
    """Ratchet baselines for level triggers.

    A review closure re-baselines a level trigger to the level observed at that
    moment; the baseline then only ever moves down, so a retirement permanently
    lowers the bar. This is what stops a closed review from either deadlocking
    (fire immediately again) or resetting to zero (which would remove the
    erosion ceiling entirely and turn a budget into a rate limit).
    """

    per_non_goal: dict[str, int] = field(default_factory=dict)
    cumulative: Fraction | None = None

    def for_non_goal(self, non_goal_id: str) -> int | None:
        """The per-non-goal baseline, if a covering review has closed."""
        return self.per_non_goal.get(non_goal_id)


@dataclass(frozen=True, slots=True)
class LedgerState:
    """The full derived projection of the ledger at one instant."""

    ordered: tuple[ResolvedEvent, ...]
    carveouts: dict[str, CarveOutState]
    reviews: dict[str, ReviewState]
    baselines: Baselines
    evaluated_at: datetime

    @property
    def open_reviews(self) -> tuple[ReviewState, ...]:
        """Reviews still open, which block ratification repo-wide."""
        return tuple(r for r in self.reviews.values() if r.status is ReviewStatus.OPEN)

    def active_carveouts_for(self, non_goal_id: str) -> tuple[CarveOutState, ...]:
        """Active carve-outs recorded against one non-goal."""
        return tuple(
            c
            for c in self.carveouts.values()
            if c.non_goal == non_goal_id and c.counts_toward_level
        )

    def find(self, event_key: str) -> ResolvedEvent | None:
        """The ordered event with this canonical key, if any."""
        return next((e for e in self.ordered if e.event_key == event_key), None)

    def status_of(self, resolved: ResolvedEvent) -> str | None:
        """The derived lifecycle status of a carve-out or review event.

        ``None`` for event kinds with no lifecycle of their own (a correction,
        or a lifecycle event whose origin failed integrity and so was never
        projected).
        """
        kind = resolved.event.event_type
        if kind in (
            EventKind.CARVEOUT_RATIFIED,
            EventKind.CARVEOUT_RETIRED,
            EventKind.CARVEOUT_EXPIRED,
        ):
            carveout = self.carveouts.get(resolved.event.id)
            return carveout.status.value if carveout else None
        if kind in (EventKind.REVIEW_OPENED, EventKind.REVIEW_CLOSED):
            review = self.reviews.get(resolved.event.id)
            return review.status.value if review else None
        return None

    def historical_of(self, resolved: ResolvedEvent) -> bool:
        """Whether a ratification predates the genesis marker (A11)."""
        if resolved.event.event_type != EventKind.CARVEOUT_RATIFIED:
            return False
        carveout = self.carveouts.get(resolved.event.id)
        return carveout.historical if carveout else False


class Closure(StrEnum):
    """Whether amendment may proceed for a given scope."""

    OPEN = "open"
    CLOSED = "closed"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class PathState:
    """Per-non-goal and global amendment-path state, always computed."""

    global_state: Closure
    per_non_goal: dict[str, Closure]
    causes: dict[str, tuple[str, ...]]

    def for_non_goal(self, non_goal_id: str) -> Closure:
        """Effective closure for one non-goal, accounting for global state."""
        if self.global_state is not Closure.OPEN:
            return self.global_state
        return self.per_non_goal.get(non_goal_id, Closure.OPEN)


class VerdictKind(StrEnum):
    """The three answers the guardian contract may return."""

    PASS = "PASS"  # noqa: S105 -- a verdict name, not a credential
    VIOLATION = "VIOLATION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class Verdict:
    """The deterministic answer an agent narrates but never infers."""

    kind: VerdictKind
    non_goals: tuple[str, ...]
    reasons: tuple[str, ...]

    def render(self) -> str:
        """The exact wire format, e.g. ``VIOLATION(NG-2)``."""
        if self.kind is VerdictKind.VIOLATION and self.non_goals:
            return f"VIOLATION({','.join(self.non_goals)})"
        return str(self.kind.value)


__all__ = [
    "Baselines",
    "CarveOutState",
    "CarveOutStatus",
    "Closure",
    "LedgerState",
    "PathState",
    "ResolvedEvent",
    "ReviewState",
    "ReviewStatus",
    "Verdict",
    "VerdictKind",
]
