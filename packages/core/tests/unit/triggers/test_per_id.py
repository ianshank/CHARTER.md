"""A6: the per-non-goal budget trigger."""

from __future__ import annotations

from fractions import Fraction

import pytest

from charter_core.profiles import get_profile
from charter_core.projection import project
from charter_core.settings import resolve_settings
from charter_core.triggers.base import TriggerContext
from charter_core.triggers.per_id import PerIdTrigger

from ...builders import T, charter, non_goal, ratified, retired, review_closed, review_opened

TRIGGER = PerIdTrigger()


def ctx(c, events, *, at):
    state = project(c, events, at=at)
    profile = get_profile(c.profile)
    settings = resolve_settings(
        config=None, profile_name=profile.name, profile_preset=profile.preset
    )
    return TriggerContext(charter=c, state=state, settings=settings, at=at)


class TestBudgetBoundary:
    @pytest.mark.req("REQ-TRIGGER-001")
    def test_at_budget_does_not_fire(self) -> None:
        """A6: exactly at budget is still open -- the off-by-one in the right direction."""
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", at=T(0)), ratified("CO-2", at=T(1))]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(2)))
        assert result.observed == Fraction(2)
        assert result.threshold == Fraction(2)
        assert result.fired is False

    @pytest.mark.req("REQ-TRIGGER-001")
    def test_over_budget_fires(self) -> None:
        """The (budget+1)th proposal, not literally 'the third'."""
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(3)))
        assert result.observed == Fraction(3)
        assert result.fired is True
        assert result.margin == Fraction(1)

    def test_budget_resolves_per_non_goal_over_config_over_profile_over_default(self) -> None:
        """A budget of 5 closes on the sixth, not the third."""
        c = charter(non_goals=[non_goal("NG-1", budget=5)])
        events = [ratified(f"CO-{i}", at=T(i)) for i in range(1, 6)]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(6)))
        assert result.threshold == Fraction(5)
        assert result.fired is False

    def test_no_budget_declared_falls_back_to_settings_default(self) -> None:
        c = charter(non_goals=[non_goal("NG-1")])  # no budget kwarg
        events = [ratified("CO-1", at=T(0)), ratified("CO-2", at=T(1))]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(2)))
        assert result.threshold == Fraction(2)  # settings.default_carveout_budget


class TestRetirementFreesQuota:
    def test_retiring_a_carveout_lowers_the_observed_count(self) -> None:
        """A4: per-ID counts concurrent, active carve-outs -- retirement relaxes it."""
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            retired("CO-1", at=T(3)),
        ]
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(4)))
        assert result.observed == Fraction(2)
        assert result.fired is False


class TestScopeIsolation:
    def test_each_non_goal_is_evaluated_independently(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=1), non_goal("NG-2", budget=5)])
        events = [
            ratified("CO-1", "NG-1", at=T(0)),
            ratified("CO-2", "NG-1", at=T(1)),
            ratified("CO-3", "NG-2", at=T(2)),
        ]
        results = {r.scope: r for r in TRIGGER.evaluate(ctx(c, events, at=T(3)))}
        assert results["NG-1"].fired is True
        assert results["NG-2"].fired is False

    def test_a_retired_non_goal_is_not_evaluated(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", status="retired", budget=1)])
        events = [ratified("CO-1", at=T(0)), ratified("CO-2", at=T(1))]
        assert list(TRIGGER.evaluate(ctx(c, events, at=T(2)))) == []


class TestRatchetIntegration:
    """The trigger consumes the projection layer's baseline directly."""

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_standing_still_after_a_review_does_not_refire(self) -> None:
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            review_opened(at=T(3), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(4)),
        ]
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(10)))
        assert result.baseline == Fraction(3)
        assert result.observed == Fraction(3)
        assert result.fired is False, "level == baseline must not refire"

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_further_erosion_after_review_still_fires(self) -> None:
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            review_opened(at=T(3), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(4)),
            ratified("CO-4", at=T(5)),
        ]
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        (result,) = TRIGGER.evaluate(ctx(c, events, at=T(6)))
        assert result.fired is True
