"""Deterministic JSON Schema generation.

The JSON Schemas are the normative published artifact -- what adopters pin and
what a non-Python implementation builds against -- while the pydantic models
are this engine's internal types. Those two must never drift, so the schemas
are generated from the models, committed, and byte-diffed in CI.

Generation is normalised aggressively because pydantic's emitter is not stable
across minor versions: keys and ``$defs`` are sorted, the ``$id`` and
``$schema`` are stamped, and volatile presentation-only keys are dropped. What
survives is the part that carries meaning.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from charter_core.models.charter import Charter
from charter_core.models.events import LedgerEvent
from charter_core.models.report import EvaluationReport
from charter_core.version import SCHEMA_VERSION

SCHEMA_BASE_URL: Final[str] = "https://charter-kit.dev/schema"
JSON_SCHEMA_DIALECT: Final[str] = "https://json-schema.org/draft/2020-12/schema"

#: Presentation-only keys pydantic emits that carry no validation meaning and
#: churn between releases. Dropping them keeps the committed schema stable.
_VOLATILE_KEYS: Final[frozenset[str]] = frozenset({"title"})

#: Keywords whose *value* is a mapping keyed by author-chosen names rather than
#: by schema keywords. Stripping volatile keys inside these would delete real
#: fields: ``title`` is presentation metadata as a keyword, but a legitimate
#: property name one level down -- and deleting it from ``properties`` while
#: leaving it in ``required`` yields a schema that rejects every valid document.
_NAME_KEYED: Final[frozenset[str]] = frozenset(
    {"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"}
)


def _normalise(node: Any, *, keys_are_names: bool = False) -> Any:
    """Recursively sort keys and drop volatile presentation metadata.

    ``keys_are_names`` marks a mapping whose keys are author-chosen names, so
    they are never treated as schema keywords. It deliberately does not
    propagate past one level: the values under those names are schemas again.
    """
    if isinstance(node, Mapping):
        result: dict[str, Any] = {}
        for key, value in sorted(node.items()):
            if keys_are_names:
                result[key] = _normalise(value)
                continue
            if key in _VOLATILE_KEYS:
                continue
            result[key] = _normalise(value, keys_are_names=key in _NAME_KEYED)
        return result
    if isinstance(node, list):
        return [_normalise(item) for item in node]
    return node


#: Which ``$defs`` model publishes each settings group. A key not appearing in
#: its group's properties is a model/table drift that
#: ``test_settings_key_sets_agree`` (in ``tests/unit/test_settings.py``) would
#: already have failed on, so silently skipping it here is safe -- this stamp
#: is presentation, not the source of truth for what is valid.
_SCHEMA_BLOCK_BY_GROUP: Final[dict[str, str]] = {
    "config": "ConfigBlock",
    "approval_policy": "ApprovalPolicyConfig",
}


def _stamp_effective_defaults(schema: dict[str, Any]) -> dict[str, Any]:
    """Publish the real fallback values on the config block.

    Every ``config`` key is optional and falls through to the profile preset
    and then the schema default, so pydantic emits ``default: null`` -- true
    about the field, useless to a reader trying to learn that the density
    window is 90 days. JSON Schema's ``default`` is an annotation rather than
    behaviour, so stamping the effective value here makes the published schema
    self-documenting without changing what validates.

    Driven by :data:`charter_core.settings.SETTING_SPECS`, the single
    declarative table every tunable is added to exactly once.
    """
    from charter_core.settings import SETTING_SPECS

    defs = schema.get("$defs", {})
    for spec in SETTING_SPECS:
        block = _SCHEMA_BLOCK_BY_GROUP[spec.group]
        properties = defs.get(block, {}).get("properties", {})
        if spec.key in properties:
            properties[spec.key]["default"] = spec.schema_default
    return schema


def _stamp(schema: dict[str, Any], name: str) -> dict[str, Any]:
    """Put ``$schema`` and ``$id`` first, in that order, then the sorted body."""
    body = {k: v for k, v in schema.items() if k not in ("$schema", "$id")}
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_BASE_URL}/{SCHEMA_VERSION}/{name}.schema.json",
        **body,
    }


def generate(adapter: TypeAdapter[Any], name: str) -> dict[str, Any]:
    """Generate one normalised, stamped schema."""
    raw = adapter.json_schema(
        by_alias=True,
        ref_template="#/$defs/{model}",
        mode="validation",
    )
    normalised = _normalise(raw)
    if name == "charter":
        normalised = _stamp_effective_defaults(normalised)
    return _stamp(normalised, name)


#: Every schema this project publishes, by filename stem.
SCHEMAS: Final[dict[str, TypeAdapter[Any]]] = {
    "charter": TypeAdapter(Charter),
    "ledger-event": TypeAdapter(LedgerEvent),
    "evaluation-report": TypeAdapter(EvaluationReport),
}


def generate_all() -> dict[str, dict[str, Any]]:
    """Generate every published schema."""
    return {name: generate(adapter, name) for name, adapter in SCHEMAS.items()}


def serialise(schema: Mapping[str, Any]) -> str:
    """Render a schema to its canonical on-disk form.

    Two spaces, a trailing newline, and no ASCII escaping: the file is meant to
    be read and diffed by humans as well as parsed.
    """
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
