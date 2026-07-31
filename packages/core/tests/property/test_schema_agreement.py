"""The engine and the published schema must agree on every document.

The JSON Schemas are the normative artifact: an adopter, or a non-Python
implementation, validates against them. If pydantic accepts a document the
schema rejects (or vice versa) then the schema is no longer a contract, and the
whole generated-schema design is decorative.

The existing fixture tests check that agreement on a handful of hand-written
documents. They missed a real divergence -- pydantic's lax mode coerced
``require_review_artifact: "no"`` to ``False`` while the schema said
``type: boolean`` -- because nobody thought to write that fixture. These tests
generate the documents instead, including the hostile shapes a human would not
think to try.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import TypeAdapter, ValidationError

from charter_core.models.charter import Charter
from charter_core.models.events import LedgerEvent

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[4] / "schema"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


CHARTER_VALIDATOR = _validator("charter")
EVENT_VALIDATOR = _validator("ledger-event")
CHARTER_ADAPTER: TypeAdapter[Any] = TypeAdapter(Charter)
EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(LedgerEvent)


def assert_agree(adapter: TypeAdapter[Any], validator: Draft202012Validator, doc: Any) -> None:
    """Both validators must reach the same verdict on ``doc``."""
    try:
        adapter.validate_python(doc)
        pydantic_ok = True
    except ValidationError:
        pydantic_ok = False
    schema_ok = validator.is_valid(doc)
    assert pydantic_ok == schema_ok, (
        f"pydantic={pydantic_ok} jsonschema={schema_ok} for {json.dumps(doc, default=str)[:400]}"
    )


# --------------------------------------------------------------------------
# Scalars chosen to include the coercion hazards, not just well-formed values.
# --------------------------------------------------------------------------
BOOL_LIKE = st.sampled_from(
    [True, False, "true", "false", "yes", "no", "on", "off", "1", "0", 1, 0, None]
)
INT_LIKE = st.sampled_from([0, 1, 2, 90, -1, "2", 2.0, 2.5, True, None])
RATIO_LIKE = st.sampled_from([0.5, 1, 0.1, "0.5", 0, 1.5, -0.5, None])
TEXT_LIKE = st.sampled_from(["x" * 30, "short", "", 12345, True, None, "  padded  "])
NG_ID_LIKE = st.sampled_from(["NG-1", "NG-12", "NG-0", "NG-01", "ng-1", "NG-1\n", "NG-", 1])


@st.composite
def charters(draw: st.DrawFn) -> dict[str, Any]:
    """A charter document, valid or not, biased toward the boundaries."""
    non_goal: dict[str, Any] = {
        "id": draw(NG_ID_LIKE),
        "text": draw(TEXT_LIKE),
        "rationale": draw(TEXT_LIKE),
    }
    if draw(st.booleans()):
        non_goal["budget"] = draw(INT_LIKE)
    if draw(st.booleans()):
        non_goal["status"] = draw(st.sampled_from(["active", "retired", "Active", "", None]))

    document: dict[str, Any] = {
        "spec_version": draw(st.sampled_from(["0.1.0", "1.0.0", "0.1", "v0.1.0", "", None])),
        "charter_version": draw(st.sampled_from(["1.0.0", "0.0.1", "1.0", None])),
        "status": draw(st.sampled_from(["draft", "ratified", "DRAFT", "", None])),
        "non_goals": [non_goal],
    }
    if draw(st.booleans()):
        document["profile"] = draw(
            st.sampled_from(["lite", "standard", "enterprise", "custom", None])
        )
    if draw(st.booleans()):
        config: dict[str, Any] = {}
        if draw(st.booleans()):
            config["require_review_artifact"] = draw(BOOL_LIKE)
        if draw(st.booleans()):
            config["ledger_pr_isolation"] = draw(BOOL_LIKE)
        if draw(st.booleans()):
            config["density_window_days"] = draw(INT_LIKE)
        if draw(st.booleans()):
            config["density_threshold"] = draw(INT_LIKE)
        if draw(st.booleans()):
            config["cumulative_ratio"] = draw(RATIO_LIKE)
        if draw(st.booleans()):
            config["approval_policy"] = {
                "min_approvals": draw(INT_LIKE),
                "require_code_owner": draw(BOOL_LIKE),
            }
        document["config"] = config
    return document


@st.composite
def ratified_events(draw: st.DrawFn) -> dict[str, Any]:
    """A carveout.ratified event, valid or not."""
    actor = {"identity": draw(st.sampled_from(["a", "", None])), "role": "maintainer"}
    constraint = st.sampled_from(["c" * 30, "n/a", "", "  " + "c" * 30 + "  ", None, 42])
    document: dict[str, Any] = {
        "event_type": "carveout.ratified",
        "id": draw(st.sampled_from(["CO-1", "CO-0", "co-1", "CO-1\n", None])),
        "non_goal": draw(NG_ID_LIKE),
        "title": draw(TEXT_LIKE),
        "constraints": {
            "bounding": draw(constraint),
            "mechanism": draw(constraint),
            "safety": draw(constraint),
            "sequencing": draw(constraint),
        },
        "actor": actor,
        "ratifiers": [actor],
    }
    if draw(st.booleans()):
        document["self_ratified"] = draw(BOOL_LIKE)
    if draw(st.booleans()):
        document["expires_at"] = draw(
            st.sampled_from(
                ["2027-01-01T00:00:00Z", "2027-01-01", "not-a-date", "", None, 1735689600]
            )
        )
    return document


@pytest.mark.req("REQ-SCHEMA-003")
@settings(max_examples=300)
@given(charters())
def test_charter_validators_agree(document: dict[str, Any]) -> None:
    assert_agree(CHARTER_ADAPTER, CHARTER_VALIDATOR, document)


@pytest.mark.req("REQ-SCHEMA-003")
@settings(max_examples=300)
@given(ratified_events())
def test_event_validators_agree(document: dict[str, Any]) -> None:
    assert_agree(EVENT_ADAPTER, EVENT_VALIDATOR, document)


@pytest.mark.req("REQ-SCHEMA-003")
@pytest.mark.parametrize(
    "artifact",
    [
        "reviews/2026-07-30.md",
        "reviews/../../../../etc/passwd.md",
        "reviews/a/../../secret.md",
        "reviews/ok.md\n",
        "reviews/..md",
        "reviews/nested/ok.md",
    ],
)
def test_artifact_paths_agree_and_reject_traversal(artifact: str) -> None:
    """A review artifact must stay under reviews/, in both validators."""
    document = {
        "event_type": "review.opened",
        "id": "RV-1",
        "trigger": "density",
        "scope": {"global": True},
        "artifact": artifact,
        "actor": {"identity": "a", "role": "maintainer"},
    }
    assert_agree(EVENT_ADAPTER, EVENT_VALIDATOR, document)
    if ".." in artifact or artifact.endswith("\n"):
        assert not EVENT_VALIDATOR.is_valid(document), f"{artifact!r} escaped the guard"


@pytest.mark.req("REQ-SCHEMA-003")
@pytest.mark.parametrize("value", ["NG-1", "NG-1\n", "NG-01", "ng-1", "NG-0", " NG-1", "NG-1 "])
def test_identifier_anchoring_agrees_across_regex_engines(value: str) -> None:
    r"""`$` matches before a trailing newline in Python re but not in Rust regex.

    That made ``NG-1\\n`` valid to the published schema and invalid to the
    engine. Both must now reject it.
    """
    document = {
        "spec_version": "0.1.0",
        "charter_version": "1.0.0",
        "status": "ratified",
        "non_goals": [{"id": value, "text": "x" * 30, "rationale": "y" * 30}],
    }
    assert_agree(CHARTER_ADAPTER, CHARTER_VALIDATOR, document)
    if value != "NG-1":
        assert not CHARTER_VALIDATOR.is_valid(document), f"{value!r} should not be a valid id"


@pytest.mark.req("REQ-SCHEMA-003")
@pytest.mark.parametrize(
    "rationale",
    ["  padded  ", "y" * 30, "        ", "block scalar text\n", "short", ""],
)
def test_text_length_is_measured_the_same_way_by_both(rationale: str) -> None:
    """`strip_whitespace` + `minLength` is not expressible in JSON Schema.

    Pydantic used to strip before measuring while the schema measured the raw
    string, so ``"  padded  "`` was accepted by one and rejected by the other.
    """
    document = {
        "spec_version": "0.1.0",
        "charter_version": "1.0.0",
        "status": "ratified",
        "non_goals": [{"id": "NG-1", "text": "x" * 30, "rationale": rationale}],
    }
    assert_agree(CHARTER_ADAPTER, CHARTER_VALIDATOR, document)


@pytest.mark.req("REQ-LEDGER-010")
@given(value=BOOL_LIKE)
def test_boolean_fields_never_accept_a_string(value: Any) -> None:
    """Pinned regression for the defect the fixture tests missed.

    The codec preserves ``no`` as a string so pydantic can decide under a
    declared type. Lax mode then turned it into ``False``, reinstating the very
    YAML 1.1 hazard the codec exists to prevent -- and disagreeing with the
    published schema, which has always said ``type: boolean``.
    """
    document = {
        "spec_version": "0.1.0",
        "charter_version": "1.0.0",
        "status": "ratified",
        "non_goals": [{"id": "NG-1", "text": "x" * 30, "rationale": "y" * 30}],
        "config": {"require_review_artifact": value},
    }
    assert_agree(CHARTER_ADAPTER, CHARTER_VALIDATOR, document)
    if isinstance(value, str):
        with pytest.raises(ValidationError):
            CHARTER_ADAPTER.validate_python(document)
