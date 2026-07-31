"""charter-core performs no I/O and holds no clock.

import-linter enforces this at the module-import level. These tests enforce it
at the *call* level, because `from datetime import datetime` is a legal import
that becomes a purity violation the moment someone calls `datetime.now()`.

If this file ever fails, the fix is to move the offending code into a CLI
adapter behind a Protocol in `charter_core.ports` -- not to add an exemption.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

CORE_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "charter_core"

#: Calls that reach outside the process or read ambient state.
BANNED_CALLS: dict[str, str] = {
    "datetime.now": "take the instant as a parameter; the CLI owns the clock",
    "datetime.utcnow": "take the instant as a parameter; the CLI owns the clock",
    "datetime.today": "take the instant as a parameter; the CLI owns the clock",
    "time.time": "take the instant as a parameter; the CLI owns the clock",
    "time.monotonic": "core does not measure elapsed time",
    "random.random": "core is deterministic",
    "random.choice": "core is deterministic",
    "random.randint": "core is deterministic",
    "uuid.uuid4": "run ids are supplied by the caller",
    "os.getenv": "configuration arrives through resolve_settings",
    "os.environ": "configuration arrives through resolve_settings",
    "open": "core does not read files; use a LedgerSource",
    "print": "core does not write to streams; return diagnostics",
    "input": "core is non-interactive",
    "exit": "core returns values; it does not terminate the process",
}

BANNED_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "pathlib",
        "subprocess",
        "socket",
        "shutil",
        "tempfile",
        "urllib",
        "httpx",
        "requests",
        "structlog",
        "logging",
        "typer",
        "click",
        "rich",
        "jsonschema",
        "charter_cli",
    }
)


def core_modules() -> list[pathlib.Path]:
    return sorted(CORE_ROOT.rglob("*.py"))


def test_core_root_is_discoverable() -> None:
    """Guards against the scan silently passing because it found nothing."""
    assert CORE_ROOT.is_dir(), f"core source root not found at {CORE_ROOT}"
    assert len(core_modules()) >= 10


def _dotted(node: ast.AST) -> str:
    """Render a call target as a dotted name, e.g. ``datetime.now``."""
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


@pytest.mark.req("REQ-PURITY-001")
@pytest.mark.parametrize("module", core_modules(), ids=lambda p: p.name)
def test_module_makes_no_impure_calls(module: pathlib.Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offences: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _dotted(node.func)
        if not target:
            continue
        # Match both the dotted form and the bare trailing name, so that
        # `now()` imported directly is caught alongside `datetime.now()`.
        for banned, why in BANNED_CALLS.items():
            bare = banned.rsplit(".", 1)[-1]
            if target in (banned, bare) or target.endswith(f".{banned}"):
                offences.append(f"line {node.lineno}: {target}() -- {why}")

    assert not offences, f"{module.name} breaks core purity:\n  " + "\n  ".join(offences)


@pytest.mark.req("REQ-PURITY-002")
@pytest.mark.parametrize("module", core_modules(), ids=lambda p: p.name)
def test_module_imports_nothing_impure(module: pathlib.Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offences: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED_MODULES:
                    offences.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in BANNED_MODULES:
                offences.append(f"line {node.lineno}: from {node.module} import ...")

    assert not offences, f"{module.name} imports impure modules:\n  " + "\n  ".join(offences)


def test_the_scan_actually_detects_violations() -> None:
    """A purity scan that cannot fail is decoration.

    This proves the AST matcher catches what it claims to.
    """
    source = "from datetime import datetime\ndef f():\n    return datetime.now()\n"
    tree = ast.parse(source)
    found = [
        _dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _dotted(node.func)
    ]
    assert "datetime.now" in found
