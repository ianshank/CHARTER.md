"""A5: the cumulative erosion ratio. A level trigger, global in scope."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from typing import ClassVar

from charter_core.diagnostics import Diagnostic
from charter_core.errors import CK
from charter_core.triggers.base import GLOBAL_SCOPE, TriggerContext, TriggerResult


class CumulativeTrigger:
    """Fires when active carve-outs, summed across every non-goal, erode too much.

    "Too much" is exceeding ``cumulative_ratio`` (default 1/2) of the active
    non-goal count. With zero active non-goals there is no boundary left to
    erode: the ratio is defined as exactly 0 (A5), the trigger cannot fire,
    and a ``CK-W1003`` warning is attached so the report says why.
    """

    id: ClassVar[str] = "cumulative"

    def evaluate(self, ctx: TriggerContext) -> Sequence[TriggerResult]:
        """A single global result over the whole charter."""
        active_non_goals = ctx.charter.active_non_goals
        denominator = len(active_non_goals)
        threshold = ctx.settings.cumulative_ratio
        baseline = ctx.state.baselines.cumulative

        if denominator == 0:
            return [
                TriggerResult(
                    trigger_id=self.id,
                    kind="level",
                    fired=False,
                    scope=GLOBAL_SCOPE,
                    observed=Fraction(0),
                    threshold=threshold,
                    baseline=baseline,
                    margin=Fraction(0) - threshold,
                    diagnostics=(Diagnostic.of(CK.W1003_NO_ACTIVE_NON_GOALS),),
                )
            ]

        contributing: list[str] = []
        numerator = 0
        for non_goal in active_non_goals:
            active = ctx.state.active_carveouts_for(non_goal.id)
            numerator += len(active)
            contributing.extend(f"{c.id}.ratified" for c in active)

        observed = Fraction(numerator, denominator)
        fired = observed > threshold and (baseline is None or observed > baseline)

        return [
            TriggerResult(
                trigger_id=self.id,
                kind="level",
                fired=fired,
                scope=GLOBAL_SCOPE,
                observed=observed,
                threshold=threshold,
                baseline=baseline,
                margin=observed - threshold,
                contributing_events=tuple(sorted(contributing)),
            )
        ]


__all__ = ["CumulativeTrigger"]
