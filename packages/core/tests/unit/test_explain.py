"""Explaining already-computed state: rendering, never recomputing."""

from __future__ import annotations

from fractions import Fraction

import pytest

from charter_core.explain import (
    explain_event,
    explain_path,
    explain_setting,
    explain_trigger,
)
from charter_core.models.state import Closure, PathState
from charter_core.profiles import get_profile
from charter_core.projection import project
from charter_core.settings import resolve_settings
from charter_core.triggers import evaluate_all
from charter_core.triggers.base import GLOBAL_SCOPE, TriggerContext

from ..builders import T, charter, correction, non_goal, ratified, review_closed, review_opened


def settings_for(c):
    profile = get_profile(c.profile)
    return resolve_settings(config=None, profile_name=profile.name, profile_preset=profile.preset)


def trigger_results(c, events, *, at):
    state = project(c, events, at=at)
    return evaluate_all(TriggerContext(charter=c, state=state, settings=settings_for(c), at=at))


class TestExplainTrigger:
    @pytest.mark.req("REQ-TRIGGER-001")
    def test_found_and_fired_narrates_the_full_trace(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        explanation = explain_trigger(trigger_results(c, events, at=T(3)), "per_id", "NG-1")
        assert explanation.found is True
        assert explanation.fired is True
        assert explanation.observed == Fraction(3)
        assert explanation.threshold == Fraction(2)
        assert explanation.margin == Fraction(1)
        assert "fired" in explanation.narrative
        assert "CO-1.ratified" in explanation.narrative

    def test_found_and_not_fired(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", at=T(0))]
        explanation = explain_trigger(trigger_results(c, events, at=T(1)), "per_id", "NG-1")
        assert explanation.found is True
        assert explanation.fired is False
        assert "did not fire" in explanation.narrative

    def test_unknown_scope_is_not_found_rather_than_raising(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        explanation = explain_trigger(trigger_results(c, [], at=T(0)), "per_id", "NG-nonexistent")
        assert explanation.found is False
        assert explanation.observed is None
        assert explanation.threshold is None
        assert explanation.margin is None
        assert "no such trigger" in explanation.narrative

    @pytest.mark.req("REQ-TRIGGER-004")
    def test_ratchet_baseline_is_included_when_present(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
            review_opened(at=T(3), scope_global=False, scope_non_goals=("NG-1",)),
            review_closed(at=T(4)),
        ]
        explanation = explain_trigger(trigger_results(c, events, at=T(10)), "per_id", "NG-1")
        assert explanation.baseline == Fraction(3)
        assert "ratchet baseline 3" in explanation.narrative

    def test_found_with_no_contributing_events_omits_that_clause(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        explanation = explain_trigger(trigger_results(c, [], at=T(0)), "per_id", "NG-1")
        assert explanation.found is True
        assert explanation.contributing_events == ()
        assert "contributing" not in explanation.narrative

    def test_density_scope_is_global(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", at=T(0))]
        explanation = explain_trigger(trigger_results(c, events, at=T(0)), "density", GLOBAL_SCOPE)
        assert explanation.found is True
        assert explanation.baseline is None


class TestExplainPath:
    def test_open_scope(self) -> None:
        path = PathState(global_state=Closure.OPEN, per_non_goal={}, causes={})
        explanation = explain_path(path, "NG-1")
        assert explanation.closure is Closure.OPEN
        assert explanation.causes == ()
        assert "open" in explanation.narrative

    @pytest.mark.req("REQ-TRIGGER-001")
    def test_per_non_goal_closure_reports_its_own_cause(self) -> None:
        path = PathState(
            global_state=Closure.OPEN,
            per_non_goal={"NG-1": Closure.CLOSED},
            causes={"NG-1": ("per_id",)},
        )
        explanation = explain_path(path, "NG-1")
        assert explanation.closure is Closure.CLOSED
        assert explanation.causes == ("per_id",)
        assert "closed, caused by per_id" in explanation.narrative

    @pytest.mark.req("REQ-TRIGGER-002")
    def test_global_closure_is_inherited_by_an_untouched_non_goal(self) -> None:
        path = PathState(
            global_state=Closure.CLOSED, per_non_goal={}, causes={GLOBAL_SCOPE: ("density",)}
        )
        explanation = explain_path(path, "NG-anything")
        assert explanation.closure is Closure.CLOSED
        assert explanation.causes == ("density",)

    def test_review_required_dominates(self) -> None:
        path = PathState(
            global_state=Closure.REVIEW_REQUIRED, per_non_goal={}, causes={GLOBAL_SCOPE: ("RV-1",)}
        )
        explanation = explain_path(path, GLOBAL_SCOPE)
        assert explanation.closure is Closure.REVIEW_REQUIRED
        assert "review required, blocked by RV-1" in explanation.narrative


class TestExplainSetting:
    def test_schema_default_provenance(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        explanation = explain_setting(settings_for(c), "density_threshold")
        assert explanation.value == 3
        assert explanation.source == "schema_default"
        assert "density_threshold" in explanation.narrative

    def test_explicit_config_provenance(self) -> None:
        profile = get_profile("standard")
        settings = resolve_settings(
            config={"density_threshold": 5},
            profile_name=profile.name,
            profile_preset=profile.preset,
        )
        explanation = explain_setting(settings, "density_threshold")
        assert explanation.value == 5
        assert explanation.source == "config"
        assert "charter.yaml#/config/density_threshold" in explanation.narrative

    def test_unknown_key_raises(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        with pytest.raises(KeyError):
            explain_setting(settings_for(c), "not_a_real_setting")


class TestExplainEvent:
    def test_found_active_carveout(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", at=T(0))]
        state = project(c, events, at=T(1))
        explanation = explain_event(state, "CO-1.ratified")
        assert explanation.found is True
        assert explanation.event_type == "carveout.ratified"
        assert explanation.status == "active"
        assert explanation.historical is False
        assert "status active" in explanation.narrative

    def test_historical_event_is_flagged(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)], adopted_at=T(0))
        events = [ratified("CO-1", at=T(0))]
        state = project(c, events, at=T(0))
        explanation = explain_event(state, "CO-1.ratified")
        assert explanation.historical is True
        assert "historical" in explanation.narrative

    def test_unknown_event_key_is_not_found(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        state = project(c, [], at=T(0))
        explanation = explain_event(state, "CO-999.ratified")
        assert explanation.found is False
        assert explanation.event_type is None
        assert "no such event" in explanation.narrative

    def test_correction_event_has_no_lifecycle_status(self) -> None:
        """A correction is annotation, not a lifecycle event -- status is None."""
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", at=T(0)), correction("CR-1", target="CO-1.ratified", at=T(1))]
        state = project(c, events, at=T(1))
        explanation = explain_event(state, "CR-1.correction")
        assert explanation.found is True
        assert explanation.status is None
        assert "status" not in explanation.narrative
