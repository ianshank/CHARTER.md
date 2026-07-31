"""The trigger contract: what every trigger consumes and returns.

Two operator conventions coexist by design, not oversight:

* **Level triggers** (``per_id``, ``cumulative``) fire on ``observed >
  threshold`` -- strict. A6 states this explicitly for the per-non-goal
  budget ("closes when active_count > budget, i.e. the (budget+1)th
  proposal"), and A2's general statement of the level-trigger rule
  ("fires when level > threshold and level > baseline") applies the same
  strict comparison to the cumulative ratio for consistency: one rule for
  both members of that family, not two.
* **The velocity trigger** (``density``) fires on ``observed >= threshold``
  -- inclusive, per its original specification ("≥3 ratifications ... in any
  rolling 90-day window"). A2 is scoped to level triggers by its own wording
  and does not redefine density's boundary, and density has no baseline to
  compare against in the first place (A1: it is self-relaxing via the
  sliding window, so nothing ratchets it).

A trigger that fired always compares strictly greater than its baseline too,
when one exists -- a level sitting exactly at a ratcheted floor must not
refire (the deadlock case A2 exists to prevent).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
from typing import ClassVar, Literal, Protocol

from charter_core.diagnostics import Diagnostic
from charter_core.models.charter import Charter
from charter_core.models.state import LedgerState
from charter_core.settings import ResolvedSettings

TriggerKind = Literal["velocity", "level"]

#: The scope a trigger result applies to: "global", or a non-goal id.
GLOBAL_SCOPE = "global"


@dataclass(frozen=True, slots=True)
class TriggerContext:
    """Everything a trigger needs, and nothing it can reach outside of this."""

    charter: Charter
    state: LedgerState
    settings: ResolvedSettings
    at: datetime


@dataclass(frozen=True, slots=True)
class TriggerResult:
    """One trigger's verdict for one scope.

    ``observed``, ``threshold``, ``baseline``, and ``margin`` are all
    :class:`~fractions.Fraction` so a single type covers both integer counts
    (rendering as e.g. ``"3"``) and ratios (``"1/2"``) without a union type at
    every call site -- and so comparisons stay exact, never float.
    """

    trigger_id: str
    kind: TriggerKind
    fired: bool
    scope: str
    observed: Fraction
    threshold: Fraction
    baseline: Fraction | None
    margin: Fraction
    """``observed - threshold``. Positive once a level trigger has fired;
    tells a reader how far past the line it is, not merely that it crossed."""
    contributing_events: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)
    """Findings the trigger itself surfaced while evaluating (e.g. A5's
    warning when a ratio's denominator is zero) -- distinct from ``fired``,
    which is a policy verdict, not a data-quality one."""


class Trigger(Protocol):
    """A registered trigger implementation."""

    id: ClassVar[str]

    def evaluate(self, ctx: TriggerContext) -> Sequence[TriggerResult]:
        """Evaluate this trigger for every scope it applies to."""
        ...


__all__ = [
    "GLOBAL_SCOPE",
    "Trigger",
    "TriggerContext",
    "TriggerKind",
    "TriggerResult",
]
