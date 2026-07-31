# Changelog

All notable changes to this project are documented in this file. Format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
will follow [SemVer](https://semver.org/) once a first version is published.
Nothing has been released yet, so entries below are grouped by development
milestone rather than a version number.

## [Unreleased]

### Added — branching model and governance docs
- Created `dev` and `qa` branches alongside `main`, under a GitFlow-lite
  model (`feature|fix|claude/*` → `dev` → `qa` → `main`).
- Added `CONTRIBUTING.md` (branching flow, commit convention, PR checklist),
  `BRANCHING.md` (exact required-checks and branch-protection settings per
  branch — to be applied by hand in GitHub's Settings UI, since no
  available tool can configure them automatically), `CODEOWNERS`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1), and
  `GOVERNANCE.md`.
- `.github/workflows/ci.yml`'s `push` trigger now includes `dev` and `qa`
  alongside `main`.

### Added — repository hygiene
- Enforced coverage floor (95%) in `pyproject.toml`'s `[tool.coverage.report]`
  rather than only in the CI workflow YAML, so `make cov` and CI can never
  silently disagree with each other or with the plan.
- Wired `deptry` and `vulture` into `make all` and CI (`hygiene` job) — both
  were dev dependencies since WP-0 but never actually invoked.
- Added `gitleaks` secret scanning and `pip-audit` dependency vulnerability
  scanning as a new CI `security` job.
- Added `.pre-commit-config.yaml` (ruff, ruff-format, mypy --strict,
  import-linter, plus standard hygiene hooks) for local pre-PR validation.
- Added `README.md`, `LICENSE` (Apache-2.0), `NEXTSTEPS.md`,
  `docs/architecture.md`, and `CLAUDE.md`.

### Fixed
- `ReviewScope` now enforces the "exactly one of global or a non-empty
  non_goals list" invariant its own docstring claimed but never checked, and
  gained `populate_by_name` so `model_dump()` round-trips through
  `model_validate` without requiring `by_alias=True`.
- `Baselines`, `LedgerState`, `PathState`, and `ResolvedSettings` wrap their
  dict-typed fields in `MappingProxyType` at construction — `frozen=True` on
  a dataclass only blocks reassigning an attribute, not mutating a dict
  already sitting behind it, so "never stored, always recomputed" state was
  never actually protected against in-place mutation.
- Renamed `CK.E0403_PROVISIONAL_PROVENANCE` to `CK.W0403_PROVISIONAL_PROVENANCE`
  to match its own code (`CK-W0403`) — the registry's stated
  name-matches-code grep convention had exactly one violation.
- The approval-policy setting provenance pointer (e.g. `min_approvals`)
  recorded `charter.yaml#/config/min_approvals`, one JSON-pointer segment
  short of where the field actually lives under `config.approval_policy`.
- mypy's `files` config named only the two `src` trees; the override meant to
  relax rules for tests targeted a module pattern nothing in `files` ever
  reached, so it was dead configuration from day one. Now scoped to include
  `packages/core/tests`, and the 16 real type gaps this surfaced are fixed.
- A correction event targeting an event that sorts *later* in total order
  now has documented, tested behavior (reported as `CK-E0505`, same as a
  genuinely nonexistent target) instead of being untested emergent behavior
  of how the integrity checker's event-key set happens to be built.

## S3 — the evaluation engine

The complete engine: everything `charter check` needs to turn a charter and
a ledger into a verdict.

### Added
- `ordering.py` — total event order (commit time, commit SHA, path).
- `window.py` — the closed trailing interval for the density trigger.
- `projection.py` — derived `LedgerState`: carve-out and review lifecycle,
  the moot cascade (a retired non-goal's carve-outs stop counting anywhere),
  the genesis exemption (events at or before `adopted_at` are historical:
  exempt from velocity, still counted by level), and the **A2 ratchet
  baseline** — a review closure re-baselines a level trigger to the level
  observed at that moment, and the baseline only ever moves down afterward.
- `triggers/` — `per_id`, `density`, `cumulative`, behind a `Trigger`
  protocol and a registry, so adding one is a registration, not an
  `if/elif` chain. `density` is the one velocity trigger (self-relaxing via
  the window, inclusive `>=`, never ratcheted); `per_id` and `cumulative`
  are level triggers (strict `>` against the A2 baseline).
- `paths.py` — per-non-goal and global amendment-path closure from trigger
  results and open reviews.
- `verdict.py` — the whole guardian contract as one pure function: `PASS`,
  `VIOLATION(NG-x)`, or `REVIEW_REQUIRED`.
- `evaluate.py` — the single engine entry point every surface calls. Total
  over well-formed input; applies the A13 draft exemption mechanically
  (a `ratified` charter blocks on violation, a `draft` charter only warns
  and caps its conformance claim at CL-2).
- `explain.py` — causal trace for a trigger, a path, a setting, or an event,
  rendered from already-computed state rather than recomputed.
- `integrity.py` — referential-integrity diagnostics: unknown non-goal refs,
  orphan/duplicate lifecycle events, unknown correction targets, correction
  chains.
- The settings spec table (`SETTING_SPECS`) as the single declarative source
  every threshold-related consumer (`SCHEMA_DEFAULTS`, `CONFIG_KEYS`,
  `APPROVAL_POLICY_KEYS`, `resolve_settings`) derives from.

## S2 — distribution rename

`charter-core` and `charter-cli` were already registered on PyPI by an
unrelated project. Renamed the published distributions to
`charter-kit-core` / `charter-kit-cli`; import names (`charter_core`,
`charter_cli`) are unchanged, so no source moved. CI packaging now installs
by explicit wheel path rather than resolving by name.

## S1 — engine/schema parity

A property test comparing pydantic and `jsonschema` validation over
generated documents found four real divergences between the engine and its
own published schema (boolean coercion of `"no"`/`"yes"`, numeric
cross-type coercion, `str_strip_whitespace` vs. raw `minLength`
measurement, and `$` vs. lookahead end-of-string anchoring across regex
engines). All four fixed, with the property test now guarding against
recurrence. The YAML anchor/alias/merge-key guard moved from a lexical regex
(which rejected ordinary prose like `"this is *important*"`) to inspecting
the parser's own event stream.

## WP-0 — contract freeze

The initial commit: diagnostic registry (`errors.py`), ports
(`charter_core.ports`), pydantic models for `charter.yaml` and ledger
events, generated JSON Schemas, and CLI exit codes. Establishes the
event-sourced ledger design, the pure-core architecture (enforced by
import-linter and an AST purity test), and the total-function evaluation
contract that everything else in the plan builds on.
