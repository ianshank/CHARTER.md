# Working in this repository

Context for a session picking up work here cold. See `README.md` for what
the project is, `NEXTSTEPS.md` for what's next and what's blocked,
`docs/architecture.md` for how the pieces fit together, and
`docs/implementation-plan-m0.md` for the full historical design record
(rounds 1-3 peer review, the A1-A14 normative decisions).

## The one rule that overrides style preferences

**`charter_core` performs no I/O.** No filesystem, network, subprocess, or
clock access — every external fact arrives through the Protocols in
`charter_core.ports`, and every function is a pure transformation of its
arguments. This is not a convention to remember; it's mechanically enforced:

- `.importlinter` fails the build if `charter_core` imports `charter_cli` or
  anything that isn't itself.
- `packages/core/tests/architecture/test_core_purity.py` is an AST scan that
  fails the build if a `charter_core` module imports `subprocess`, opens a
  file, or calls `datetime.now()`/`time.time()` — the instant to evaluate
  against (`at: datetime`) is always a parameter, never read from the clock.

If a change to `charter_core` needs to read a file or make a network call,
that need belongs in `charter_cli` behind a new or existing Protocol in
`ports.py`, not in core.

## Build and test commands

```console
$ uv sync                          # install the workspace + dev deps
$ HYPOTHESIS_PROFILE=ci uv run pytest -q   # full suite, deterministic property tests
$ make all                         # everything CI runs: lint, types, imports,
                                    # coverage (95% floor), schema drift,
                                    # deptry, vulture, pip-audit
$ make help                        # list every target
$ uv run pre-commit run --all-files  # same checks pre-commit wires into git commit
```

Coverage floor lives in `pyproject.toml`'s `[tool.coverage.report]
fail_under` — one number, so `make cov` and CI can't silently disagree.
Schema regeneration: `make schema`; drift check: `make drift`.

## Where things live

```
packages/core/src/charter_core/
  models/            pydantic models: Charter, LedgerEvent union, EvaluationReport
  codec.py           safe YAML decode (no anchors/aliases/duplicate keys/multi-doc)
  settings.py        SETTING_SPECS -- the one declarative source every
                      threshold-related consumer derives from
  ordering.py         total event order
  window.py           the density trigger's trailing interval
  projection.py       LedgerState derivation -- the A2 ratchet baseline lives here
  integrity.py         referential-integrity diagnostics
  triggers/            per_id, density, cumulative, behind a registry
  paths.py             per-non-goal and global amendment-path closure
  verdict.py            the guardian contract: PASS / VIOLATION / REVIEW_REQUIRED
  evaluate.py            the single engine entry point everything else calls
  explain.py              causal trace, rendered from already-computed state
  errors.py                the CK diagnostic registry every code is defined in

packages/cli/src/charter_cli/
  exit_codes.py       the only thing implemented so far
  main.py, commands/  do not exist yet (S4, blocked -- see NEXTSTEPS.md)

packages/core/tests/builders.py   shared test builders -- the reference for
                                    constructing a valid Charter/ResolvedEvent
                                    without a real git repository behind it
```

## Conventions worth knowing before editing

- **`Fraction`, never `float`**, for every ratio and count comparison. A
  `cumulative_ratio: 0.1` threshold and a `2/20` observed value must compare
  exactly at the boundary.
- **`SETTING_SPECS` is the single source of truth** for every tunable
  (`SCHEMA_DEFAULTS`, `CONFIG_KEYS`, `APPROVAL_POLICY_KEYS`, and
  `resolve_settings()` all derive from it). Add a threshold there first;
  everything else either derives from the table or is cross-checked against
  it by a test.
- **Diagnostic codes**: defined once in `errors.py`'s `CK` enum, named
  `<CODE>_<SLUG>` so the member name's letter prefix matches its `code`'s
  letter prefix (`test_member_name_prefix_matches_its_code_prefix` in
  `test_errors.py` enforces this — it wasn't always true; see
  `CHANGELOG.md`).
- **Frozen dataclasses with dict fields wrap them in `MappingProxyType`** at
  construction (`Baselines`, `LedgerState`, `PathState`, `ResolvedSettings`)
  — `frozen=True` alone only blocks reassigning the attribute, not mutating
  what it points at.
- **mypy `--strict` runs against `packages/core/tests` too**, not just
  `src/`. Test-local helper functions (`ctx()`, `result()`, small builders)
  are allowed to stay loosely typed via a `tests.*` override
  (`disallow_untyped_defs`/`disallow_incomplete_defs`/`disallow_untyped_calls`
  all relaxed there); everything else, including whether the reference port
  fakes in `test_contract_smoke.py` actually satisfy their Protocols, is
  checked at full strictness.
- **Schema/engine parity is tested, not assumed.** `test_schema_export.py`
  and `test_schema_agreement.py` run generated documents through both
  pydantic and `jsonschema` and assert they agree — this is how the S1 work
  package found four real divergences that hand-written fixtures never
  caught.

## What NOT to build speculatively

`NEXTSTEPS.md` has the full list, but the short version: no Dockerfile until
the CLI it would package actually exists, no MCP server or additional
adapters until an external repository adopts the gate, no `.claude/`
agents/skills/hooks (no such convention exists in this repo — this file is
the extent of Claude-specific configuration here). Check `NEXTSTEPS.md`
before adding a new work package rather than inferring one from the design
docs; the design docs describe the full end state, not what's in scope now.
