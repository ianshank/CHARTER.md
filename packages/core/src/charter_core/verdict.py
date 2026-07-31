"""The guardian contract.

:func:`compute_verdict` is the whole contract: a pure function from computed
path state and the non-goals a change touches to one of three answers. This is
what makes the charter-guardian agent role safe to build -- the agent calls
this function (via ``charter verdict``) and narrates its result; it never
infers a verdict itself. The contract is what is unit-tested here; the agent
is a thin, untested-by-necessity presenter over it.
"""

from __future__ import annotations

from collections.abc import Sequence

from charter_core.models.state import Closure, PathState, Verdict, VerdictKind


def compute_verdict(path_state: PathState, touched_non_goals: Sequence[str]) -> Verdict:
    """PASS, VIOLATION(NG-x, ...), or REVIEW_REQUIRED.

    Only ``touched_non_goals`` are examined: a closed non-goal that a change
    does not touch produces no violation, and REVIEW_REQUIRED dominates
    everything else the moment any review is open, whether or not the change
    touches the reviewed non-goal.
    """
    if path_state.global_state is Closure.REVIEW_REQUIRED:
        return Verdict(
            kind=VerdictKind.REVIEW_REQUIRED,
            non_goals=(),
            reasons=path_state.causes.get("global", ()),
        )

    violated = sorted(
        {ng for ng in touched_non_goals if path_state.for_non_goal(ng) is Closure.CLOSED}
    )
    if not violated:
        return Verdict(kind=VerdictKind.PASS, non_goals=(), reasons=())

    reasons: set[str] = set()
    if path_state.global_state is Closure.CLOSED:
        reasons.update(path_state.causes.get("global", ()))
    for non_goal_id in violated:
        reasons.update(path_state.causes.get(non_goal_id, ()))

    return Verdict(
        kind=VerdictKind.VIOLATION, non_goals=tuple(violated), reasons=tuple(sorted(reasons))
    )


__all__ = ["compute_verdict"]
