"""The rolling density window trigger: velocity, global scope, no baseline."""

from __future__ import annotations

from fractions import Fraction

import pytest

from charter_core.profiles import get_profile
from charter_core.projection import project
from charter_core.settings import resolve_settings
from charter_core.triggers.base import GLOBAL_SCOPE, TriggerContext
from charter_core.triggers.density import DensityTrigger

from ...builders import T, charter, ratified, retired

TRIGGER = DensityTrigger()


def ctx(c, events, *, at):
    state = project(c, events, at=at)
    profile = get_profile(c.profile)
    settings = resolve_settings(
        config=None, profile_name=profile.name, profile_preset=profile.preset
    )
    return TriggerContext(charter=c, state=state, settings=settings, at=at)


class TestDensityBoundary:
    @pytest.mark.req("REQ-TRIGGER-002")
    def test_below_threshold_does_not_fire(self) -> None:
        events = [ratified("CO-1", at=T(0)), ratified("CO-2", at=T(1))]
        (result,) = TRIGGER.evaluate(ctx(charter(), events, at=T(1)))
        assert result.observed == Fraction(2)
        assert result.fired is False

    @pytest.mark.req("REQ-TRIGGER-002")
    def test_at_threshold_fires(self) -> None:
        """Density is inclusive ('>=3'), unlike the level triggers' strict '>'."""
        c = charter(non_goals=[{"id": "NG-1", "text": "x" * 30, "rationale": "y" * 30}])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(2)))
        assert result.observed == Fraction(3)
        assert result.threshold == Fraction(3)
        assert result.fired is True

    def test_scope_is_always_global(self) -> None:
        (result,) = TRIGGER.evaluate(ctx(charter(), [ratified(at=T(0))], at=T(0)))
        assert result.scope == GLOBAL_SCOPE

    def test_no_baseline_ever(self) -> None:
        """A1: density is self-relaxing via the window; nothing ratchets it."""
        (result,) = TRIGGER.evaluate(ctx(charter(), [ratified(at=T(0))], at=T(0)))
        assert result.baseline is None


class TestWindowMembership:
    @pytest.mark.req("REQ-TRIGGER-003")
    def test_exactly_90_days_old_is_inside_the_default_inclusive_window(self) -> None:
        c = charter(non_goals=[{"id": "NG-1", "text": "x" * 30, "rationale": "y" * 30}])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(90)))
        assert "CO-1.ratified" in result.contributing_events

    def test_91_days_old_is_outside_the_window(self) -> None:
        (result,) = TRIGGER.evaluate(ctx(charter(), [ratified(at=T(0))], at=T(91)))
        assert result.observed == Fraction(0)

    def test_window_slides_forward_and_relaxes_on_its_own(self) -> None:
        """Time only relaxes: no new events, just advancing `at`, drops the count."""
        c = charter(non_goals=[{"id": "NG-1", "text": "x" * 30, "rationale": "y" * 30}])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        still_in_window = TRIGGER.evaluate(ctx(c, events, at=T(2)))[0]
        aged_out = TRIGGER.evaluate(ctx(c, events, at=T(200)))[0]
        assert still_in_window.fired is True
        assert aged_out.fired is False


class TestVelocityExclusions:
    @pytest.mark.req("REQ-TRIGGER-006")
    def test_historical_backfill_is_excluded(self) -> None:
        """A11: genesis back-fill must not trip density on day one."""
        c = charter(
            adopted_at=T(0), non_goals=[{"id": "NG-1", "text": "x" * 30, "rationale": "y" * 30}]
        )
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(0)),
            ratified("CO-3", at=T(0)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(0)))
        assert result.observed == Fraction(0)
        assert result.fired is False

    def test_a_retired_carveout_still_counted_lifetime(self) -> None:
        """A4: density counts lifetime ratifications; retirement doesn't undo churn."""
        c = charter(non_goals=[{"id": "NG-1", "text": "x" * 30, "rationale": "y" * 30}])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            retired("CO-1", at=T(3)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(3)))
        assert result.observed == Fraction(3)
