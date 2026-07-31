"""A5: the cumulative erosion ratio trigger. Level, global, exact Fraction math."""

from __future__ import annotations

from fractions import Fraction

import pytest

from charter_core.errors import CK
from charter_core.profiles import get_profile
from charter_core.projection import project
from charter_core.settings import resolve_settings
from charter_core.triggers.base import GLOBAL_SCOPE, TriggerContext
from charter_core.triggers.cumulative import CumulativeTrigger

from ...builders import T, charter, non_goal, ratified, retired, review_closed, review_opened

TRIGGER = CumulativeTrigger()


def ctx(c, events, *, at, config=None):
    state = project(c, events, at=at)
    profile = get_profile(c.profile)
    settings = resolve_settings(
        config=config, profile_name=profile.name, profile_preset=profile.preset
    )
    return TriggerContext(charter=c, state=state, settings=settings, at=at)


class TestExactRatioBoundary:
    @pytest.mark.req("REQ-TRIGGER-008")
    def test_exactly_at_threshold_does_not_fire(self) -> None:
        """1 of 2 active non-goals carved out == the 0.5 default threshold, exactly."""
        c = charter(non_goals=[non_goal("NG-1", budget=5), non_goal("NG-2", budget=5)])
        events = [ratified("CO-1", "NG-1", at=T(0))]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(1)))
        assert result.observed == Fraction(1, 2)
        assert result.threshold == Fraction(1, 2)
        assert result.fired is False

    @pytest.mark.req("REQ-TRIGGER-008")
    def test_over_threshold_fires(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=5), non_goal("NG-2", budget=5)])
        events = [ratified("CO-1", "NG-1", at=T(0)), ratified("CO-2", "NG-2", at=T(1))]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(2)))
        assert result.observed == Fraction(2, 2)
        assert result.fired is True

    def test_arithmetic_is_exact_not_float(self) -> None:
        """2 of 20 against a configured 0.1 threshold -- float would be unreliable here."""
        non_goals = [non_goal(f"NG-{i}", budget=5) for i in range(1, 21)]
        c = charter(non_goals=non_goals)
        events = [ratified("CO-1", "NG-1", at=T(0)), ratified("CO-2", "NG-2", at=T(1))]
        result_ctx = ctx(c, events, at=T(2), config={"cumulative_ratio": 0.1})
        (result,) = TRIGGER.evaluate(result_ctx)
        assert result.observed == Fraction(1, 10)
        assert result.threshold == Fraction(1, 10)
        assert result.fired is False


class TestZeroActiveNonGoals:
    @pytest.mark.req("REQ-TRIGGER-008")
    def test_ratio_is_zero_with_a_warning_not_an_error(self) -> None:
        """A5: no boundary left to erode -- defined, not a crash."""
        c = charter(non_goals=[non_goal("NG-1", status="retired")])
        (result,) = TRIGGER.evaluate(ctx(c, [], at=T(0)))
        assert result.observed == Fraction(0)
        assert result.fired is False
        assert [d.code for d in result.diagnostics] == [CK.W1003_NO_ACTIVE_NON_GOALS.code]


class TestScope:
    def test_scope_is_always_global(self) -> None:
        (result,) = TRIGGER.evaluate(ctx(charter(), [ratified(at=T(0))], at=T(0)))
        assert result.scope == GLOBAL_SCOPE


class TestRetirementRelaxes:
    def test_retiring_a_carveout_lowers_the_ratio(self) -> None:
        """A4: cumulative counts concurrent active carve-outs."""
        c = charter(non_goals=[non_goal("NG-1", budget=5), non_goal("NG-2", budget=5)])
        events = [
            ratified("CO-1", "NG-1", at=T(0)),
            ratified("CO-2", "NG-2", at=T(1)),
            retired("CO-2", at=T(2)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(3)))
        assert result.observed == Fraction(1, 2)


class TestRatchetIntegration:
    @pytest.mark.req("REQ-TRIGGER-005")
    def test_a_non_global_review_does_not_set_the_baseline(self) -> None:
        """Cumulative is repo-wide; only a global closure re-baselines it."""
        c = charter(non_goals=[non_goal("NG-1", budget=5)])
        events = [
            ratified("CO-1", at=T(0)),
            review_opened(at=T(1), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(2)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(3)))
        assert result.baseline is None

    @pytest.mark.req("REQ-TRIGGER-005")
    def test_further_erosion_after_global_closure_still_fires(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=5), non_goal("NG-2", budget=5)])
        events = [
            ratified("CO-1", "NG-1", at=T(0)),
            review_opened(at=T(1), scope_global=True),
            review_closed(at=T(2)),
            ratified("CO-2", "NG-2", at=T(3)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(4)))
        assert result.baseline == Fraction(1, 2)
        assert result.observed == Fraction(2, 2)
        assert result.fired is True
