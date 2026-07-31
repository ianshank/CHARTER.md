"""The single engine entry point.

Every other surface -- the CLI, the Action, the MCP server, the conformance
suite -- calls this one function and nothing else in core. It is total over
well-formed input: policy problems become diagnostics in the returned report,
never exceptions. It raises only on a genuine programmer error (a malformed
``ResolvedEvent`` that should never have reached this layer).

The one thing this function is not responsible for: deciding whether trigger
violations should fail a run. That is A13's job, applied here mechanically --
structural diagnostics (integrity, version negotiation) always contribute to
``result``/``exit_code``; a trigger-caused VIOLATION or REVIEW_REQUIRED only
does when ``charter.status == "ratified"``. Under ``draft``, the same verdict
is still computed and still visible in the report, with a warning explaining
that it is not blocking -- draft relaxes trigger-based blocking specifically,
not structural checks, and it caps the conformance claim at CL-2.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime

from charter_core.diagnostics import Diagnostic, DiagnosticBag, worst_exit_code
from charter_core.errors import CK
from charter_core.integrity import check_integrity
from charter_core.models.charter import Charter
from charter_core.models.report import (
    BaselineFacts,
    CountFacts,
    DiagnosticOut,
    EvaluationReport,
    EventFact,
    FactSet,
    InputFacts,
    LocationOut,
    PathStateOut,
    SettingProvenanceOut,
    TriggerReport,
    VerdictOut,
)
from charter_core.models.state import LedgerState, ResolvedEvent, VerdictKind
from charter_core.ordering import total_order
from charter_core.paths import compute_path_state
from charter_core.profiles import get_profile
from charter_core.projection import project
from charter_core.settings import ResolvedSettings
from charter_core.triggers import evaluate_all
from charter_core.triggers.base import TriggerContext, TriggerResult
from charter_core.verdict import compute_verdict
from charter_core.version import CORE_VERSION as _CORE_VERSION
from charter_core.version import SCHEMA_VERSION as _SCHEMA_VERSION
from charter_core.version import negotiate


def _digest(charter: Charter) -> str:
    """A stable fingerprint for audit purposes, not a security boundary."""
    payload = charter.model_dump_json().encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _to_diagnostic_out(diagnostic: Diagnostic) -> DiagnosticOut:
    location = None
    if diagnostic.location is not None:
        location = LocationOut(
            path=diagnostic.location.path,
            event_key=diagnostic.location.event_key,
            entity_id=diagnostic.location.entity_id,
            pointer=diagnostic.location.pointer,
        )
    return DiagnosticOut(
        code=diagnostic.code,
        severity=diagnostic.severity.value,
        message=diagnostic.message,
        spec_ref=diagnostic.spec_ref,
        remediation=diagnostic.remediation,
        location=location,
        context=dict(diagnostic.context),
    )


def _build_facts(state: LedgerState, charter: Charter) -> FactSet:
    events = tuple(
        EventFact(
            event_key=resolved.event_key,
            path=resolved.path,
            event_type=resolved.event.event_type.value,
            commit_sha=resolved.provenance.commit_sha,
            committed_at=resolved.provenance.committed_at.isoformat(),
            order_index=index,
            status=state.status_of(resolved),
            provisional=resolved.provenance.provisional,
            historical=state.historical_of(resolved),
        )
        for index, resolved in enumerate(state.ordered)
    )

    per_non_goal_counts = {
        ng.id: len(state.active_carveouts_for(ng.id)) for ng in charter.active_non_goals
    }
    cumulative_denominator = len(charter.active_non_goals)
    cumulative_numerator = sum(per_non_goal_counts.values())

    return FactSet(
        events=events,
        counts=CountFacts(
            per_non_goal=per_non_goal_counts,
            density=sum(1 for c in state.carveouts.values() if c.counts_toward_velocity),
            cumulative_numerator=cumulative_numerator,
            cumulative_denominator=cumulative_denominator,
        ),
        baselines=BaselineFacts(
            per_non_goal=dict(state.baselines.per_non_goal),
            cumulative=(
                str(state.baselines.cumulative) if state.baselines.cumulative is not None else None
            ),
        ),
    )


def _to_trigger_report(result: TriggerResult) -> TriggerReport:
    return TriggerReport(
        trigger_id=result.trigger_id,
        kind=result.kind,
        fired=result.fired,
        scope=result.scope,
        observed=str(result.observed),
        threshold=str(result.threshold),
        baseline=str(result.baseline) if result.baseline is not None else None,
        margin=str(result.margin),
        contributing_events=result.contributing_events,
    )


def evaluate(
    *,
    charter: Charter,
    events: Sequence[ResolvedEvent],
    at: datetime,
    settings: ResolvedSettings,
    run_id: str,
    touched_non_goals: Sequence[str] = (),
    base_ref: str | None = None,
    head_ref: str | None = None,
    default_ref: str | None = None,
    shallow: bool = False,
    fail_on_warning: bool = False,
) -> EvaluationReport:
    """Evaluate a charter against its ledger, as of ``at``.

    Total over well-formed input. A malformed ``spec_version`` or a broken
    referential-integrity rule ends the evaluation with a diagnosis rather
    than a partial or crashing result -- the report's ``path_state`` and
    ``verdict`` fields are always present and always mean what they say, even
    when nothing meaningful could be computed.
    """
    bag = DiagnosticBag()
    profile = get_profile(charter.profile)
    conformance_ceiling = 2 if charter.status == "draft" else profile.max_conformance_level
    inputs = InputFacts(
        charter_digest=_digest(charter),
        event_count=len(events),
        base_ref=base_ref,
        head_ref=head_ref,
        default_ref=default_ref,
        shallow=shallow,
        provisional=any(e.provenance.provisional for e in events),
    )

    negotiation = negotiate(charter.spec_version)
    if negotiation.code is not None:
        bag.add(negotiation.code)

    if not negotiation.can_evaluate:
        exit_code = worst_exit_code(bag.items(), fail_on_warning=fail_on_warning)
        return EvaluationReport(
            run_id=run_id,
            evaluated_at=at.isoformat(),
            core_version=_CORE_VERSION,
            spec_version=charter.spec_version,
            schema_version=_SCHEMA_VERSION,
            profile=charter.profile,
            status=charter.status,
            conformance_ceiling=conformance_ceiling,
            inputs=inputs,
            path_state=PathStateOut(global_state="open"),
            verdict=VerdictOut(kind="PASS", rendered="PASS"),
            diagnostics=tuple(_to_diagnostic_out(d) for d in bag),
            result="fail" if bag.has_errors() else "pass",
            exit_code=exit_code,
        )

    bag.extend(check_integrity(charter, total_order(events)))

    state = project(charter, events, at=at)
    trigger_results = evaluate_all(
        TriggerContext(charter=charter, state=state, settings=settings, at=at)
    )
    for result in trigger_results:
        bag.extend(result.diagnostics)

    path_state = compute_path_state(state, trigger_results)
    verdict = compute_verdict(path_state, touched_non_goals)

    if charter.status == "ratified":
        if verdict.kind is VerdictKind.VIOLATION:
            bag.add(
                CK.E0701_PATH_CLOSED,
                message=f"Touched non-goals are closed to amendment: {verdict.render()}",
                non_goals=verdict.non_goals,
            )
        elif verdict.kind is VerdictKind.REVIEW_REQUIRED:
            bag.add(
                CK.E0702_REVIEW_OPEN,
                message="A charter review is open; all ratification is blocked repo-wide.",
                open_reviews=path_state.causes.get("global", ()),
            )
    elif verdict.kind is not VerdictKind.PASS:
        bag.add(
            CK.W1004_DRAFT_STATUS_NON_BLOCKING,
            message=f"Would block under ratified status: {verdict.render()}",
        )

    exit_code = worst_exit_code(bag.items(), fail_on_warning=fail_on_warning)
    return EvaluationReport(
        run_id=run_id,
        evaluated_at=at.isoformat(),
        core_version=_CORE_VERSION,
        spec_version=charter.spec_version,
        schema_version=_SCHEMA_VERSION,
        profile=charter.profile,
        status=charter.status,
        conformance_ceiling=conformance_ceiling,
        settings={
            key: SettingProvenanceOut(
                value=prov.value, source=prov.source.value, detail=prov.detail
            )
            for key, prov in settings.provenance.items()
        },
        inputs=inputs,
        facts=_build_facts(state, charter),
        triggers=tuple(_to_trigger_report(r) for r in trigger_results),
        path_state=PathStateOut(
            global_state=path_state.global_state.value,
            per_non_goal={k: v.value for k, v in path_state.per_non_goal.items()},
            causes=path_state.causes,
        ),
        verdict=VerdictOut(
            kind=verdict.kind.value,
            non_goals=verdict.non_goals,
            reasons=verdict.reasons,
            rendered=verdict.render(),
        ),
        diagnostics=tuple(_to_diagnostic_out(d) for d in bag),
        result="fail" if bag.has_errors() else "pass",
        exit_code=exit_code,
    )


__all__ = ["evaluate"]
