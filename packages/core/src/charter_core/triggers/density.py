"""The rolling density window. A velocity trigger, global in scope.

Self-relaxing by construction (A1): as ``at`` advances with no new events, the
window slides forward and ratifications age out of it on their own, with no
baseline to ratchet. This is the trigger the A2 correction does not touch.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from typing import ClassVar

from charter_core.triggers.base import GLOBAL_SCOPE, TriggerContext, TriggerResult
from charter_core.window import in_window


class DensityTrigger:
    """Fires when enough ratifications fall inside the trailing window.

    At least ``density_threshold`` (default 3) ratifications inside the
    trailing ``density_window_days`` window (default 90). Counts only
    ratifications that
    :attr:`~charter_core.models.state.CarveOutState.counts_toward_velocity` --
    excluding genesis back-fill (A11) and moot carve-outs (A12), since neither
    represents real amendment activity.
    """

    id: ClassVar[str] = "density"

    def evaluate(self, ctx: TriggerContext) -> Sequence[TriggerResult]:
        """A single global result over the whole ledger."""
        eligible = (c for c in ctx.state.carveouts.values() if c.counts_toward_velocity)
        in_range = [
            c
            for c in eligible
            if in_window(
                c.ratified_at,
                at=ctx.at,
                days=ctx.settings.density_window_days,
                boundary=ctx.settings.window_boundary,
            )
        ]
        observed = Fraction(len(in_range))
        threshold = Fraction(ctx.settings.density_threshold)

        return [
            TriggerResult(
                trigger_id=self.id,
                kind="velocity",
                fired=observed >= threshold,  # inclusive; see triggers/base.py
                scope=GLOBAL_SCOPE,
                observed=observed,
                threshold=threshold,
                baseline=None,
                margin=observed - threshold,
                contributing_events=tuple(sorted(f"{c.id}.ratified" for c in in_range)),
            )
        ]


__all__ = ["DensityTrigger"]
