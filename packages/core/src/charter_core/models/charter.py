"""The charter.yaml document: declarations only.

What lives here is slow-moving and human-authored -- the non-goals, their
budgets, the thresholds, the profile. What does *not* live here is anything the
engine can compute: counts, path state, ratification provenance, or the date of
the last review. Those are derived from the ledger at check time, and storing
them would create a second source of truth with no defined winner.

Fields that a reader might reasonably expect and will not find are listed in
``FORBIDDEN_DERIVED_FIELDS`` so the gate can reject them with a migration hint
rather than a bare "additional properties" error.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from charter_core.models.common import (
    DocFloat,
    DocInt,
    NonGoalIdStr,
    Prose,
    SemVerStr,
    StrictBool,
    StrictModel,
    UtcModel,
)
from charter_core.settings import SCHEMA_DEFAULTS

#: Names that were part of the pre-event-sourcing draft, or that describe
#: derived state. Each maps to the remediation the gate should print.
FORBIDDEN_DERIVED_FIELDS: Final[dict[str, str]] = {
    "amendment_path": "Path state is computed from the ledger; remove this field.",
    "carveouts": "Carve-outs are ledger events under ledger/, not charter.yaml entries.",
    "reviews": "Reviews are ledger events under ledger/, not charter.yaml entries.",
    "last_full_review": "Derived from the most recent review.closed event; remove this field.",
    "ratified_at": "Derived from repository history; remove this field.",
    "commit": "Derived from repository history; remove this field.",
    "pr": "Derived from repository history; remove this field.",
}


class CharterStatus(StrictModel):
    """Placeholder namespace kept for symmetry; status is a plain literal."""


class NonGoal(UtcModel):
    """A declared boundary: something the system deliberately does not do."""

    id: NonGoalIdStr
    text: Prose = Field(description="The boundary, stated as a negative capability.")
    rationale: Prose = Field(description="Why this boundary exists.")
    status: Literal["active", "retired"] = "active"
    budget: Annotated[DocInt, Field(ge=0)] | None = Field(
        default=None,
        description="Concurrent carve-outs permitted. Falls back to config, profile, schema.",
    )


class ApprovalPolicyConfig(UtcModel):
    """Per-charter override of the profile's approval policy."""

    min_approvals: Annotated[DocInt, Field(ge=0)] | None = None
    require_code_owner: StrictBool | None = None
    distinct_from_author: StrictBool | None = None
    self_ratification_allowed: StrictBool | None = None


class ConfigBlock(UtcModel):
    """Every tunable in the system, in one place.

    All values are optional: an omitted key falls through to the profile preset
    and then to the schema default, and the resolved value records which layer
    supplied it.
    """

    density_window_days: Annotated[DocInt, Field(ge=1)] | None = None
    density_threshold: Annotated[DocInt, Field(ge=1)] | None = None
    cumulative_ratio: Annotated[DocFloat, Field(gt=0, le=1)] | None = None
    default_carveout_budget: Annotated[DocInt, Field(ge=0)] | None = None
    window_boundary: Literal["inclusive", "exclusive"] | None = None
    require_review_artifact: StrictBool | None = None
    ledger_pr_isolation: StrictBool | None = None
    approval_policy: ApprovalPolicyConfig | None = None


class Charter(UtcModel):
    """The parsed charter.yaml."""

    spec_version: SemVerStr = Field(description="The charter-kit SPEC version this targets.")
    charter_version: SemVerStr = Field(description="Semver of this charter's own content.")
    status: Literal["draft", "ratified"] = Field(
        description=(
            "In draft, trigger-based blocking is disabled but every structural check "
            "still applies, and conformance is capped at CL-2."
        )
    )
    profile: Literal["lite", "standard", "enterprise"] = "standard"
    adopted_at: AwareDatetime | None = Field(
        default=None,
        description=(
            "Genesis marker. Events at or before this instant are historical: exempt "
            "from velocity triggers, still counted by level triggers. Without it, "
            "back-filling existing carve-outs at adoption trips density on day one."
        ),
    )
    non_goals: Annotated[tuple[NonGoal, ...], Field(min_length=1)]
    config: ConfigBlock | None = None

    @field_validator("non_goals")
    @classmethod
    def _unique_ids(cls, value: tuple[NonGoal, ...]) -> tuple[NonGoal, ...]:
        seen: set[str] = set()
        for non_goal in value:
            if non_goal.id in seen:
                raise ValueError(f"Duplicate non-goal id: {non_goal.id}")
            seen.add(non_goal.id)
        return value

    @model_validator(mode="after")
    def _draft_caps_conformance(self) -> Charter:
        # Recorded here rather than enforced: the conformance level is computed
        # by the gate, which has the repository settings this model does not.
        return self

    @property
    def active_non_goals(self) -> tuple[NonGoal, ...]:
        """Non-goals that are still in force."""
        return tuple(ng for ng in self.non_goals if ng.status == "active")

    def budget_for(self, non_goal_id: str, *, fallback: int) -> int:
        """Resolve the carve-out budget for one non-goal."""
        for non_goal in self.non_goals:
            if non_goal.id == non_goal_id and non_goal.budget is not None:
                return non_goal.budget
        return fallback


def schema_default(key: str) -> object:
    """Expose a schema default for documentation and schema generation."""
    return SCHEMA_DEFAULTS[key]


__all__ = [
    "FORBIDDEN_DERIVED_FIELDS",
    "ApprovalPolicyConfig",
    "Charter",
    "ConfigBlock",
    "NonGoal",
    "schema_default",
]
