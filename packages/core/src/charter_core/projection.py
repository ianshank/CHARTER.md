"""Events, projected into derived state.

Nothing in :class:`~charter_core.models.state.LedgerState` is stored anywhere;
this module is the only place it is computed, always fresh, from the charter
declarations and the resolved event stream, as of one instant.

Two simplifications make the harder parts of this tractable:

* **Non-goal status is a single fixed fact for the whole evaluation.** A
  non-goal's ``active``/``retired`` status lives in ``charter.yaml``, which has
  no ledger-event-level provenance the way carve-outs and reviews do -- there
  is one charter snapshot per evaluation, not a per-instant history of it. So
  "is NG-3 retired" does not vary by time within a single call to
  :func:`project`; the A12 moot cascade is a filter applied once, not a
  time-varying computation.
* **The A2 ratchet baseline is a minimum over a step function.** Between any
  two count-changing events (a ratification or a terminal event) the active
  count for a non-goal is constant, so the running minimum since a review's
  closure is achieved either at the closure instant itself or immediately
  after a later decrease -- see :func:`_floor_since` for the argument in full.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from charter_core.models.charter import Charter, NonGoal
from charter_core.models.events import EventKind
from charter_core.models.state import (
    Baselines,
    CarveOutState,
    CarveOutStatus,
    LedgerState,
    ResolvedEvent,
    ReviewState,
    ReviewStatus,
)
from charter_core.ordering import total_order


@dataclass(frozen=True, slots=True)
class _Interval:
    """When one carve-out counted as active, for baseline history."""

    non_goal: str
    start: datetime
    end: datetime | None
    """``None`` means still active as of the evaluation instant."""


@dataclass(frozen=True, slots=True)
class _CarveOutLifecycle:
    """A carve-out's status and, if it has ended, exactly when.

    Computed once so :class:`~charter_core.models.state.CarveOutState` (the
    status) and the baseline interval math (the terminal instant) cannot
    derive different answers from the same events.
    """

    status: CarveOutStatus
    terminal_at: datetime | None
    """When this carve-out stopped counting as active, or ``None`` if it has
    not (retirement and expiry both end it; whichever applies, its own event
    or declared instant -- never the outer evaluation instant)."""
    effective_expiry: datetime | None
    """A8: the declared/attested expiry, published on the state regardless of
    whether it has taken effect yet."""


def _lifecycle(
    *,
    declared_expires_at: datetime | None,
    non_goal_retired: bool,
    retirement: ResolvedEvent | None,
    expiration: ResolvedEvent | None,
    at: datetime,
) -> _CarveOutLifecycle:
    candidates = [
        ts for ts in (declared_expires_at, expiration.at if expiration else None) if ts is not None
    ]
    effective_expiry = min(candidates) if candidates else None  # A8

    if non_goal_retired:
        return _CarveOutLifecycle(CarveOutStatus.MOOT, None, effective_expiry)
    if retirement is not None:
        return _CarveOutLifecycle(CarveOutStatus.RETIRED, retirement.at, effective_expiry)
    if expiration is not None:
        return _CarveOutLifecycle(CarveOutStatus.EXPIRED, expiration.at, effective_expiry)
    if effective_expiry is not None and at >= effective_expiry:
        return _CarveOutLifecycle(CarveOutStatus.EXPIRED, effective_expiry, effective_expiry)
    return _CarveOutLifecycle(CarveOutStatus.ACTIVE, None, effective_expiry)


def _group_carveout_events(
    events: Sequence[ResolvedEvent],
) -> tuple[dict[str, ResolvedEvent], dict[str, ResolvedEvent], dict[str, ResolvedEvent]]:
    ratifications: dict[str, ResolvedEvent] = {}
    retirements: dict[str, ResolvedEvent] = {}
    expirations: dict[str, ResolvedEvent] = {}
    for resolved in events:
        kind = resolved.event.event_type
        if kind == EventKind.CARVEOUT_RATIFIED:
            ratifications.setdefault(resolved.event.id, resolved)
        elif kind == EventKind.CARVEOUT_RETIRED:
            retirements.setdefault(resolved.event.id, resolved)
        elif kind == EventKind.CARVEOUT_EXPIRED:
            expirations.setdefault(resolved.event.id, resolved)
    return ratifications, retirements, expirations


def _project_carveouts(
    charter: Charter,
    events: Sequence[ResolvedEvent],
    *,
    at: datetime,
    adopted_at: datetime | None,
) -> tuple[dict[str, CarveOutState], list[_Interval]]:
    retired_non_goals = {ng.id for ng in charter.non_goals if ng.status == "retired"}
    ratifications, retirements, expirations = _group_carveout_events(events)

    carveouts: dict[str, CarveOutState] = {}
    intervals: list[_Interval] = []
    for co_id, ratified in ratifications.items():
        event = ratified.event
        assert event.event_type == EventKind.CARVEOUT_RATIFIED  # noqa: S101 -- narrows the union
        lifecycle = _lifecycle(
            declared_expires_at=event.expires_at,
            non_goal_retired=event.non_goal in retired_non_goals,
            retirement=retirements.get(co_id),
            expiration=expirations.get(co_id),
            at=at,
        )

        carveouts[co_id] = CarveOutState(
            id=co_id,
            non_goal=event.non_goal,
            status=lifecycle.status,
            ratified_at=ratified.at,
            ratified_commit=ratified.provenance.commit_sha,
            self_ratified=event.self_ratified,
            expires_at=lifecycle.effective_expiry,
            historical=adopted_at is not None and ratified.at <= adopted_at,
        )
        if lifecycle.status is not CarveOutStatus.MOOT:
            intervals.append(
                _Interval(non_goal=event.non_goal, start=ratified.at, end=lifecycle.terminal_at)
            )
    return carveouts, intervals


def _project_reviews(events: Sequence[ResolvedEvent]) -> dict[str, ReviewState]:
    opened: dict[str, ResolvedEvent] = {}
    closed: dict[str, ResolvedEvent] = {}
    for resolved in events:
        kind = resolved.event.event_type
        if kind == EventKind.REVIEW_OPENED:
            opened.setdefault(resolved.event.id, resolved)
        elif kind == EventKind.REVIEW_CLOSED:
            closed.setdefault(resolved.event.id, resolved)

    reviews: dict[str, ReviewState] = {}
    for rv_id, opening in opened.items():
        event = opening.event
        assert event.event_type == EventKind.REVIEW_OPENED  # noqa: S101 -- narrows the union
        closing = closed.get(rv_id)
        reviews[rv_id] = ReviewState(
            id=rv_id,
            status=ReviewStatus.CLOSED if closing is not None else ReviewStatus.OPEN,
            opened_at=opening.at,
            closed_at=closing.at if closing is not None else None,
            scope_global=event.scope.global_,
            scope_non_goals=event.scope.non_goals,
            trigger=str(event.trigger.value),
            artifact=event.artifact,
        )
    return reviews


def _count_at(intervals: Sequence[_Interval], non_goal: str, instant: datetime) -> int:
    """Active count for ``non_goal`` at ``instant``.

    ``instant < end`` (strict) mirrors the main status derivation: expiry takes
    effect *at* its instant, so a carve-out is not counted there.
    """
    return sum(
        1
        for interval in intervals
        if interval.non_goal == non_goal
        and interval.start <= instant
        and (interval.end is None or instant < interval.end)
    )


def _floor_since(intervals: Sequence[_Interval], non_goal: str, since: datetime) -> int:
    """The minimum active count for ``non_goal`` observed at or after ``since``.

    Only decreases can lower a running minimum; new ratifications after
    ``since`` only ever raise the count, so they cannot be where the floor is
    achieved and do not need their own candidate instant. Evaluating at
    ``since`` itself and at every later terminal instant is therefore
    sufficient -- and, because ``_count_at`` already excludes an interval at
    its own end instant, each candidate reflects the count *immediately after*
    that decrease, which is exactly the floor's definition.
    """
    candidates = {since}
    candidates.update(
        interval.end
        for interval in intervals
        if interval.non_goal == non_goal and interval.end is not None and interval.end > since
    )
    return min(_count_at(intervals, non_goal, instant) for instant in candidates)


def _per_non_goal_baseline(
    non_goals: Sequence[NonGoal],
    intervals: Sequence[_Interval],
    reviews: dict[str, ReviewState],
    *,
    at: datetime,
) -> dict[str, int]:
    baselines: dict[str, int] = {}
    for ng in non_goals:
        if ng.status != "active":
            continue
        covering_closures = [
            review.closed_at
            for review in reviews.values()
            if review.status is ReviewStatus.CLOSED
            and review.closed_at is not None
            and review.closed_at <= at
            and review.covers(ng.id)
        ]
        if not covering_closures:
            continue
        closure_at = max(covering_closures)
        baselines[ng.id] = _floor_since(intervals, ng.id, closure_at)
    return baselines


def _cumulative_baseline(
    non_goals: Sequence[NonGoal],
    intervals: Sequence[_Interval],
    reviews: dict[str, ReviewState],
    *,
    at: datetime,
) -> Fraction | None:
    active_ids = tuple(ng.id for ng in non_goals if ng.status == "active")
    denominator = len(active_ids)
    if denominator == 0:
        return None

    covering_closures = [
        review.closed_at
        for review in reviews.values()
        if review.status is ReviewStatus.CLOSED
        and review.closed_at is not None
        and review.closed_at <= at
        and review.scope_global
    ]
    if not covering_closures:
        return None

    closure_at = max(covering_closures)

    candidates = {closure_at}
    candidates.update(
        interval.end
        for interval in intervals
        if interval.end is not None and interval.end > closure_at
    )

    def numerator_at(instant: datetime) -> int:
        return sum(_count_at(intervals, ng_id, instant) for ng_id in active_ids)

    floor_numerator = min(numerator_at(instant) for instant in candidates)
    return Fraction(floor_numerator, denominator)


def project(charter: Charter, events: Sequence[ResolvedEvent], *, at: datetime) -> LedgerState:
    """Derive the full ledger state as of ``at``.

    Only events with provenance at or before ``at`` are considered: evaluating
    "as of instant X" must not see events that, from X's perspective, have not
    happened yet. This also grounds the monotonicity guarantee -- advancing
    ``at`` over a fixed event set can only ever reveal more events, never
    retract one already in view.
    """
    ordered = tuple(e for e in total_order(events) if e.at <= at)

    carveouts, intervals = _project_carveouts(
        charter, ordered, at=at, adopted_at=charter.adopted_at
    )
    reviews = _project_reviews(ordered)

    baselines = Baselines(
        per_non_goal=_per_non_goal_baseline(charter.non_goals, intervals, reviews, at=at),
        cumulative=_cumulative_baseline(charter.non_goals, intervals, reviews, at=at),
    )

    return LedgerState(
        ordered=ordered,
        carveouts=carveouts,
        reviews=reviews,
        baselines=baselines,
        evaluated_at=at,
    )


__all__ = ["project"]
