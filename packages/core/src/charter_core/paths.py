"""Computing amendment-path state from trigger results.

Never stored: this is a pure function of the current trigger verdicts and
which reviews are open, recomputed at every check.
"""

from __future__ import annotations

from collections.abc import Sequence

from charter_core.models.state import Closure, LedgerState, PathState
from charter_core.triggers.base import GLOBAL_SCOPE, TriggerResult


def compute_path_state(state: LedgerState, trigger_results: Sequence[TriggerResult]) -> PathState:
    """Derive per-non-goal and global closure.

    Any open review blocks ratification repo-wide, regardless of its own
    scope -- this is a hard gate, not itself a trigger, and it dominates
    everything else via
    :meth:`~charter_core.models.state.PathState.for_non_goal`. Absent an open
    review: ``density`` and ``cumulative`` (both global-scope triggers) close
    the path for everyone; ``per_id`` closes it only for the non-goal it
    fired against.
    """
    causes: dict[str, tuple[str, ...]] = {}
    per_non_goal: dict[str, Closure] = {}

    for result in trigger_results:
        if not result.fired or result.scope == GLOBAL_SCOPE:
            continue
        per_non_goal[result.scope] = Closure.CLOSED
        causes[result.scope] = (result.trigger_id,)

    global_triggers = tuple(
        sorted(r.trigger_id for r in trigger_results if r.fired and r.scope == GLOBAL_SCOPE)
    )
    open_review_ids = tuple(sorted(r.id for r in state.open_reviews))

    if open_review_ids:
        global_state = Closure.REVIEW_REQUIRED
        causes[GLOBAL_SCOPE] = open_review_ids
    elif global_triggers:
        global_state = Closure.CLOSED
        causes[GLOBAL_SCOPE] = global_triggers
    else:
        global_state = Closure.OPEN

    return PathState(global_state=global_state, per_non_goal=per_non_goal, causes=causes)


__all__ = ["compute_path_state"]
