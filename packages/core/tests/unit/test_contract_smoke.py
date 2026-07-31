"""The contract smoke test: every frozen model builds, every port has a fake.

WP-0 exists so that ten parallel work packages can build against contracts that
will not move. This module is the proof those contracts are usable: it
constructs one of every model and one working fake of every Protocol. If a lane
cannot write its code against these, WP-0 is not finished.

The fakes here are also the reference implementations the other lanes copy.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from fractions import Fraction

import pytest
from pydantic import TypeAdapter

from charter_core.ids import LedgerPath, event_key, parse_ledger_path
from charter_core.models.charter import Charter
from charter_core.models.events import EventKind, LedgerEvent
from charter_core.models.report import EvaluationReport
from charter_core.models.state import (
    Baselines,
    CarveOutState,
    CarveOutStatus,
    Closure,
    LedgerState,
    PathState,
    ResolvedEvent,
    ReviewState,
    ReviewStatus,
    Verdict,
    VerdictKind,
)
from charter_core.ports import (
    Actor,
    ApprovalFacts,
    ApprovalSource,
    ChangeStatus,
    Clock,
    DiffSource,
    LedgerSource,
    PathChange,
    Provenance,
    ProvenanceProvider,
    PullRequestResolver,
)

AT = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Reference fakes. Other work packages should copy these rather than invent
# their own, so that a port change breaks one place instead of ten.
# --------------------------------------------------------------------------
class FakeProvenance:
    """A ProvenanceProvider backed by a dictionary."""

    def __init__(
        self,
        entries: Mapping[str, Provenance] | None = None,
        *,
        shallow: bool = False,
        default_ref: str = "origin/main",
    ) -> None:
        self._entries = dict(entries or {})
        self._shallow = shallow
        self._default_ref = default_ref

    def provenance_for(self, paths: Sequence[LedgerPath]) -> Mapping[LedgerPath, Provenance | None]:
        return {path: self._entries.get(path) for path in paths}

    def is_shallow(self) -> bool:
        return self._shallow

    def default_ref(self) -> str:
        return self._default_ref


class FakeLedger:
    """A LedgerSource backed by decoded documents."""

    def __init__(self, documents: Mapping[str, Mapping[str, object]]) -> None:
        self._documents = dict(documents)

    def documents(self) -> Iterator[tuple[LedgerPath, Mapping[str, object]]]:
        for path, document in self._documents.items():
            yield LedgerPath(path), document


class FakeDiff:
    """A DiffSource returning a fixed changeset."""

    def __init__(self, changes: Sequence[PathChange] = ()) -> None:
        self._changes = tuple(changes)

    def changed_paths(self, base: str, head: str) -> Sequence[PathChange]:
        del base, head
        return self._changes


class FakeApprovals:
    """An ApprovalSource and PullRequestResolver in one."""

    def __init__(self, facts: ApprovalFacts, *, sha_to_pr: Mapping[str, int] | None = None) -> None:
        self._facts = facts
        self._sha_to_pr = dict(sha_to_pr or {})

    def approvals_for(self, pr_number: int) -> ApprovalFacts:
        del pr_number
        return self._facts

    def pr_for_commit(self, sha: str) -> int | None:
        return self._sha_to_pr.get(sha)


class FrozenClock:
    """A Clock pinned to one instant, so tests never depend on wall time."""

    def __init__(self, instant: datetime = AT) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class TestPortsHaveWorkingFakes:
    def test_provenance_provider(self) -> None:
        provenance = Provenance(
            commit_sha="abc123", committed_at=AT, first_parent=True, provisional=False
        )
        provider: ProvenanceProvider = FakeProvenance({"ledger/CO-1.ratified.yaml": provenance})
        resolved = provider.provenance_for(
            [LedgerPath("ledger/CO-1.ratified.yaml"), LedgerPath("ledger/CO-2.ratified.yaml")]
        )
        assert resolved[LedgerPath("ledger/CO-1.ratified.yaml")] == provenance
        assert resolved[LedgerPath("ledger/CO-2.ratified.yaml")] is None
        assert provider.is_shallow() is False
        assert provider.default_ref() == "origin/main"

    def test_ledger_source(self) -> None:
        source: LedgerSource = FakeLedger({"ledger/CO-1.ratified.yaml": {"id": "CO-1"}})
        assert list(source.documents()) == [("ledger/CO-1.ratified.yaml", {"id": "CO-1"})]

    def test_diff_source(self) -> None:
        source: DiffSource = FakeDiff(
            [PathChange(path="ledger/CO-1.ratified.yaml", status=ChangeStatus.ADDED)]
        )
        (change,) = source.changed_paths("main", "HEAD")
        assert change.status is ChangeStatus.ADDED

    def test_diff_source_reports_renames_with_the_previous_path(self) -> None:
        """Renames are forbidden, so the previous path must survive to the error."""
        source: DiffSource = FakeDiff(
            [
                PathChange(
                    path="ledger/CO-2.ratified.yaml",
                    status=ChangeStatus.RENAMED,
                    previous_path="ledger/CO-1.ratified.yaml",
                )
            ]
        )
        (change,) = source.changed_paths("main", "HEAD")
        assert change.previous_path == "ledger/CO-1.ratified.yaml"

    def test_approval_source_and_resolver(self) -> None:
        facts = ApprovalFacts(
            pr_number=42,
            merged=True,
            author="author",
            approvers=(Actor(identity="reviewer", role="maintainer"),),
            code_owner_approved=True,
        )
        approvals: ApprovalSource = FakeApprovals(facts, sha_to_pr={"abc123": 42})
        resolver: PullRequestResolver = FakeApprovals(facts, sha_to_pr={"abc123": 42})
        assert approvals.approvals_for(42).merged
        assert resolver.pr_for_commit("abc123") == 42
        assert resolver.pr_for_commit("unknown") is None

    def test_clock(self) -> None:
        clock: Clock = FrozenClock()
        assert clock.now() == AT
        assert clock.now().tzinfo is not None


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
def test_charter_model_constructs() -> None:
    charter = TypeAdapter(Charter).validate_python(
        {
            "spec_version": "0.1.0",
            "charter_version": "1.0.0",
            "status": "ratified",
            "non_goals": [
                {
                    "id": "NG-1",
                    "text": "The system does not target platforms other than GitHub.",
                    "rationale": "Control-plane primitives differ enough to make it premature.",
                }
            ],
        }
    )
    assert charter.active_non_goals[0].id == "NG-1"


@pytest.mark.parametrize("kind", list(EventKind))
def test_every_event_kind_has_a_constructible_variant(kind: EventKind) -> None:
    """A kind with no buildable payload would be an unreachable branch."""
    actor = {"identity": "maintainer", "role": "maintainer"}
    constraints = {
        "bounding": "Applies only to read paths under /export; no write surface exposed.",
        "mechanism": "Feature-flagged behind export.v2, owned by the platform team.",
        "safety": "No PII leaves the region; verified by the residency test suite.",
        "sequencing": "Expires when the covering review closes, or on 2027-01-01.",
    }
    payloads: dict[EventKind, dict[str, object]] = {
        EventKind.CARVEOUT_RATIFIED: {
            "id": "CO-1",
            "non_goal": "NG-1",
            "title": "Export path",
            "constraints": constraints,
            "ratifiers": [actor],
        },
        EventKind.CARVEOUT_RETIRED: {"id": "CO-1", "reason": "Superseded by the v3 design."},
        EventKind.CARVEOUT_EXPIRED: {
            "id": "CO-1",
            "basis": "condition_met",
            "reason": "The covering review closed as amended.",
        },
        EventKind.REVIEW_OPENED: {
            "id": "RV-1",
            "trigger": "density",
            "scope": {"global": True},
            "artifact": "reviews/2026-07-30.md",
        },
        EventKind.REVIEW_CLOSED: {
            "id": "RV-1",
            "outcome": "amended",
            "closed_by": [actor],
            "artifact": "reviews/2026-07-30.md",
        },
        EventKind.CORRECTION: {
            "id": "CR-1",
            "corrects": {"event_key": "CO-1.ratified"},
            "kind": "annotate",
            "reason": "The safety constraint referenced the wrong test module.",
        },
    }
    event = TypeAdapter(LedgerEvent).validate_python(
        {"event_type": kind.value, "actor": actor, **payloads[kind]}
    )
    assert event.event_type is kind


def test_resolved_event_key_matches_the_filename_grammar() -> None:
    """The stem and the payload must agree, or provenance points at the wrong event."""
    event = TypeAdapter(LedgerEvent).validate_python(
        {
            "event_type": "carveout.retired",
            "id": "CO-7",
            "reason": "Superseded by the v3 design.",
            "actor": {"identity": "maintainer", "role": "maintainer"},
        }
    )
    resolved = ResolvedEvent(
        path=LedgerPath("ledger/CO-7.retired.yaml"),
        event=event,
        provenance=Provenance(
            commit_sha="abc123", committed_at=AT, first_parent=True, provisional=False
        ),
    )
    assert resolved.event_key == "CO-7.retired"
    assert resolved.at == AT

    parsed = parse_ledger_path(resolved.path)
    assert parsed is not None
    assert event_key(*parsed) == resolved.event_key


def test_state_models_construct() -> None:
    carve_out = CarveOutState(
        id="CO-1",
        non_goal="NG-1",
        status=CarveOutStatus.ACTIVE,
        ratified_at=AT,
        ratified_commit="abc123",
        self_ratified=False,
        expires_at=None,
        historical=False,
    )
    review = ReviewState(
        id="RV-1",
        status=ReviewStatus.OPEN,
        opened_at=AT,
        closed_at=None,
        scope_global=True,
        scope_non_goals=(),
        trigger="density",
        artifact="reviews/2026-07-30.md",
    )
    state = LedgerState(
        ordered=(),
        carveouts={"CO-1": carve_out},
        reviews={"RV-1": review},
        baselines=Baselines(per_non_goal={"NG-1": 2}, cumulative=Fraction(1, 2)),
        evaluated_at=AT,
    )

    assert state.active_carveouts_for("NG-1") == (carve_out,)
    assert state.open_reviews == (review,)
    assert review.covers("NG-1") is True
    assert state.baselines.for_non_goal("NG-1") == 2
    assert state.baselines.for_non_goal("NG-2") is None


def test_moot_carveouts_leave_every_count() -> None:
    """A retired non-goal must not let its carve-outs spike the ratio."""
    moot = CarveOutState(
        id="CO-1",
        non_goal="NG-1",
        status=CarveOutStatus.MOOT,
        ratified_at=AT,
        ratified_commit="abc123",
        self_ratified=False,
        expires_at=None,
        historical=False,
    )
    assert moot.counts_toward_level is False
    assert moot.counts_toward_velocity is False


def test_historical_carveouts_leave_velocity_but_not_level() -> None:
    """Genesis back-fill must not trip density, yet must still count toward the ceiling."""
    historical = CarveOutState(
        id="CO-1",
        non_goal="NG-1",
        status=CarveOutStatus.ACTIVE,
        ratified_at=AT,
        ratified_commit="abc123",
        self_ratified=False,
        expires_at=None,
        historical=True,
    )
    assert historical.counts_toward_velocity is False
    assert historical.counts_toward_level is True


class TestVerdictWireFormat:
    def test_violation_renders_the_non_goal(self) -> None:
        verdict = Verdict(kind=VerdictKind.VIOLATION, non_goals=("NG-2",), reasons=("per_id",))
        assert verdict.render() == "VIOLATION(NG-2)"

    def test_multiple_non_goals_render_deterministically(self) -> None:
        verdict = Verdict(
            kind=VerdictKind.VIOLATION, non_goals=("NG-1", "NG-2"), reasons=("per_id",)
        )
        assert verdict.render() == "VIOLATION(NG-1,NG-2)"

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [(VerdictKind.PASS, "PASS"), (VerdictKind.REVIEW_REQUIRED, "REVIEW_REQUIRED")],
    )
    def test_non_violation_verdicts_render_bare(self, kind: VerdictKind, expected: str) -> None:
        assert Verdict(kind=kind, non_goals=(), reasons=()).render() == expected


def test_path_state_global_closure_dominates_per_non_goal() -> None:
    """An open review blocks everything, whatever a single non-goal's state says."""
    state = PathState(
        global_state=Closure.REVIEW_REQUIRED,
        per_non_goal={"NG-1": Closure.OPEN},
        causes={"global": ("RV-1",)},
    )
    assert state.for_non_goal("NG-1") is Closure.REVIEW_REQUIRED


def test_evaluation_report_model_constructs() -> None:
    """The report is an attestation subject; it must build from plain data."""
    report = TypeAdapter(EvaluationReport).validate_python(
        {
            "run_id": "01JZ",
            "evaluated_at": "2026-07-31T12:00:00Z",
            "core_version": "0.1.0",
            "spec_version": "0.1.0",
            "schema_version": "0.1",
            "profile": "standard",
            "status": "ratified",
            "conformance_ceiling": 3,
            "inputs": {"charter_digest": "sha256:0", "event_count": 0},
            "path_state": {"global_state": "open"},
            "verdict": {"kind": "PASS", "rendered": "PASS"},
            "result": "pass",
            "exit_code": 0,
        }
    )
    assert report.verdict.rendered == "PASS"
    assert report.report_version == "1"


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [("NG-1", 1), ("CO-12", 12), ("RV-100", 100), ("CR-7", 7)],
)
def test_ordinal_extracts_the_numeric_part(entity_id: str, expected: int) -> None:
    """Used for allocating the next free id; the grammar guarantees the split."""
    from charter_core.ids import ordinal

    assert ordinal(entity_id) == expected


@pytest.mark.parametrize(
    "path",
    [
        "ledger/CO-1.bogus.yaml",
        "ledger/CO-1.ratified.yml",
        "ledger/CO-01.ratified.yaml",
        "ledger/../CO-1.ratified.yaml",
        "reviews/CO-1.ratified.yaml",
        "ledger/CO-1.ratified.yaml\n",
    ],
)
def test_malformed_ledger_paths_do_not_parse(path: str) -> None:
    """The filename grammar is normative; anything off-grammar has no identity."""
    assert parse_ledger_path(path) is None
