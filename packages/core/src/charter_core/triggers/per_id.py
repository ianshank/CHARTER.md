"""A6: the per-non-goal budget. A level trigger, scoped to one non-goal."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from typing import ClassVar

from charter_core.triggers.base import TriggerContext, TriggerResult


class PerIdTrigger:
    """Fires when a non-goal's active carve-out count exceeds its budget.

    Budget resolves per-non-goal -> config -> profile -> schema default
    (:meth:`~charter_core.models.charter.Charter.budget_for`), so "the third
    proposal" is really "the (budget+1)th": a non-goal with an explicit
    ``budget: 5`` closes on its sixth active carve-out, not its third.
    """

    id: ClassVar[str] = "per_id"

    def evaluate(self, ctx: TriggerContext) -> Sequence[TriggerResult]:
        """One result per active non-goal."""
        results: list[TriggerResult] = []
        for non_goal in ctx.charter.active_non_goals:
            active = ctx.state.active_carveouts_for(non_goal.id)
            observed = Fraction(len(active))
            threshold = Fraction(
                ctx.charter.budget_for(non_goal.id, fallback=ctx.settings.default_carveout_budget)
            )
            baseline_raw = ctx.state.baselines.for_non_goal(non_goal.id)
            baseline = Fraction(baseline_raw) if baseline_raw is not None else None

            fired = observed > threshold and (baseline is None or observed > baseline)
            results.append(
                TriggerResult(
                    trigger_id=self.id,
                    kind="level",
                    fired=fired,
                    scope=non_goal.id,
                    observed=observed,
                    threshold=threshold,
                    baseline=baseline,
                    margin=observed - threshold,
                    contributing_events=tuple(sorted(f"{c.id}.ratified" for c in active)),
                )
            )
        return results


__all__ = ["PerIdTrigger"]
