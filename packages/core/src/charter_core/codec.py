"""Decoding charter and ledger documents, safely.

This is the one place YAML enters the system, and it is deliberately strict.
The default YAML 1.1 dialect coerces ``no`` to ``False``, turns ISO timestamps
into ``datetime`` objects before pydantic ever sees them, and drops duplicate
keys silently, last-wins. In a governance format all three are exploitable: a
duplicate ``budget:`` key that quietly changes policy is a tampering vector,
not a typo.

So: YAML 1.2 core schema, duplicate keys rejected, anchors and aliases
rejected, one document per file, and timestamps left as strings.

That last point is deliberate and narrow. Decoding produces exactly the JSON
data model -- null, bool, number, string, array, object -- because the
published JSON Schema is the normative artifact and an adopter may validate
their charter with any JSON Schema validator. YAML's timestamp resolver has no
JSON counterpart, so a decoded ``datetime`` would make this engine disagree
with the schema it publishes. Booleans and numbers keep their native types,
which JSON has; date-times stay strings carrying ``format: date-time``, and
pydantic parses them under a declared ``AwareDatetime``.

The behaviour is pinned by contract tests rather than by trusting the library,
so it survives a dependency swap.

This module is pure: it decodes text that a caller has already read.
"""

from __future__ import annotations

import re
from io import StringIO
from typing import Any, Final

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError, SafeConstructor
from ruamel.yaml.error import MarkedYAMLError
from ruamel.yaml.nodes import ScalarNode

MAX_DOCUMENT_BYTES: Final[int] = 256 * 1024

_ANCHOR_OR_ALIAS_RE: Final[re.Pattern[str]] = re.compile(
    r"(?m)^\s*[^#\n]*?(?:\s|^)[&*][A-Za-z0-9_-]+"
)
_MERGE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"(?m)^\s*<<\s*:")
_DOC_SEPARATOR_RE: Final[re.Pattern[str]] = re.compile(r"(?m)^---\s*$")


class CodecError(ValueError):
    """A document could not be decoded under the safe dialect."""

    def __init__(self, message: str, *, hazard: str) -> None:
        super().__init__(message)
        self.hazard = hazard


class _JsonModelConstructor(SafeConstructor):
    """A constructor whose output stays inside the JSON data model."""


def _construct_timestamp_as_string(constructor: SafeConstructor, node: ScalarNode) -> str:
    """Keep date-times as written, for pydantic to parse under a declared type."""
    del constructor
    return str(node.value)


_JsonModelConstructor.add_constructor("tag:yaml.org,2002:timestamp", _construct_timestamp_as_string)


def _reader() -> YAML:
    """Build a reader pinned to the safe dialect."""
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    yaml.Constructor = _JsonModelConstructor
    return yaml


def _guard(text: str) -> None:
    """Reject constructs that are unsafe or unreviewable in a governance file."""
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise CodecError(
            f"Document exceeds {MAX_DOCUMENT_BYTES} bytes.",
            hazard="oversize",
        )
    if text.startswith("﻿"):
        raise CodecError(
            "Document starts with a byte order mark; use plain UTF-8.",
            hazard="bom",
        )
    if _MERGE_KEY_RE.search(text):
        raise CodecError(
            "Merge keys ('<<:') are not permitted; write the mapping out in full.",
            hazard="merge_key",
        )
    if _ANCHOR_OR_ALIAS_RE.search(text):
        raise CodecError(
            "Anchors and aliases are not permitted; they make review unreliable.",
            hazard="anchor_alias",
        )
    # A leading '---' is a legal document start; a second one begins a stream.
    separators = _DOC_SEPARATOR_RE.findall(text)
    leading = text.lstrip().startswith("---")
    if len(separators) > (1 if leading else 0):
        raise CodecError(
            "Multi-document streams are not permitted; use one document per file.",
            hazard="multi_document",
        )


def decode(text: str) -> dict[str, Any]:
    """Decode a charter or ledger document into a plain mapping.

    Scalars are returned as written -- strings stay strings, ``no`` stays
    ``"no"``, timestamps stay text -- so that pydantic performs every coercion
    under a declared type rather than the YAML resolver guessing.
    """
    _guard(text)
    try:
        loaded = _reader().load(StringIO(text))
    except DuplicateKeyError as exc:
        raise CodecError(
            f"Duplicate key in document: {exc}",
            hazard="duplicate_key",
        ) from exc
    except MarkedYAMLError as exc:
        raise CodecError(f"Malformed YAML: {exc}", hazard="malformed") from exc

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise CodecError(
            f"Expected a mapping at the document root, found {type(loaded).__name__}.",
            hazard="not_a_mapping",
        )
    return loaded


def normalize_newlines(text: str) -> str:
    """Collapse CRLF and CR to LF.

    The only normalisation applied before generated-block comparison. Anything
    more -- whitespace trimming, Unicode normalisation -- would let real drift
    pass as equal.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")
