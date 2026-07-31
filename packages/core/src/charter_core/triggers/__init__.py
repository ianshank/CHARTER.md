"""The trigger registry: a dictionary, not an if/elif chain.

Adding a fourth trigger means writing a class that satisfies
:class:`~charter_core.triggers.base.Trigger` and instantiating it here --
:func:`evaluate_all` and every caller iterate the registry, so nothing else
needs to change. ``test_registry_completeness`` (in
``tests/unit/triggers/test_registry.py``) asserts every entry has both a unit
test and a conformance case, so a trigger added without tests fails CI rather
than shipping silently.
"""

from __future__ import annotations

from types import MappingProxyType

from charter_core.triggers.base import Trigger, TriggerContext, TriggerResult
from charter_core.triggers.cumulative import CumulativeTrigger
from charter_core.triggers.density import DensityTrigger
from charter_core.triggers.per_id import PerIdTrigger

TRIGGERS: MappingProxyType[str, Trigger] = MappingProxyType(
    {
        "per_id": PerIdTrigger(),
        "density": DensityTrigger(),
        "cumulative": CumulativeTrigger(),
    }
)


def evaluate_all(ctx: TriggerContext) -> tuple[TriggerResult, ...]:
    """Run every registered trigger and flatten their results."""
    return tuple(result for trigger in TRIGGERS.values() for result in trigger.evaluate(ctx))


__all__ = [
    "TRIGGERS",
    "CumulativeTrigger",
    "DensityTrigger",
    "PerIdTrigger",
    "Trigger",
    "TriggerContext",
    "TriggerResult",
    "evaluate_all",
]
