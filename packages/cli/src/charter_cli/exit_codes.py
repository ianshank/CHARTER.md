"""The frozen exit-code contract.

CI configurations, adopter scripts, and documentation all reference these
numbers, so they are part of the public interface and change only with a major
version.

One collision is deliberate and must be handled rather than avoided: Click
reserves 1 for ``Abort`` and 2 for ``UsageError``. Since 1 is VIOLATION here, a
Ctrl-C must never be allowed to look like a charter violation -- ``main`` traps
``click.exceptions.Abort`` and re-maps it explicitly, and a test pins that.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes returned by every ``charter`` command."""

    OK = 0
    """No error-severity diagnostics."""

    VIOLATION = 1
    """A normative rule was violated. This is what the gate fails on."""

    USAGE = 2
    """Bad invocation. Matches Click's own usage-error code deliberately."""

    INPUT_INVALID = 3
    """Malformed charter.yaml or ledger event; the document could not be read."""

    ENVIRONMENT = 4
    """Shallow clone, missing git, unreadable repository, or a symlinked ledger."""

    SPEC_UNSUPPORTED = 5
    """charter.yaml declares a spec_version major this engine does not implement."""

    INTERRUPTED = 130
    """Interrupted by signal. Never conflated with VIOLATION."""

    INTERNAL = 70
    """Unexpected exception. Always prints the run id for correlation."""


#: Codes that mean "the engine ran and reached a conclusion", as opposed to
#: failing before it could evaluate anything.
CONCLUSIVE: frozenset[ExitCode] = frozenset({ExitCode.OK, ExitCode.VIOLATION})
