"""Causal trace: turning already-computed state into a narrative.

Every fact reported here already lives on a :class:`~charter_core.triggers.base.TriggerResult`,
a :class:`~charter_core.models.state.PathState`, a
:class:`~charter_core.settings.ResolvedSettings`, or a
:class:`~charter_core.models.state.LedgerState` -- explaining is rendering,
not recomputing. Nothing in this module reruns projection or trigger
evaluation; callers pass in what :func:`charter_core.evaluate.evaluate` (or
the trigger registry directly) already produced, so an explanation can never
disagree with the report it explains.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from charter_core.models.state import Closure, LedgerState, PathState
from charter_core.settings import ResolvedSettings
from charter_core.triggers.base import GLOBAL_SCOPE, TriggerResult


@dataclass(frozen=True, slots=True)
class TriggerExplanation:
    """Why one trigger, at one scope, did or did not fire."""

    trigger_id: str
    scope: str
    found: bool
    fired: bool
    observed: Fraction | None
    threshold: Fraction | None
    baseline: Fraction | None
    margin: Fraction | None
    contributing_events: tuple[str, ...]
    narrative: str


def explain_trigger(
    trigger_results: Sequence[TriggerResult], trigger_id: str, scope: str = GLOBAL_SCOPE
) -> TriggerExplanation:
    """Find the result for ``trigger_id`` at ``scope`` and narrate it.

    ``found=False`` when nothing evaluated at that id/scope pair -- typically
    a retired non-goal, or a scope that was never touched -- rather than
    raising, since a mistyped scope from an interactive ``explain`` call is a
    user question, not a programmer error.
    """
    for result in trigger_results:
        if result.trigger_id != trigger_id or result.scope != scope:
            continue
        verb = "fired" if result.fired else "did not fire"
        baseline_clause = (
            f", ratchet baseline {result.baseline}" if result.baseline is not None else ""
        )
        narrative = (
            f"{trigger_id}/{scope}: observed {result.observed}, threshold "
            f"{result.threshold}{baseline_clause}, margin {result.margin} -> {verb}"
        )
        if result.contributing_events:
            narrative += f", contributing: {', '.join(result.contributing_events)}"
        return TriggerExplanation(
            trigger_id=trigger_id,
            scope=scope,
            found=True,
            fired=result.fired,
            observed=result.observed,
            threshold=result.threshold,
            baseline=result.baseline,
            margin=result.margin,
            contributing_events=result.contributing_events,
            narrative=narrative,
        )
    return TriggerExplanation(
        trigger_id=trigger_id,
        scope=scope,
        found=False,
        fired=False,
        observed=None,
        threshold=None,
        baseline=None,
        margin=None,
        contributing_events=(),
        narrative=f"{trigger_id}/{scope}: no such trigger evaluated at this scope",
    )


@dataclass(frozen=True, slots=True)
class PathExplanation:
    """Why one scope's amendment path is open, closed, or review-required."""

    scope: str
    closure: Closure
    causes: tuple[str, ...]
    narrative: str


def explain_path(path_state: PathState, scope: str = GLOBAL_SCOPE) -> PathExplanation:
    """Narrate the closure for ``scope`` -- a non-goal id, or the global scope.

    Delegates to :meth:`~charter_core.models.state.PathState.for_non_goal` so
    the closure reported here is exactly what
    :func:`charter_core.verdict.compute_verdict` would have used, never a
    re-derivation that could drift from it. A non-goal closed only because
    review is open repo-wide, or because a global trigger fired, reports the
    global causes -- it has none of its own.
    """
    closure = path_state.global_state if scope == GLOBAL_SCOPE else path_state.for_non_goal(scope)
    causes = path_state.causes.get(scope, ())
    if not causes and scope != GLOBAL_SCOPE and closure is not Closure.OPEN:
        causes = path_state.causes.get(GLOBAL_SCOPE, ())

    if closure is Closure.OPEN:
        narrative = f"{scope}: open -- no trigger has fired and no review is open"
    elif closure is Closure.REVIEW_REQUIRED:
        narrative = f"{scope}: review required, blocked by {', '.join(causes)}"
    else:
        narrative = f"{scope}: closed, caused by {', '.join(causes)}"
    return PathExplanation(scope=scope, closure=closure, causes=causes, narrative=narrative)


@dataclass(frozen=True, slots=True)
class SettingExplanation:
    """Where one resolved threshold came from."""

    key: str
    value: object
    source: str
    detail: str
    narrative: str


def explain_setting(settings: ResolvedSettings, key: str) -> SettingExplanation:
    """Narrate a threshold's provenance.

    A thin wrapper over :meth:`~charter_core.settings.ResolvedSettings.explain`
    -- the provenance was already recorded at resolution time, in
    :func:`charter_core.settings.resolve_settings`; this only renders it.
    Raises ``KeyError`` for a key outside :data:`~charter_core.settings.SETTING_SPECS`,
    since that is a caller programming error, not a fact about the ledger.
    """
    provenance = settings.explain(key)
    narrative = (
        f"{key} = {provenance.value!r} (from {provenance.source.value}: {provenance.detail})"
    )
    return SettingExplanation(
        key=key,
        value=provenance.value,
        source=provenance.source.value,
        detail=provenance.detail,
        narrative=narrative,
    )


@dataclass(frozen=True, slots=True)
class EventExplanation:
    """What the engine derived for one ledger event."""

    event_key: str
    found: bool
    event_type: str | None
    path: str | None
    committed_at: str | None
    status: str | None
    historical: bool
    narrative: str


def explain_event(state: LedgerState, event_key: str) -> EventExplanation:
    """Narrate one event's derived status.

    Looks ``event_key`` up in the already-projected ``LedgerState.ordered``
    via :meth:`~charter_core.models.state.LedgerState.find` -- the same
    source :func:`charter_core.evaluate.evaluate` reads for its fact set, so
    this can never disagree with what a report says.
    """
    resolved = state.find(event_key)
    if resolved is None:
        return EventExplanation(
            event_key=event_key,
            found=False,
            event_type=None,
            path=None,
            committed_at=None,
            status=None,
            historical=False,
            narrative=f"{event_key}: no such event in the projected ledger",
        )

    status = state.status_of(resolved)
    historical = state.historical_of(resolved)
    narrative = (
        f"{event_key}: {resolved.event.event_type.value} "
        f"at {resolved.provenance.committed_at.isoformat()}"
    )
    if status is not None:
        narrative += f", status {status}"
    if historical:
        narrative += " (historical: exempt from velocity, A11)"
    return EventExplanation(
        event_key=event_key,
        found=True,
        event_type=resolved.event.event_type.value,
        path=str(resolved.path),
        committed_at=resolved.provenance.committed_at.isoformat(),
        status=status,
        historical=historical,
        narrative=narrative,
    )


__all__ = [
    "EventExplanation",
    "PathExplanation",
    "SettingExplanation",
    "TriggerExplanation",
    "explain_event",
    "explain_path",
    "explain_setting",
    "explain_trigger",
]
