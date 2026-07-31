"""Shared field types and value objects for the domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

#: A carve-out constraint must say something. The floor is a deliberate,
#: documented heuristic against placeholder text like "n/a" -- CI validates
#: structure, ratifiers validate substance, and SPEC says so plainly.
CONSTRAINT_MIN_LENGTH = 24

ConstraintText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=CONSTRAINT_MIN_LENGTH),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Prose = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8)]
SemVerStr = Annotated[
    str,
    StringConstraints(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"),
]
NonGoalIdStr = Annotated[str, StringConstraints(pattern=r"^NG-[1-9][0-9]*$")]
CarveOutIdStr = Annotated[str, StringConstraints(pattern=r"^CO-[1-9][0-9]*$")]
ReviewIdStr = Annotated[str, StringConstraints(pattern=r"^RV-[1-9][0-9]*$")]
CorrectionIdStr = Annotated[str, StringConstraints(pattern=r"^CR-[1-9][0-9]*$")]
ArtifactPath = Annotated[
    str,
    StringConstraints(pattern=r"^reviews/[A-Za-z0-9._/-]+\.md$"),
]


class StrictModel(BaseModel):
    """Base for every domain model: unknown fields are an error, not a shrug."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class ActorModel(StrictModel):
    """Who performed an action, as both identity and role.

    Both are required: a role alone cannot support an audit trail, and a bare
    identity cannot express policy.
    """

    identity: ShortText
    role: ShortText


class Constraints(StrictModel):
    """The four constraints that make a carve-out bounded.

    Modelled as required, substantive fields rather than a list of labels: a
    list would let the gate verify four words are present and call it
    completeness, which is checkbox theatre.
    """

    bounding: ConstraintText = Field(description="What the carve-out does and does not reach.")
    mechanism: ConstraintText = Field(description="How it is implemented and who owns it.")
    safety: ConstraintText = Field(
        description="What prevents it causing harm, and how that is verified."
    )
    sequencing: ConstraintText = Field(description="When it expires or what supersedes it.")


def to_utc(value: datetime) -> datetime:
    """Normalise an aware datetime to UTC."""
    return value.astimezone(UTC)


class UtcModel(StrictModel):
    """Base for models carrying instants, normalising them to UTC."""

    @field_validator("*", mode="after")
    @classmethod
    def _normalise_instants(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return to_utc(value)
        return value


__all__ = [
    "CONSTRAINT_MIN_LENGTH",
    "ActorModel",
    "ArtifactPath",
    "AwareDatetime",
    "CarveOutIdStr",
    "ConstraintText",
    "Constraints",
    "CorrectionIdStr",
    "NonGoalIdStr",
    "Prose",
    "ReviewIdStr",
    "SemVerStr",
    "ShortText",
    "StrictModel",
    "UtcModel",
    "to_utc",
]
