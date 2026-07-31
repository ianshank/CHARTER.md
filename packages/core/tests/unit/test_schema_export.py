"""The published JSON Schemas must never drift from the pydantic models.

The schemas are the normative artifact -- what adopters pin and what a
non-Python implementation builds against -- while the models are this engine's
internal types. These tests are what makes it impossible for the two to
disagree without CI noticing.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import TypeAdapter, ValidationError

from charter_core.models.charter import FORBIDDEN_DERIVED_FIELDS, Charter
from charter_core.models.events import LedgerEvent
from charter_core.schema_export import SCHEMAS, generate, generate_all, serialise
from charter_core.settings import SCHEMA_DEFAULTS
from charter_core.version import SCHEMA_VERSION

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[4] / "schema"


def committed(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


@pytest.mark.req("REQ-SCHEMA-001")
@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_committed_schema_matches_the_models(name: str) -> None:
    """This is the drift gate. If it fails, run `charter schema export`."""
    on_disk = (SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8")
    regenerated = serialise(generate(SCHEMAS[name], name))
    assert on_disk == regenerated, (
        f"{name}.schema.json is stale. Regenerate it and commit the result."
    )


@pytest.mark.req("REQ-SCHEMA-002")
@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schema_id_is_versioned_and_permanent(name: str) -> None:
    """`$id` URLs are the one commitment that cannot be walked back."""
    schema = committed(name)
    assert schema["$id"] == f"https://charter-kit.dev/schema/{SCHEMA_VERSION}/{name}.schema.json"
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schema_is_itself_valid(name: str) -> None:
    Draft202012Validator.check_schema(committed(name))


def test_generation_is_deterministic() -> None:
    """Two runs must be byte-identical, or the drift gate would be flaky."""
    assert serialise(generate_all()["charter"]) == serialise(generate_all()["charter"])


class TestNormalisationDoesNotEatRealFields:
    """Regression guard for a bug the dual-validation test caught.

    ``title`` is presentation metadata as a schema keyword and a legitimate
    field name one level down. Stripping it indiscriminately deleted
    ``CarveOutRatified.title`` from ``properties`` while leaving it in
    ``required``, producing a schema that rejected every valid carve-out.
    """

    @pytest.mark.req("REQ-SCHEMA-004")
    def test_a_field_named_title_survives(self) -> None:
        definition = committed("ledger-event")["$defs"]["CarveOutRatified"]
        assert "title" in definition["properties"]
        assert "title" in definition["required"]

    @pytest.mark.req("REQ-SCHEMA-004")
    def test_schema_level_title_metadata_is_still_stripped(self) -> None:
        definition = committed("ledger-event")["$defs"]["CarveOutRatified"]
        assert "title" not in definition, "schema-level title metadata should be dropped"

    @pytest.mark.req("REQ-SCHEMA-004")
    @pytest.mark.parametrize("name", sorted(SCHEMAS))
    def test_every_required_field_is_declared(self, name: str) -> None:
        """The invariant the bug broke: `required` may only name real properties."""
        schema = committed(name)
        for definition_name, definition in schema.get("$defs", {}).items():
            declared = set(definition.get("properties", {}))
            required = set(definition.get("required", []))
            missing = required - declared
            assert not missing, f"{name}/{definition_name} requires undeclared {sorted(missing)}"


class TestChartersDeclarationsOnly:
    @pytest.mark.req("REQ-CHARTER-004")
    @pytest.mark.parametrize("field", sorted(FORBIDDEN_DERIVED_FIELDS))
    def test_derived_fields_are_rejected(self, field: str) -> None:
        """Storing a derived value creates a second source of truth."""
        document = {
            "spec_version": "0.1.0",
            "charter_version": "1.0.0",
            "status": "draft",
            "non_goals": [{"id": "NG-1", "text": "Does not do X.", "rationale": "Because Y."}],
            field: "anything",
        }
        with pytest.raises(ValidationError):
            TypeAdapter(Charter).validate_python(document)
        assert not Draft202012Validator(committed("charter")).is_valid(document)

    @pytest.mark.req("REQ-CHARTER-005")
    def test_config_publishes_effective_defaults(self) -> None:
        """An adopter reading the schema must learn the real fallback values."""
        properties = committed("charter")["$defs"]["ConfigBlock"]["properties"]
        assert (
            properties["density_window_days"]["default"] == SCHEMA_DEFAULTS["density_window_days"]
        )
        assert properties["density_threshold"]["default"] == SCHEMA_DEFAULTS["density_threshold"]
        assert properties["cumulative_ratio"]["default"] == float(
            SCHEMA_DEFAULTS["cumulative_ratio"]
        )


class TestLedgerEventUnion:
    @pytest.mark.req("REQ-LEDGER-001")
    def test_every_event_kind_is_a_union_variant(self) -> None:
        from charter_core.models.events import EventKind

        schema = committed("ledger-event")
        assert len(schema["oneOf"]) == len(EventKind)

    @pytest.mark.req("REQ-LEDGER-001")
    def test_no_variant_stores_provenance(self) -> None:
        """Provenance is derived; a stored field would be an unverified claim."""
        forbidden = {"ratified_at", "commit", "pr", "status", "opened", "closed"}
        for name, definition in committed("ledger-event")["$defs"].items():
            present = forbidden & set(definition.get("properties", {}))
            assert not present, f"{name} stores derived provenance: {sorted(present)}"


VALID_CHARTER = {
    "spec_version": "0.1.0",
    "charter_version": "1.0.0",
    "status": "ratified",
    "profile": "standard",
    "non_goals": [
        {
            "id": "NG-1",
            "text": "The system does not target platforms other than GitHub in v1.",
            "rationale": "Control-plane primitives differ enough that abstraction is premature.",
            "budget": 2,
        }
    ],
    "config": {"density_window_days": 45},
}

VALID_EVENT = {
    "event_type": "carveout.ratified",
    "id": "CO-1",
    "non_goal": "NG-1",
    "title": "Read-only export path for the audit team",
    "constraints": {
        "bounding": "Applies only to read paths under /export; no write surface is exposed.",
        "mechanism": "Feature-flagged behind export.v2; the flag is owned by the platform team.",
        "safety": "No PII leaves the region; verified by the residency test in tests/export.",
        "sequencing": "Expires when the NG-1 review RV-2 closes, or on 2027-01-01.",
    },
    "actor": {"identity": "maintainer", "role": "maintainer"},
    "ratifiers": [{"identity": "maintainer", "role": "maintainer"}],
}


@pytest.mark.req("REQ-SCHEMA-003")
@pytest.mark.parametrize(
    ("name", "adapter", "document", "expected_valid"),
    [
        ("charter", TypeAdapter(Charter), VALID_CHARTER, True),
        ("charter", TypeAdapter(Charter), {**VALID_CHARTER, "status": "nonsense"}, False),
        ("charter", TypeAdapter(Charter), {**VALID_CHARTER, "non_goals": []}, False),
        ("ledger-event", TypeAdapter(LedgerEvent), VALID_EVENT, True),
        (
            "ledger-event",
            TypeAdapter(LedgerEvent),
            {
                **VALID_EVENT,
                "constraints": dict.fromkeys(
                    ("bounding", "mechanism", "safety", "sequencing"), "n/a"
                ),
            },
            False,
        ),
        ("ledger-event", TypeAdapter(LedgerEvent), {**VALID_EVENT, "id": "CO-0"}, False),
    ],
)
def test_pydantic_and_jsonschema_agree(
    name: str, adapter: TypeAdapter, document: dict, expected_valid: bool
) -> None:
    """The two validators must never disagree.

    Disagreement means the published schema and the engine enforce different
    rules, which is the exact failure the generated-schema design exists to
    prevent -- so it must be a loud test failure, not a silent divergence.
    """
    try:
        adapter.validate_python(document)
        pydantic_valid = True
    except ValidationError:
        pydantic_valid = False

    validator = Draft202012Validator(committed(name), format_checker=FormatChecker())
    jsonschema_valid = validator.is_valid(document)

    assert pydantic_valid == expected_valid
    assert pydantic_valid == jsonschema_valid, (
        f"pydantic={pydantic_valid} jsonschema={jsonschema_valid} for {name}"
    )
