"""charter-kit's pure evaluation engine.

This package performs no I/O. Everything it needs from the outside world
arrives through the Protocols in :mod:`charter_core.ports`, which is what makes
evaluation deterministic and lets the CLI, the GitHub Action, the MCP server,
and the conformance suite share one engine.
"""

from charter_core.diagnostics import Diagnostic, DiagnosticBag, Location
from charter_core.errors import CK, REGISTRY, ErrorDef, Severity
from charter_core.ids import (
    CarveOutId,
    CorrectionId,
    LedgerPath,
    NonGoalId,
    ReviewId,
)
from charter_core.ports import (
    ApprovalFacts,
    ApprovalSource,
    Clock,
    DiffSource,
    LedgerSource,
    PathChange,
    Provenance,
    ProvenanceProvider,
    PullRequestResolver,
)
from charter_core.settings import (
    ApprovalPolicy,
    ResolvedSettings,
    SettingSource,
    resolve_settings,
)
from charter_core.version import CORE_VERSION, SPEC_VERSION, Compatibility, negotiate

__version__ = CORE_VERSION

__all__ = [
    "CK",
    "CORE_VERSION",
    "REGISTRY",
    "SPEC_VERSION",
    "ApprovalFacts",
    "ApprovalPolicy",
    "ApprovalSource",
    "CarveOutId",
    "Clock",
    "Compatibility",
    "CorrectionId",
    "Diagnostic",
    "DiagnosticBag",
    "DiffSource",
    "ErrorDef",
    "LedgerPath",
    "LedgerSource",
    "Location",
    "NonGoalId",
    "PathChange",
    "Provenance",
    "ProvenanceProvider",
    "PullRequestResolver",
    "ResolvedSettings",
    "ReviewId",
    "SettingSource",
    "Severity",
    "__version__",
    "negotiate",
    "resolve_settings",
]
