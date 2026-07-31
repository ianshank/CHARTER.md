"""Shared field types and value objects for the domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Final

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    Strict,
    StringConstraints,
    field_validator,
)

#: A carve-out constraint must say something. The floor is a deliberate,
#: documented heuristic against placeholder text like "n/a" -- CI validates
#: structure, ratifiers validate substance, and SPEC says so plainly.
CONSTRAINT_MIN_LENGTH = 24

#: A boolean that will not accept a string.
#:
#: The codec deliberately preserves ``no`` as the string ``"no"`` rather than
#: letting the YAML 1.1 resolver decide, so that pydantic performs the coercion
#: under a declared type. Pydantic's lax mode then coerces ``"no"`` to ``False``
#: anyway -- which reinstates exactly the hazard the codec exists to prevent,
#: and makes the engine accept a document the published schema (``type:
#: boolean``) rejects. Strict here restores the intended behaviour.
#:
#: Applied only to booleans; strings need no equivalent because pydantic already
#: refuses int-to-str and bool-to-str, and model-wide strictness is *not* the
#: answer -- it would break list-to-tuple and str-to-datetime, both of which
#: JSON and YAML input require.
StrictBool = Annotated[bool, Strict()]


def _reject_cross_type(value: Any) -> Any:
    """Refuse the coercions JSON's type system does not have.

    A string is never a number and a boolean is never an integer -- but Python
    says otherwise on both counts (pydantic's lax mode parses ``"2"`` as ``2``,
    and ``bool`` subclasses ``int``). JSON Schema draws the line where JSON
    does, so an engine that coerces here accepts documents its own published
    schema rejects.

    Numeric widening is deliberately still allowed: JSON Schema's
    ``type: integer`` matches ``2.0``, and ``type: number`` matches ``2``.
    """
    if isinstance(value, str | bool):
        raise ValueError(f"expected a number, not {type(value).__name__}")
    return value


#: An integer as JSON understands it: not a string, not a boolean.
DocInt = Annotated[int, BeforeValidator(_reject_cross_type)]

#: A number as JSON understands it, accepting an integer literal.
DocFloat = Annotated[float, BeforeValidator(_reject_cross_type)]

#: At least one non-whitespace character, anywhere in the value.
#:
#: Deliberately unanchored. ``strip_whitespace`` plus ``min_length`` looks
#: equivalent and is not: pydantic strips before measuring while JSON Schema's
#: ``minLength`` measures the raw string, so ``"  padded  "`` was accepted by
#: the published schema and rejected by the engine. JSON Schema cannot express
#: "strip, then measure", so the length is measured raw on both sides and this
#: pattern carries the "must say something" half of the rule.
#:
#: Anchors are avoided on purpose. ``$`` also matches before a trailing newline
#: in Python's ``re`` but not in Rust's regex crate, which is a second engine
#: disagreement -- and a trailing newline is *normal* here, because a YAML block
#: scalar (``rationale: |``) produces one.
HAS_CONTENT: Final[str] = r"\S"

ConstraintText = Annotated[
    str,
    StringConstraints(min_length=CONSTRAINT_MIN_LENGTH, pattern=HAS_CONTENT),
]
ShortText = Annotated[str, StringConstraints(min_length=1, pattern=HAS_CONTENT)]
Prose = Annotated[str, StringConstraints(min_length=8, pattern=HAS_CONTENT)]
#: True end of string.
#:
#: ``$`` is not it. In Python's ``re`` -- which the ``jsonschema`` library uses
#: -- ``$`` also matches immediately before a trailing newline, so ``"NG-1\n"``
#: satisfies ``^NG-[1-9][0-9]*$``. Rust's regex crate does not allow that, so
#: the engine and the published schema disagreed on exactly those inputs. A
#: negative lookahead for "any character at all" means end-of-string in both,
#: and lookahead is part of ECMA-262, which is the dialect JSON Schema patterns
#: are specified against.
END: Final[str] = r"(?![\s\S])"

#: Rejects any path containing a ``..`` segment, before the path is matched.
#: Without it ``reviews/../../../../etc/passwd.md`` is a valid artifact path.
NO_TRAVERSAL: Final[str] = r"(?!.*\.\.)"

SemVerStr = Annotated[
    str,
    StringConstraints(pattern=rf"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*){END}"),
]
NonGoalIdStr = Annotated[str, StringConstraints(pattern=rf"^NG-[1-9][0-9]*{END}")]
CarveOutIdStr = Annotated[str, StringConstraints(pattern=rf"^CO-[1-9][0-9]*{END}")]
ReviewIdStr = Annotated[str, StringConstraints(pattern=rf"^RV-[1-9][0-9]*{END}")]
CorrectionIdStr = Annotated[str, StringConstraints(pattern=rf"^CR-[1-9][0-9]*{END}")]
ArtifactPath = Annotated[
    str,
    StringConstraints(pattern=rf"^reviews/{NO_TRAVERSAL}[A-Za-z0-9._/-]+\.md{END}"),
]


class StrictModel(BaseModel):
    """Base for every domain model: unknown fields are an error, not a shrug.

    ``str_strip_whitespace`` is deliberately **off**. It mutates authored text
    before validation, which JSON Schema cannot replicate, so it made the engine
    and the published schema disagree at every length boundary. Values are kept
    as written and :data:`HAS_CONTENT` enforces that they say something.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        # Match the engine the `jsonschema` library uses, so a pattern cannot
        # mean one thing to the validator and another to the schema it emits.
        # It also buys lookahead, which Rust's regex crate does not support and
        # which :data:`END` needs.
        regex_engine="python-re",
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
    "DocFloat",
    "DocInt",
    "NonGoalIdStr",
    "Prose",
    "ReviewIdStr",
    "SemVerStr",
    "ShortText",
    "StrictBool",
    "StrictModel",
    "UtcModel",
    "to_utc",
]
