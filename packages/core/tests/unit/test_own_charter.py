"""charter-kit dogfoods its own format.

The repo's own charter.yaml must be a real, valid Charter document, decoded
through the same safe codec and validated against the same model every
adopter's charter.yaml goes through.

There is no CLI yet to run `charter check` against this file (see
NEXTSTEPS.md), so this is deliberately narrower than the eventual S5
self-enforcement milestone -- it proves the document is well-formed, not
that the gate passes against it. That milestone needs the CLI.
"""

from __future__ import annotations

import pathlib

from pydantic import TypeAdapter

from charter_core.codec import decode
from charter_core.models.charter import Charter

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CHARTER_PATH = _REPO_ROOT / "charter.yaml"

_CHARTER_ADAPTER: TypeAdapter[Charter] = TypeAdapter(Charter)


def test_own_charter_yaml_exists_at_the_repo_root() -> None:
    assert _CHARTER_PATH.is_file(), f"expected a charter.yaml at {_CHARTER_PATH}"


def test_own_charter_yaml_decodes_under_the_safe_codec() -> None:
    """The same guard rails every adopter's document goes through.

    No anchors, aliases, duplicate keys, or multi-document streams.
    """
    document = decode(_CHARTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    assert document["status"] == "draft"


def test_own_charter_yaml_validates_against_the_real_model() -> None:
    document = decode(_CHARTER_PATH.read_text(encoding="utf-8"))
    charter = _CHARTER_ADAPTER.validate_python(document)

    assert charter.status == "draft"
    assert charter.profile == "lite"
    assert {ng.id for ng in charter.active_non_goals} == {"NG-1", "NG-2"}


def test_own_charter_conformance_is_capped_at_cl2_while_draft() -> None:
    """A repeat of A13 against the real document, not a synthetic fixture.

    This is the actual charter that will need to flip to `ratified` before
    this project can claim more.
    """
    from charter_core.profiles import get_profile

    document = decode(_CHARTER_PATH.read_text(encoding="utf-8"))
    charter = _CHARTER_ADAPTER.validate_python(document)
    profile = get_profile(charter.profile)

    conformance_ceiling = 2 if charter.status == "draft" else profile.max_conformance_level
    assert conformance_ceiling == 2
