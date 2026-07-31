"""Central registry of charter-kit diagnostic codes.

Every normative failure the engine can report is defined exactly once here.
SPEC.md, the CLI exit codes, the evaluation report schema, the conformance
fixtures, and the traceability gate all key off this registry, so a code that
exists here without a SPEC reference -- or a SPEC requirement with no code --
is a CI failure rather than a documentation gap.

Code ranges:
    E01xx  spec version negotiation
    E02xx  charter declarations
    E03xx  ledger structure
    E04xx  environment and provenance
    E05xx  referential integrity
    E06xx  render / generated blocks
    E07xx  policy and triggers
    E08xx  approvals and profile policy
    E09xx  milestone guards
    W1xxx  warnings
    I2xxx  informational
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Final


class Severity(StrEnum):
    """How a diagnostic affects the outcome of an evaluation."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ErrorDef:
    """The immutable definition of a single diagnostic code."""

    code: str
    title: str
    severity: Severity
    spec_ref: str
    remediation: str
    exit_code: int


# Exit codes are duplicated as plain ints here so that charter-core stays free
# of any dependency on charter-cli. charter_cli.exit_codes.ExitCode is the
# authority on their names, and a test asserts the two agree.
_OK: Final = 0
_VIOLATION: Final = 1
_INPUT_INVALID: Final = 3
_ENVIRONMENT: Final = 4
_SPEC_UNSUPPORTED: Final = 5


class CK(Enum):
    """The diagnostic registry.

    Members are named ``<CODE>_<SLUG>`` so that a grep for the bare code finds
    both the definition and every use site.
    """

    # -- E01xx  spec version negotiation ------------------------------------
    E0101_SPEC_MAJOR_UNSUPPORTED = ErrorDef(
        code="CK-E0101",
        title="Unsupported spec_version major",
        severity=Severity.ERROR,
        spec_ref="REQ-VERSION-001",
        remediation="Upgrade charter-cli, or lower spec_version to a supported major.",
        exit_code=_SPEC_UNSUPPORTED,
    )
    W0102_SPEC_MINOR_NEWER = ErrorDef(
        code="CK-W0102",
        title="charter.yaml targets a newer spec minor than this engine",
        severity=Severity.WARNING,
        spec_ref="REQ-VERSION-002",
        remediation="Upgrade charter-cli to evaluate every feature this charter declares.",
        exit_code=_OK,
    )

    # -- E02xx  charter declarations ----------------------------------------
    E0201_DERIVED_VALUE_STORED = ErrorDef(
        code="CK-E0201",
        title="Derived value stored in charter.yaml",
        severity=Severity.ERROR,
        spec_ref="REQ-CHARTER-004",
        remediation=(
            "Remove the field. Counts, path state, and ratification provenance are "
            "computed from the ledger at check time and must never be stored."
        ),
        exit_code=_INPUT_INVALID,
    )
    E0202_NON_GOAL_REMOVED = ErrorDef(
        code="CK-E0202",
        title="Non-goal removed or renumbered",
        severity=Severity.ERROR,
        spec_ref="REQ-CHARTER-006",
        remediation="Set status to 'retired' instead of deleting the entry; ids are permanent.",
        exit_code=_VIOLATION,
    )
    E0203_NON_GOAL_EDIT_WITHOUT_REVIEW = ErrorDef(
        code="CK-E0203",
        title="Non-goal text changed without a review artifact",
        severity=Severity.ERROR,
        spec_ref="REQ-CHARTER-007",
        remediation="Open a charter review and reference its artifact in the same change.",
        exit_code=_VIOLATION,
    )
    E0204_NON_GOAL_ID_REUSED = ErrorDef(
        code="CK-E0204",
        title="Retired non-goal id reused",
        severity=Severity.ERROR,
        spec_ref="REQ-CHARTER-008",
        remediation="Allocate the next unused NG id; retired ids are never reused.",
        exit_code=_VIOLATION,
    )
    E0205_NON_GOAL_UNRETIRED = ErrorDef(
        code="CK-E0205",
        title="Non-goal moved from retired back to active",
        severity=Severity.ERROR,
        spec_ref="REQ-CHARTER-009",
        remediation="Declare a new non-goal instead of reviving a retired one.",
        exit_code=_VIOLATION,
    )
    E0206_CHARTER_VERSION_BUMP_REQUIRED = ErrorDef(
        code="CK-E0206",
        title="charter_version was not bumped for a change that requires it",
        severity=Severity.ERROR,
        spec_ref="REQ-CHARTER-010",
        remediation=(
            "Adding a non-goal or editing its text requires a MINOR bump; removing or "
            "narrowing one requires a MAJOR bump."
        ),
        exit_code=_VIOLATION,
    )

    # -- E03xx  ledger structure --------------------------------------------
    E0301_LEDGER_STEM_MISMATCH = ErrorDef(
        code="CK-E0301",
        title="Ledger filename does not match the event it contains",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-002",
        remediation="Rename so the stem is '<id>.<kind>', e.g. ledger/CO-1.ratified.yaml.",
        exit_code=_INPUT_INVALID,
    )
    E0302_LEDGER_FILE_RENAMED = ErrorDef(
        code="CK-E0302",
        title="Ledger file renamed",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-004",
        remediation=(
            "Restore the original path. Ratification provenance is derived from the "
            "commit that introduced the path, so renames destroy the audit trail."
        ),
        exit_code=_VIOLATION,
    )
    E0303_LEDGER_NON_ADDITIVE_HISTORY = ErrorDef(
        code="CK-E0303",
        title="Ledger path was added more than once",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-005",
        remediation=(
            "A second add means the file was previously deleted, which the append-only "
            "rule forbids. Record a correction event instead."
        ),
        exit_code=_VIOLATION,
    )
    E0304_LEDGER_ID_CASE_COLLISION = ErrorDef(
        code="CK-E0304",
        title="Ledger filenames collide case-insensitively",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-003",
        remediation="Rename one file; case-insensitive filesystems cannot hold both.",
        exit_code=_INPUT_INVALID,
    )
    E0305_LEDGER_FILE_MODIFIED = ErrorDef(
        code="CK-E0305",
        title="Existing ledger file modified",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-006",
        remediation="Revert the edit and append a correction event referencing the original.",
        exit_code=_VIOLATION,
    )
    E0306_LEDGER_FILE_DELETED = ErrorDef(
        code="CK-E0306",
        title="Ledger file deleted",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-006",
        remediation="Restore the file and append a retirement event instead.",
        exit_code=_VIOLATION,
    )
    E0307_CORRECTION_CHAIN = ErrorDef(
        code="CK-E0307",
        title="Correction targets another correction",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-009",
        remediation="Correct the original event directly; correction chains are not permitted.",
        exit_code=_VIOLATION,
    )
    E0308_LEDGER_YAML_HAZARD = ErrorDef(
        code="CK-E0308",
        title="Ledger document uses an unsafe YAML construct",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-010",
        remediation=(
            "Remove duplicate keys, anchors, aliases, merge keys, or extra documents. "
            "Ledger events must be a single plain mapping."
        ),
        exit_code=_INPUT_INVALID,
    )

    # -- E04xx  environment and provenance ----------------------------------
    E0401_SHALLOW_CLONE = ErrorDef(
        code="CK-E0401",
        title="Repository is a shallow clone",
        severity=Severity.ERROR,
        spec_ref="REQ-PROV-002",
        remediation="Set 'fetch-depth: 0' on actions/checkout, or run 'git fetch --unshallow'.",
        exit_code=_ENVIRONMENT,
    )
    E0402_NO_PROVENANCE = ErrorDef(
        code="CK-E0402",
        title="Ledger file has no commit on the default branch",
        severity=Severity.ERROR,
        spec_ref="REQ-PROV-003",
        remediation="Commit the event; uncommitted ledger files cannot be ratified.",
        exit_code=_ENVIRONMENT,
    )
    E0403_PROVISIONAL_PROVENANCE = ErrorDef(
        code="CK-W0403",
        title="Provenance derived off the default branch is provisional",
        severity=Severity.WARNING,
        spec_ref="REQ-PROV-004",
        remediation="Merge-time state is authoritative; this result is an advisory preview.",
        exit_code=_OK,
    )
    E0405_UNREVIEWED_LEDGER_COMMIT = ErrorDef(
        code="CK-E0405",
        title="Ledger event reached the default branch without a pull request",
        severity=Severity.ERROR,
        spec_ref="REQ-GATE-006",
        remediation="Ratification happens through a merged pull request; revert and reopen one.",
        exit_code=_VIOLATION,
    )
    E0406_LEDGER_SYMLINK = ErrorDef(
        code="CK-E0406",
        title="Ledger path is a symbolic link",
        severity=Severity.ERROR,
        spec_ref="REQ-LEDGER-011",
        remediation="Replace the symlink with a regular file; symlinks defeat the diff rules.",
        exit_code=_ENVIRONMENT,
    )

    # -- E05xx  referential integrity ---------------------------------------
    E0501_UNKNOWN_NON_GOAL_REF = ErrorDef(
        code="CK-E0501",
        title="Carve-out references an unknown non-goal",
        severity=Severity.ERROR,
        spec_ref="REQ-INTEG-001",
        remediation="Point the event at a non-goal declared in charter.yaml.",
        exit_code=_VIOLATION,
    )
    E0502_ORPHAN_LIFECYCLE_EVENT = ErrorDef(
        code="CK-E0502",
        title="Lifecycle event has no matching origin event",
        severity=Severity.ERROR,
        spec_ref="REQ-INTEG-002",
        remediation=(
            "A retirement, expiry, or closure requires the ratification or opening it refers to."
        ),
        exit_code=_VIOLATION,
    )
    E0503_DUPLICATE_LIFECYCLE_EVENT = ErrorDef(
        code="CK-E0503",
        title="Duplicate lifecycle event",
        severity=Severity.ERROR,
        spec_ref="REQ-INTEG-003",
        remediation="An entity may only be retired, expired, or closed once.",
        exit_code=_VIOLATION,
    )
    E0504_DUPLICATE_EVENT_ID = ErrorDef(
        code="CK-E0504",
        title="Two events declare the same id and kind",
        severity=Severity.ERROR,
        spec_ref="REQ-INTEG-004",
        remediation="Allocate a fresh id; event keys are unique across the ledger.",
        exit_code=_VIOLATION,
    )
    E0505_UNKNOWN_CORRECTION_TARGET = ErrorDef(
        code="CK-E0505",
        title="Correction references an event that does not exist",
        severity=Severity.ERROR,
        spec_ref="REQ-INTEG-005",
        remediation="Reference the event key of a real ledger event.",
        exit_code=_VIOLATION,
    )

    # -- E06xx  render and generated blocks ---------------------------------
    E0601_BLOCK_MARKER_MISSING = ErrorDef(
        code="CK-E0601",
        title="Generated block marker missing",
        severity=Severity.ERROR,
        spec_ref="REQ-RENDER-002",
        remediation="Restore the begin/end comment pair, then run 'charter render --write'.",
        exit_code=_VIOLATION,
    )
    E0602_BLOCK_DUPLICATED = ErrorDef(
        code="CK-E0602",
        title="Generated block id appears more than once",
        severity=Severity.ERROR,
        spec_ref="REQ-RENDER-003",
        remediation="Remove the duplicate; each block id may appear at most once per document.",
        exit_code=_VIOLATION,
    )
    E0603_BLOCK_UNBALANCED = ErrorDef(
        code="CK-E0603",
        title="Generated block markers are unbalanced",
        severity=Severity.ERROR,
        spec_ref="REQ-RENDER-004",
        remediation="Every begin marker needs a matching end marker, in order.",
        exit_code=_VIOLATION,
    )
    E0604_BLOCK_DRIFT = ErrorDef(
        code="CK-E0604",
        title="Generated block content is stale",
        severity=Severity.ERROR,
        spec_ref="REQ-RENDER-001",
        remediation="Run 'charter render --write' and commit the result.",
        exit_code=_VIOLATION,
    )
    E0605_BLOCK_NESTED = ErrorDef(
        code="CK-E0605",
        title="Generated blocks are nested",
        severity=Severity.ERROR,
        spec_ref="REQ-RENDER-005",
        remediation="Close the outer block before opening another.",
        exit_code=_VIOLATION,
    )
    E0606_BLOCK_UNKNOWN_ID = ErrorDef(
        code="CK-E0606",
        title="Unknown generated block id",
        severity=Severity.ERROR,
        spec_ref="REQ-RENDER-006",
        remediation="Use a block id this engine can render; see 'charter render --list'.",
        exit_code=_VIOLATION,
    )

    # -- E07xx  policy and triggers -----------------------------------------
    E0701_PATH_CLOSED = ErrorDef(
        code="CK-E0701",
        title="Amendment path is closed",
        severity=Severity.ERROR,
        spec_ref="REQ-TRIGGER-001",
        remediation="Open a charter review; ratification resumes once the review closes.",
        exit_code=_VIOLATION,
    )
    E0702_REVIEW_OPEN = ErrorDef(
        code="CK-E0702",
        title="Ratification attempted while a review is open",
        severity=Severity.ERROR,
        spec_ref="REQ-TRIGGER-002",
        remediation="Close the open review before ratifying further carve-outs.",
        exit_code=_VIOLATION,
    )
    E0705_CONSTRAINTS_INCOMPLETE = ErrorDef(
        code="CK-E0705",
        title="Carve-out constraints are incomplete",
        severity=Severity.ERROR,
        spec_ref="REQ-CARVEOUT-001",
        remediation=(
            "Give substantive bounding, mechanism, safety, and sequencing constraints. "
            "Placeholder text is rejected."
        ),
        exit_code=_VIOLATION,
    )
    E0707_LEDGER_PR_NOT_ISOLATED = ErrorDef(
        code="CK-E0707",
        title="Ledger change mixed with unrelated changes",
        severity=Severity.ERROR,
        spec_ref="REQ-GATE-004",
        remediation=(
            "Split the change: a pull request touching ledger/ may only also touch "
            "reviews/ and generated blocks."
        ),
        exit_code=_VIOLATION,
    )

    # -- E08xx  approvals and profile policy --------------------------------
    E0801_INSUFFICIENT_APPROVALS = ErrorDef(
        code="CK-E0801",
        title="Ratifying pull request lacks the required approvals",
        severity=Severity.ERROR,
        spec_ref="REQ-APPROVAL-001",
        remediation="Obtain the approvals this profile requires before merging.",
        exit_code=_VIOLATION,
    )
    E0803_SELF_RATIFICATION_FORBIDDEN = ErrorDef(
        code="CK-E0803",
        title="Self-ratification is not permitted by this profile",
        severity=Severity.ERROR,
        spec_ref="REQ-APPROVAL-003",
        remediation="Have a second ratifier approve, or switch to the lite profile.",
        exit_code=_VIOLATION,
    )

    # -- E09xx  milestone guards --------------------------------------------
    E0901_NOT_IMPLEMENTED = ErrorDef(
        code="CK-E0901",
        title="Capability is not available in this milestone",
        severity=Severity.ERROR,
        spec_ref="REQ-SCOPE-001",
        remediation="This surface is read-only in M0; open the pull request manually.",
        exit_code=_VIOLATION,
    )

    # -- W1xxx  warnings -----------------------------------------------------
    W1003_NO_ACTIVE_NON_GOALS = ErrorDef(
        code="CK-W1003",
        title="No active non-goals; cumulative ratio is undefined and treated as zero",
        severity=Severity.WARNING,
        spec_ref="REQ-TRIGGER-008",
        remediation=(
            "Declare at least one active non-goal for the cumulative trigger to mean anything."
        ),
        exit_code=_OK,
    )
    W1004_DRAFT_STATUS_NON_BLOCKING = ErrorDef(
        code="CK-W1004",
        title="Charter status is draft; trigger-based blocking is disabled",
        severity=Severity.WARNING,
        spec_ref="REQ-STATUS-002",
        remediation="Set status to 'ratified' to enforce triggers. Draft repositories cap at CL-2.",
        exit_code=_OK,
    )

    @property
    def code(self) -> str:
        """The stable ``CK-...`` string for this diagnostic."""
        return self.value.code

    @property
    def severity(self) -> Severity:
        """Whether this diagnostic fails an evaluation."""
        return self.value.severity

    @property
    def spec_ref(self) -> str:
        """The SPEC requirement id this diagnostic enforces."""
        return self.value.spec_ref

    @property
    def exit_code(self) -> int:
        """The process exit code this diagnostic maps to."""
        return self.value.exit_code


REGISTRY: Final[dict[str, ErrorDef]] = {member.value.code: member.value for member in CK}
