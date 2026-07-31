"""The evaluation report: the gate's structured output.

This is simultaneously the CI debugging surface, the enterprise audit trail,
and the conformance suite's golden artifact. It is designed to be an
attestation subject -- stable field order, canonical serialisation, content
digest -- so that signing it later does not require reshaping it.

Everything a reader needs to reproduce a verdict is here: the facts used, the
settings and where each came from, the thresholds compared against, and the
events that contributed to each trigger.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from charter_core.models.common import StrictModel


class SettingProvenanceOut(StrictModel):
    """A resolved threshold and the layer that supplied it."""

    value: object
    source: Literal["config", "profile", "schema_default"]
    detail: str


class EventFact(StrictModel):
    """One ledger event as the engine saw it."""

    event_key: str
    path: str
    event_type: str
    commit_sha: str
    committed_at: str
    order_index: int
    status: str | None = None
    provisional: bool = False
    historical: bool = False


class CountFacts(StrictModel):
    """The raw counts every trigger decision was made from."""

    per_non_goal: dict[str, int] = Field(default_factory=dict)
    density: int = 0
    cumulative_numerator: int = 0
    cumulative_denominator: int = 0


class BaselineFacts(StrictModel):
    """Ratchet baselines in force at evaluation time."""

    per_non_goal: dict[str, int] = Field(default_factory=dict)
    cumulative: str | None = None


class FactSet(StrictModel):
    """Everything the engine read, before it decided anything."""

    events: tuple[EventFact, ...] = ()
    counts: CountFacts = Field(default_factory=CountFacts)
    baselines: BaselineFacts = Field(default_factory=BaselineFacts)


class TriggerReport(StrictModel):
    """One trigger's evaluation, with enough detail to explain itself."""

    trigger_id: str
    kind: Literal["velocity", "level"]
    fired: bool
    scope: str
    observed: str
    threshold: str
    baseline: str | None = None
    margin: str
    contributing_events: tuple[str, ...] = ()


class PathStateOut(StrictModel):
    """Computed amendment-path state."""

    global_state: Literal["open", "closed", "review_required"]
    per_non_goal: dict[str, str] = Field(default_factory=dict)
    causes: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class VerdictOut(StrictModel):
    """The guardian contract's answer."""

    kind: Literal["PASS", "VIOLATION", "REVIEW_REQUIRED"]
    non_goals: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    rendered: str


class LocationOut(StrictModel):
    """Where a diagnostic applies."""

    path: str | None = None
    event_key: str | None = None
    entity_id: str | None = None
    pointer: str | None = None


class DiagnosticOut(StrictModel):
    """One finding, as serialised into the report."""

    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    spec_ref: str
    remediation: str
    location: LocationOut | None = None
    context: dict[str, object] = Field(default_factory=dict)


class InputFacts(StrictModel):
    """What the engine was pointed at."""

    charter_digest: str
    event_count: int
    base_ref: str | None = None
    head_ref: str | None = None
    default_ref: str | None = None
    shallow: bool = False
    provisional: bool = False


class EvaluationReport(StrictModel):
    """The complete result of one evaluation."""

    report_version: str = "1"
    run_id: str
    evaluated_at: str
    core_version: str
    spec_version: str
    schema_version: str
    profile: str
    status: Literal["draft", "ratified"]
    conformance_ceiling: Annotated[int, Field(ge=1, le=4)] = Field(
        description="Highest level this repository may claim. Draft status caps at CL-2."
    )
    settings: dict[str, SettingProvenanceOut] = Field(default_factory=dict)
    inputs: InputFacts
    facts: FactSet = Field(default_factory=FactSet)
    triggers: tuple[TriggerReport, ...] = ()
    path_state: PathStateOut
    verdict: VerdictOut
    diagnostics: tuple[DiagnosticOut, ...] = ()
    result: Literal["pass", "fail"]
    exit_code: int


__all__ = [
    "BaselineFacts",
    "CountFacts",
    "DiagnosticOut",
    "EvaluationReport",
    "EventFact",
    "FactSet",
    "InputFacts",
    "LocationOut",
    "PathStateOut",
    "SettingProvenanceOut",
    "TriggerReport",
    "VerdictOut",
]
