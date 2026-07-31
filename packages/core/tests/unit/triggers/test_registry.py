"""The trigger registry: completeness, not just presence."""

from __future__ import annotations

import pathlib

from charter_core.profiles import get_profile
from charter_core.projection import project
from charter_core.settings import resolve_settings
from charter_core.triggers import TRIGGERS, evaluate_all
from charter_core.triggers.base import TriggerContext

from ...builders import T, charter, ratified


def test_the_registry_holds_exactly_the_three_specified_triggers() -> None:
    """A1: the velocity/level taxonomy names exactly three triggers."""
    assert set(TRIGGERS) == {"per_id", "density", "cumulative"}


def test_every_trigger_is_keyed_by_its_own_id() -> None:
    for key, trigger in TRIGGERS.items():
        assert trigger.id == key


def test_every_registered_trigger_has_a_unit_test_module() -> None:
    """A trigger added to the registry without its own test file is unreviewed."""
    triggers_dir = pathlib.Path(__file__).resolve().parent
    for trigger_id in TRIGGERS:
        assert (triggers_dir / f"test_{trigger_id}.py").is_file(), (
            f"{trigger_id} has no tests/unit/triggers/test_{trigger_id}.py"
        )


def test_evaluate_all_runs_every_trigger() -> None:
    c = charter()
    events = [ratified(at=T(0))]
    state = project(c, events, at=T(0))
    profile = get_profile(c.profile)
    settings = resolve_settings(
        config=None, profile_name=profile.name, profile_preset=profile.preset
    )
    results = evaluate_all(TriggerContext(charter=c, state=state, settings=settings, at=T(0)))
    assert {r.trigger_id for r in results} == {"per_id", "density", "cumulative"}
