# charter-kit

[![CI](https://github.com/ianshank/CHARTER.md/actions/workflows/ci.yml/badge.svg)](https://github.com/ianshank/CHARTER.md/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**A governance framework that makes project-charter rules computable.** Non-goal
IDs, budgeted carve-outs, and review triggers stop being prose a reviewer has
to remember and become an append-only ledger a pure evaluation engine checks
on every change.

## What exists today

This is pre-release, mid-build software. Being direct about that:

| Piece | Status |
|---|---|
| **Engine** (`charter_core`) — ordering, projection, triggers, verdict, evaluate, explain | Built, tested, 99%+ branch coverage |
| **JSON Schemas** (`schema/`) — the normative contract for `charter.yaml`, ledger events, and evaluation reports | Built, generated from the same pydantic models the engine validates against, dual-validation tested |
| **CLI** (`charter_cli`) — `init`, `lint`, `check`, `verdict`, `explain` | Not yet implemented. `exit_codes.py` exists; the commands do not. |
| **Git adapters** — provenance from `--first-parent` commit history | Not yet implemented |
| **GitHub Action / gate** | Not yet implemented |
| **MCP server** | Not yet implemented |

If you're looking for a tool you can install and run against your own
repository today, it isn't ready yet. If you're looking at the engine design,
the schemas, or the test suite, all of that is real and exercised.

## The idea

A project charter usually lives as prose: a `NON_GOALS.md` or a paragraph in a
design doc that says "we will not do X, except in these narrow, budgeted
cases." Nobody enforces it. Six months later there are twelve exceptions, no
one remembers the budget, and the boundary has quietly dissolved.

charter-kit turns that prose into three things:

1. **`charter.yaml`** — the non-goals, their budgets, and the thresholds that
   govern them. Declarations only; nothing derived is stored here.
2. **An append-only ledger** (`ledger/*.yaml`) — one event per file:
   a carve-out ratified, retired, or expired; a review opened or closed. Ledger
   provenance comes from git history itself (which commit, on the default
   branch, first introduced the file), so it cannot be backdated by editing a
   field.
3. **A pure evaluation engine** — replays the ledger against the charter as of
   any instant and returns one of three answers: `PASS`,
   `VIOLATION(NG-1,NG-2)`, or `REVIEW_REQUIRED`. Deterministic, replayable, and
   the same function every surface (CLI, CI gate, agent tool) calls.

The engine is where the actual design effort has gone. In particular:

- **The ratchet baseline (A2).** When a review closes, a trigger's threshold
  re-baselines to the level observed at that moment and only ever moves down
  afterward. A team standing still after a review doesn't get flagged again
  for the same level; a team eroding further does; a team retiring a carve-out
  permanently lowers the bar. Getting this wrong either deadlocks (the trigger
  fires again immediately after every review) or removes the ceiling entirely
  (a closed review resets the count to zero and erosion restarts from
  nothing) — both were real designs in earlier drafts, both are now dedicated
  regression tests.
- **Exact arithmetic.** Every ratio and count comparison uses `Fraction`, never
  `float`, so a `cumulative_ratio: 0.1` threshold and a `2/20` observed value
  compare exactly at the boundary instead of drifting on binary
  representation.
- **A pure core, enforced structurally.** `charter_core` performs no I/O — no
  filesystem, network, subprocess, or clock access. This isn't a style
  preference stated in a docstring: an [import-linter](.importlinter) contract
  and an AST-based test both fail the build if a `charter_core` module ever
  imports `subprocess`, `pathlib.Path.open`, or anything from `charter_cli`.

## Using the engine today

There's no CLI yet, but the engine is a normal Python library:

```python
from datetime import datetime, timezone
from charter_core.evaluate import evaluate
from charter_core.models.charter import Charter
from charter_core.profiles import get_profile
from charter_core.settings import resolve_settings
from pydantic import TypeAdapter

charter = TypeAdapter(Charter).validate_python(
    {
        "spec_version": "0.1.0",
        "charter_version": "1.0.0",
        "status": "ratified",
        "non_goals": [
            {
                "id": "NG-1",
                "text": "The system does not target platforms other than GitHub.",
                "rationale": "Control-plane primitives differ enough to make it premature.",
                "budget": 2,
            }
        ],
    }
)

profile = get_profile(charter.profile)
settings = resolve_settings(config=None, profile_name=profile.name, profile_preset=profile.preset)

report = evaluate(
    charter=charter,
    events=[],  # ResolvedEvent objects -- see packages/core/tests/builders.py
    at=datetime.now(timezone.utc),
    settings=settings,
    run_id="example-1",
)

print(report.verdict.rendered)  # "PASS"
```

`packages/core/tests/builders.py` is the reference for constructing
`ResolvedEvent`s (ratifications, retirements, reviews) without a real git
repository behind them — it's what the engine's own test suite uses.

## Repository layout

```
packages/
  core/   charter_core — the pure evaluation engine (this is the real thing)
  cli/    charter_cli  — CLI + git/filesystem adapters (scaffolded, not built)
schema/   generated JSON Schemas for charter.yaml, ledger events, reports
docs/     design and planning documents
```

See [`docs/architecture.md`](docs/architecture.md) for a diagram of how the
pieces fit together, and [`NEXTSTEPS.md`](NEXTSTEPS.md) for what's actually
next and what's blocking it.

## Development

```console
$ uv sync                # install the workspace + dev dependencies
$ make all                # lint, types, import contracts, coverage, schema drift, deptry, vulture, pip-audit
$ uv run pytest -q        # just the test suite
```

`make help` lists every target. `.pre-commit-config.yaml` wires the same
checks (minus coverage, which needs the full suite) into `git commit` via
`uv run pre-commit install`.

## What charter-kit does not do

- It does not replace human judgment about whether a boundary is worth
  keeping — it makes the *bookkeeping* of an already-agreed boundary
  computable, nothing more.
- It does not infer non-goals from code. Every non-goal, budget, and threshold
  is declared by a human in `charter.yaml`.
- It targets GitHub in v1. Other forges, and an enterprise profile beyond what
  `packages/core/src/charter_core/profiles.py` already has, are deliberately
  out of scope until at least one repository other than this one runs the
  gate as a required check.

## License

Apache-2.0 for code. See [`LICENSE`](LICENSE).
