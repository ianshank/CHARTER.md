"""The engine's single entry point: integrity, projection, triggers, verdict."""

from __future__ import annotations

import pytest

from charter_core.evaluate import evaluate
from charter_core.profiles import get_profile
from charter_core.settings import resolve_settings

from ..builders import T, charter, non_goal, ratified, review_opened


def settings_for(c):
    profile = get_profile(c.profile)
    return resolve_settings(config=None, profile_name=profile.name, profile_preset=profile.preset)


class TestVersionNegotiationEarlyExit:
    def test_unsupported_major_short_circuits(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)], charter_version="1.0.0")
        c = c.model_copy(update={"spec_version": "9.0.0"})
        report = evaluate(charter=c, events=[], at=T(0), settings=settings_for(c), run_id="run-1")
        assert report.result == "fail"
        assert report.exit_code == 5
        assert any(d.code == "CK-E0101" for d in report.diagnostics)
        assert report.path_state.global_state == "open"
        assert report.verdict.kind == "PASS"
        assert report.facts.events == ()


class TestCleanPass:
    def test_no_events_no_touches_passes(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        report = evaluate(
            charter=c,
            events=[],
            at=T(0),
            settings=settings_for(c),
            run_id="run-2",
            touched_non_goals=(),
        )
        assert report.result == "pass"
        assert report.exit_code == 0
        assert report.verdict.kind == "PASS"
        assert report.verdict.rendered == "PASS"
        assert report.path_state.global_state == "open"
        assert report.diagnostics == ()

    def test_facts_reflect_projected_state(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", at=T(0))]
        report = evaluate(
            charter=c, events=events, at=T(1), settings=settings_for(c), run_id="run-3"
        )
        assert len(report.facts.events) == 1
        event_fact = report.facts.events[0]
        assert event_fact.event_type == "carveout.ratified"
        assert event_fact.status == "active"
        assert report.facts.counts.per_non_goal == {"NG-1": 1}
        assert len(report.triggers) > 0


class TestViolationUnderRatified:
    @pytest.mark.req("REQ-TRIGGER-001")
    def test_over_budget_touched_non_goal_violates_and_blocks(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)], status="ratified")
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        report = evaluate(
            charter=c,
            events=events,
            at=T(3),
            settings=settings_for(c),
            run_id="run-4",
            touched_non_goals=["NG-1"],
        )
        assert report.verdict.kind == "VIOLATION"
        assert report.verdict.non_goals == ("NG-1",)
        assert any(d.code == "CK-E0701" for d in report.diagnostics)
        assert report.result == "fail"
        assert report.exit_code == 1

    def test_untouched_non_goal_does_not_block(self) -> None:
        """Only NG-1's per_id trigger fires here.

        Four non-goals keep the cumulative ratio at exactly the threshold and
        two carve-outs stay below density's window count, confirming a
        per-non-goal closure doesn't leak to a scope it wasn't raised against.
        """
        c = charter(
            non_goals=[
                non_goal("NG-1", budget=1),
                non_goal("NG-2", budget=5),
                non_goal("NG-3", budget=5),
                non_goal("NG-4", budget=5),
            ]
        )
        events = [ratified("CO-1", at=T(0)), ratified("CO-2", at=T(1))]
        report = evaluate(
            charter=c,
            events=events,
            at=T(2),
            settings=settings_for(c),
            run_id="run-5",
            touched_non_goals=["NG-2"],
        )
        assert report.verdict.kind == "PASS"
        assert report.result == "pass"
        assert report.exit_code == 0


class TestReviewRequiredUnderRatified:
    @pytest.mark.req("REQ-TRIGGER-002")
    def test_open_review_blocks_repo_wide(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [review_opened(at=T(0))]
        report = evaluate(
            charter=c,
            events=events,
            at=T(1),
            settings=settings_for(c),
            run_id="run-6",
            touched_non_goals=(),
        )
        assert report.verdict.kind == "REVIEW_REQUIRED"
        assert any(d.code == "CK-E0702" for d in report.diagnostics)
        assert report.path_state.global_state == "review_required"
        assert report.result == "fail"
        assert report.exit_code == 1


class TestDraftStatusNonBlocking:
    def test_would_be_violation_only_warns_under_draft(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)], status="draft")
        events = [
            ratified("CO-1", at=T(0)),
            ratified("CO-2", at=T(1)),
            ratified("CO-3", at=T(2)),
        ]
        report = evaluate(
            charter=c,
            events=events,
            at=T(3),
            settings=settings_for(c),
            run_id="run-7",
            touched_non_goals=["NG-1"],
        )
        assert report.verdict.kind == "VIOLATION"
        assert any(d.code == "CK-W1004" for d in report.diagnostics)
        assert not any(d.code == "CK-E0701" for d in report.diagnostics)
        assert report.result == "pass"
        assert report.exit_code == 0
        assert report.conformance_ceiling == 2

    def test_draft_pass_is_silent(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)], status="draft")
        report = evaluate(charter=c, events=[], at=T(0), settings=settings_for(c), run_id="run-8")
        assert report.verdict.kind == "PASS"
        assert report.diagnostics == ()
        assert report.result == "pass"


class TestIntegrityDiagnosticsCarryLocation:
    def test_unknown_non_goal_ref_reports_a_located_diagnostic(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", "NG-999", at=T(0))]
        report = evaluate(
            charter=c, events=events, at=T(1), settings=settings_for(c), run_id="run-11"
        )
        (diagnostic,) = [d for d in report.diagnostics if d.code == "CK-E0501"]
        assert diagnostic.location is not None
        assert diagnostic.location.path == "ledger/CO-1.ratified.yaml"
        assert diagnostic.location.event_key == "CO-1.ratified"
        assert report.result == "fail"


class TestReportShape:
    def test_settings_provenance_is_carried(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        report = evaluate(charter=c, events=[], at=T(0), settings=settings_for(c), run_id="run-9")
        assert "density_threshold" in report.settings
        assert report.settings["density_threshold"].source == "schema_default"

    def test_trigger_reports_render_fractions_as_strings(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        events = [ratified("CO-1", at=T(0)), ratified("CO-2", at=T(1))]
        report = evaluate(
            charter=c, events=events, at=T(2), settings=settings_for(c), run_id="run-10"
        )
        per_id = next(t for t in report.triggers if t.trigger_id == "per_id" and t.scope == "NG-1")
        assert per_id.observed == "2"
        assert per_id.threshold == "2"
        assert per_id.fired is False

    def test_run_id_and_versions_are_echoed(self) -> None:
        c = charter(non_goals=[non_goal("NG-1", budget=2)])
        report = evaluate(
            charter=c, events=[], at=T(0), settings=settings_for(c), run_id="the-run-id"
        )
        assert report.run_id == "the-run-id"
        assert report.spec_version == c.spec_version
        assert report.status == c.status
