"""The ledger event union.

One file per event, appended and never touched again. Everything downstream --
both JSON Schemas, the ledger filename grammar, the conformance fixtures, the
agent roles -- is shaped by this module.

Note what is *absent*: no ``ratified_at``, no ``commit``, no ``pr``, no
``status``. Those are derived at check time from repository history, because a
field written inside the commit being merged cannot describe that merge, and a
status that mutates in place cannot live in an append-only ledger.

The one stored instant is ``expires_at``, which is a declaration about the
future rather than a claim about the past, and so is legal to write down.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from charter_core.models.common import (
    ActorModel,
    ArtifactPath,
    CarveOutIdStr,
    Constraints,
    CorrectionIdStr,
    NonGoalIdStr,
    Prose,
    ReviewIdStr,
    SemVerStr,
    ShortText,
    StrictBool,
    UtcModel,
)


class EventKind(StrEnum):
    """The closed set of ledger event types for spec major 0."""

    CARVEOUT_RATIFIED = "carveout.ratified"
    CARVEOUT_RETIRED = "carveout.retired"
    CARVEOUT_EXPIRED = "carveout.expired"
    REVIEW_OPENED = "review.opened"
    REVIEW_CLOSED = "review.closed"
    CORRECTION = "correction"


#: Maps an event kind to the filename suffix that must carry it, so that the
#: path and the payload cannot disagree.
KIND_SUFFIX: dict[EventKind, str] = {
    EventKind.CARVEOUT_RATIFIED: "ratified",
    EventKind.CARVEOUT_RETIRED: "retired",
    EventKind.CARVEOUT_EXPIRED: "expired",
    EventKind.REVIEW_OPENED: "opened",
    EventKind.REVIEW_CLOSED: "closed",
    EventKind.CORRECTION: "correction",
}


class ReviewTrigger(StrEnum):
    """What caused a review to be opened."""

    PER_ID = "per_id"
    DENSITY = "density"
    CUMULATIVE = "cumulative"
    VOLUNTARY = "voluntary"


class ReviewOutcome(StrEnum):
    """How a review resolved."""

    UPHELD = "upheld"
    """The boundary stands as written."""
    AMENDED = "amended"
    """Carve-outs were retired or the non-goal was rewritten."""
    EXPANDED = "expanded"
    """The budget or the boundary itself was deliberately widened."""


class ExpiryBasis(StrEnum):
    """Why a carve-out expired."""

    CONDITION_MET = "condition_met"
    SUPERSEDED = "superseded"


class CorrectionKind(StrEnum):
    """What a correction does to the event it targets."""

    SUPERSEDE = "supersede"
    ANNOTATE = "annotate"


class EventBase(UtcModel):
    """Fields common to every ledger event."""

    actor: ActorModel = Field(description="Who authored this event.")
    note: str | None = Field(default=None, description="Free-text context for humans.")
    spec_version: SemVerStr | None = Field(
        default=None,
        description="The spec version this event was authored against, when it differs.",
    )


class ReviewScope(UtcModel):
    """What a review covers.

    Exactly one of ``global_`` or a non-empty ``non_goals`` list, so the scope a
    closure reopens is never ambiguous. ``populate_by_name`` accepts the field
    name as well as the ``global`` alias on input, so ``model_dump()`` without
    ``by_alias=True`` -- which emits the field name -- still round-trips
    through ``model_validate``.
    """

    model_config = ConfigDict(populate_by_name=True)

    global_: StrictBool = Field(default=False, alias="global")
    non_goals: tuple[NonGoalIdStr, ...] = ()

    @model_validator(mode="after")
    def _exactly_one_scope(self) -> ReviewScope:
        if self.global_ and self.non_goals:
            raise ValueError("scope must be either global or scoped to non-goals, not both")
        if not self.global_ and not self.non_goals:
            raise ValueError("scope must be global, or name at least one non-goal")
        return self


class CarveOutRatified(EventBase):
    """A carve-out was ratified against a non-goal."""

    event_type: Literal[EventKind.CARVEOUT_RATIFIED]
    id: CarveOutIdStr
    non_goal: NonGoalIdStr
    title: ShortText
    constraints: Constraints
    ratifiers: Annotated[tuple[ActorModel, ...], Field(min_length=1)]
    expires_at: AwareDatetime | None = Field(
        default=None,
        description="Declared expiry. A statement about the future, so storing it is legal.",
    )
    self_ratified: StrictBool = Field(
        default=False,
        description="Visible, never hidden. Permitted only under the lite profile.",
    )


class CarveOutRetired(EventBase):
    """A carve-out was deliberately withdrawn."""

    event_type: Literal[EventKind.CARVEOUT_RETIRED]
    id: CarveOutIdStr
    reason: Prose


class CarveOutExpired(EventBase):
    """A carve-out's expiry condition was attested as met."""

    event_type: Literal[EventKind.CARVEOUT_EXPIRED]
    id: CarveOutIdStr
    basis: ExpiryBasis
    reason: Prose


class ReviewOpened(EventBase):
    """A charter review was opened, blocking ratification while it stands."""

    event_type: Literal[EventKind.REVIEW_OPENED]
    id: ReviewIdStr
    trigger: ReviewTrigger
    scope: ReviewScope
    artifact: ArtifactPath


class ReviewClosed(EventBase):
    """A charter review was closed by a human.

    Scope is *not* restated here; it is derived from the matching
    ``review.opened``, so the two can never disagree.
    """

    event_type: Literal[EventKind.REVIEW_CLOSED]
    id: ReviewIdStr
    outcome: ReviewOutcome
    closed_by: Annotated[tuple[ActorModel, ...], Field(min_length=1)]
    artifact: ArtifactPath


class CorrectionTarget(UtcModel):
    """The event a correction refers to."""

    event_key: ShortText


class Correction(EventBase):
    """A correction to an earlier event.

    Corrections are how mistakes are fixed under an append-only ledger: a new
    file referencing the old one, never an edit.
    """

    event_type: Literal[EventKind.CORRECTION]
    id: CorrectionIdStr
    corrects: CorrectionTarget
    kind: CorrectionKind
    reason: Prose
    fields: dict[str, object] | None = Field(
        default=None,
        description="Replacement values, for supersede corrections only.",
    )


LedgerEvent = Annotated[
    CarveOutRatified | CarveOutRetired | CarveOutExpired | ReviewOpened | ReviewClosed | Correction,
    Field(discriminator="event_type"),
]

CARVE_OUT_EVENTS = (CarveOutRatified, CarveOutRetired, CarveOutExpired)
REVIEW_EVENTS = (ReviewOpened, ReviewClosed)

__all__ = [
    "CARVE_OUT_EVENTS",
    "KIND_SUFFIX",
    "REVIEW_EVENTS",
    "CarveOutExpired",
    "CarveOutRatified",
    "CarveOutRetired",
    "Correction",
    "CorrectionKind",
    "CorrectionTarget",
    "EventBase",
    "EventKind",
    "ExpiryBasis",
    "LedgerEvent",
    "ReviewClosed",
    "ReviewOpened",
    "ReviewOutcome",
    "ReviewScope",
    "ReviewTrigger",
]
