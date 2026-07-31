# charter-kit — Round-2 Peer Review + M0-prime Implementation Plan

## Context

Two deliverables in one document.

**Why:** the user asked for a second objective peer review of the charter-kit v0 framework, then an
implementation plan built on the research. charter-kit makes project-charter governance (non-goal IDs,
budgeted carve-outs, review triggers) computable and CI-enforced, and exposes charter state to AI agents
as first-class SDD context.

**Where things stand:** the repo (`ianshank/CHARTER.md`) is greenfield — branch
`claude/charter-kit-framework-review-ei8up6` holds only `charter-kit-v0-draft.md` (the design) and
`charter-kit-v0-peer-review.md` (round-1 findings F1–F11: three blockers — append-only invariant vs.
mutable status records, provenance chicken-and-egg on `ratified_at`/`commit`, stored path state with no
reopen semantics — plus TOCTOU, checkbox-theatre §7.1 constraints, and self-asserted ledger fields).

**Intended outcome:** a shippable M0-prime that implements the review-corrected design — event-sourced
ledger, derived provenance, computed path state — with an enterprise-grade agents/skills layer, strict
quality gates, and a traceability mechanism that makes unimplemented or untested normative statements
fail CI rather than surface at audit.

---

# Part 1 — Round-2 Peer Review

## New findings

**R2-1 — Conformance suite is sequenced after the adapters it validates.** Fixtures and golden files sit
in M3, adapters in M2. Worse, given the full-test-suite requirement, conformance fixtures *are* the
integration tests — they must exist alongside core. Move a minimal conformance harness into M0.

**R2-2 — Event ordering and tie-breaking are undefined.** Two ratifications in the same second make
"the (budget+1)th proposal" order-dependent. Define a total order — `(committer_timestamp, commit_sha,
event_file_path)` — and property-test the ordering laws.

**R2-3 — Gate↔CLI version skew has no mechanism.** Local-green/CI-red when the action and the local CLI
resolve different core versions. Resolve tooling from `spec_version`: fail unknown MAJOR with a stable
error code, warn on newer MINOR.

**R2-4 — ID discipline and referential integrity are unchecked.** ID reuse after retirement must be
banned (stable IDs is a headline feature); the gate needs dangling-reference checks (CO→NG,
correction→prior event); and ledger files must never be renamed, since git-derived provenance depends on
path identity.

**R2-5 — The generated-block protocol is unspecified.** Marker syntax, byte-exact vs. normalized
comparison, CRLF handling, and behavior when a marker is deleted or duplicated all need normative text.

**R2-6 — Gate observability is absent.** Emit a structured JSON evaluation report (facts used, triggers
fired, evaluation instant, core/spec versions) as a check artifact plus a human step summary, with a
stable error taxonomy (`CK-Exxx`). This is simultaneously the enterprise audit trail and the debugging
surface — it is not a nice-to-have.

**R2-7 — MCP state freshness.** `charter://state` must disclose its source commit; a stale checkout
otherwise yields confidently wrong guardian verdicts.

**R2-8 — Onboarding is undesigned.** `charter init --profile lite` reaching CL-2 in minutes is
make-or-break for the adoption gate that governs M2+, yet `init` appears only as one word in a CLI list.

**R2-9 — Enterprise-pitch hygiene gaps.** No LICENSE, SECURITY.md/disclosure policy, threat model, or
pre-1.0 ADR process anywhere in the draft.

## Calibrations of round 1 (objective self-correction)

**F4 narrows — and the correction matters.** Time passage alone can never invalidate a green gate: events
leaving the 90-day window only *relax* constraints; only new merges tighten them. The real TOCTOU exposure
is concurrent interleaved ratifications, not merge delay. The merge-queue requirement stands with a
smaller blast radius than round 1 implied. This monotonicity property — *time only relaxes; only events
tighten* — is provable and becomes a property-tested core invariant.

**F1 and F2 are load-bearing for each other.** "First commit introducing the entry" is only crisp under
file-per-event; under a single mutable YAML it is ambiguous with rebase merges. Adopt them together, plus
the no-rename rule.

**Nothing retracted; no new blockers.** Round 2 contributes sequencing corrections, a determinism spec,
a version-skew mechanism, and observability requirements — all folded into Part 2.

---

# Part 1b — Round-3 Peer Review (final pass)

This pass audits the design *including rounds 1 and 2's own recommendations*. It found one defect in my
round-2 fix, two genuine state-model bugs nobody caught in three passes, and a one-line enforcement
bypass. All are folded into Part 2 as A-items.

## Blocking findings

### R3-1 — The round-2 watermark fix (A2) destroys the erosion ceiling. Replace reset with ratchet.

Round 2 introduced review watermarks to break the deadlock: after `review.closed`, all trigger counting
ignores events at or before the watermark. That terminates closure, but it silently converts every
constraint into a rate limit and removes any absolute cap on carve-out accumulation.

Concretely: NG-1 has budget 2 and three active carve-outs, so the path closes. A review opens and closes.
All three carve-outs are now pre-watermark, so the per-ID count reads 0 — while three carve-outs remain
active. Two more may now be added before closing again. Iterate: a repo can reach fifty active carve-outs
with a review every third one. **The charter exists to prevent boundary erosion, and rate-limiting does
not prevent erosion — it only meters it.** The same flaw hits the cumulative trigger, which is precisely
the one meant to be the absolute guard.

The root error is treating three semantically different triggers identically. Separate them:

- **Velocity trigger — density.** Measures amendment *rate*. It is already self-relaxing via the sliding
  window (A1), so it needs no watermark at all. Round 2's watermark was redundant here.
- **Level triggers — per-ID budget and cumulative ratio.** These measure *stock*, not flow. A thing
  called a "budget" that resets on review is not a budget.

**Corrected rule (replaces A2): level triggers ratchet, they do not reset.** A level trigger fires when
`level > threshold` **and** `level > baseline(scope)`, where `baseline` is set to the level observed at
the most recent covering `review.closed` and thereafter tracks downward — it is the minimum level
observed since (improvements lock in; a retirement permanently lowers the bar). Baseline is derived from
the event stream at check time, never stored, so Invariant 6 holds.

This terminates (standing still after a review never re-fires), preserves an absolute ceiling (further
erosion always re-fires), keeps monotonicity (adding a carve-out can only tighten; retiring can only
relax), and is more auditable than watermarks — `charter explain` can say *"cumulative 0.62, threshold
0.50, baseline 0.60 at RV-2 → fires because 0.62 > 0.60."* It also states the honest division of labor:
**the system's job is to force the conversation, not to dictate its outcome.** A review may retire
carve-outs, amend the non-goal, or explicitly raise the budget — all three are legitimate, and all three
are recorded.

### R3-2 — Bootstrap paradox: adopting charter-kit immediately closes the amendment path.

A repo adopting the framework back-fills the carve-outs it already lives with. Every one of those ledger
files is introduced by the adoption commit, so under F2's derived-provenance rule they all carry the same
timestamp. Three or more back-filled carve-outs therefore land in a single 90-day window and trip the
density trigger on day one — the new adopter's first experience is a closed amendment path and a
mandatory review of decisions made years earlier.

This is not a corner case; it is the *default* adoption path, and it directly threatens the external-CL-3
adoption gate that governs M2+. **Fix (A11): a genesis marker.** `charter.yaml` declares `adopted_at`, or
a `ledger/GENESIS.yaml` event records it; events whose derived provenance is at or before the genesis
commit are historical and exempt from velocity triggers, though they still count toward level triggers
(they *are* real active carve-outs — the ceiling should see them; only the rate should not).

### R3-3 — Retiring a non-goal can close the global path as a side effect.

Nothing defines what happens to carve-outs on a retired non-goal. They remain `active` in the ledger, so
the cumulative trigger's numerator holds them while the denominator (active non-goals) drops. Retiring
NG-1 — an ordinary, legitimate act of scope cleanup — can therefore spike the ratio past threshold and
close the amendment path repo-wide, with no carve-out having been proposed at all.

**Fix (A12): retiring a non-goal cascades its carve-outs to a derived `moot` status**, excluded from
every count. Derived, not stored, and testable as a single conformance case.

### R3-4 — `status: draft` is a one-line enforcement bypass.

§8 defines `status: draft` as "triggers computed but non-blocking," scoped as a pre-1.0 policy for this
repo. But `status` is a field in *every* adopter's `charter.yaml`. Any repo can set one line and keep a
green required check while all policy enforcement is off — a repo can claim CL-3 "Enforced" with
enforcement disabled. This is the badge-hunting risk from the draft's own register, except it needs no
repo-settings tampering at all.

**Fix (A13):** `draft` relaxes *only* trigger-based blocking. All structural checks — schema,
append-only, referential integrity, render freshness, ledger isolation — stay blocking in every status.
CL-3 MUST require `status: ratified`; a draft repo is capped at CL-2. The evaluation report carries
`status` so any badge or attestation is qualified by it.

## Major findings

**R3-5 — `charter_version` has no defined semantics and no enforcement.** It is declared as "semver of
this charter's content," but nothing says what forces a major versus a minor bump, and no check verifies
one happened. An unenforced version field is decoration. Either define bump rules and enforce them in the
gate against the merge base (non-goal added or text changed → MINOR; non-goal removed or semantics
narrowed → MAJOR; carve-out events alone → no bump) or drop the field. Recommend defining and enforcing:
it is cheap and it is exactly the kind of thing the framework claims to make computable.

**R3-6 — Conformance claims must be profile- and status-qualified.** "CL-3" under `lite` with
self-ratification permitted is a materially weaker claim than "CL-3" under `enterprise` with dual
ratification — and (per R3-4) "CL-3 draft" is not a claim at all. The report already carries `profile`
and `status`; require badges and attestations to render them, e.g. `CL-3 (standard, ratified)`. A bare
"CL-3" should be non-conforming.

**R3-7 — Capability parity is inverted between agents and humans.** The MCP surface offers
`validate_carveout` with trigger simulation ("would this close the path?"), but the CLI has no
equivalent — a human cannot ask the question an agent can. That inverts Invariant 3, which holds that
agents are ergonomics and the CI gate is the control. Add `charter simulate --with-event <file>` (or
`check --dry-run --with-event`) so the human surface is a superset of the agent surface, and have the MCP
tool call it rather than reimplement it.

**R3-8 — The precedence chain is asserted but not computable.** §6 declares Charter > constitution >
spec > plan > tasks as normative, yet nothing detects a contradiction between a charter and a Spec Kit
constitution — that would require semantic comparison. The draft is rigorous about computability
everywhere else, so this stands out. Downgrade it honestly to an *authoring* rule for humans and agents,
in the same paragraph as F9's "the gate enforces the amendment process, not the boundary itself."

## Moderate findings

- **Provenance is unstable below CL-3.** Derived provenance assumes default-branch history is immutable;
  a force push rewrites every timestamp retroactively. Branch protection blocks this at CL-3, so document
  that CL-1/CL-2 provenance is advisory, and consider recording the previous head in the post-merge
  report so a rewrite is at least detectable.
- **The evaluation report is unsigned.** For regulated adopters the audit trail should be attestable —
  in-toto/SLSA provenance over the report artifact. M4, but design the report as an attestation subject
  now (stable canonical serialization, content digest) so it does not need reshaping later.
- **License the SPEC separately from the code.** A standard others may implement should be quotable:
  CC-BY-4.0 for `SPEC.md` and the schemas, Apache-2.0 for the code. Also decide the project/trademark
  name posture before 1.0 rather than after adopters cite it.
- **Ledger scale.** Provenance derivation is one git call per ledger file; a mature repo with hundreds of
  events on a large history will feel it. Batch the derivation in a single `git log` pass over `ledger/`
  and cache by tree SHA. Worth building right in M0 — it is much harder to retrofit than to measure.

## Verdict after three passes

The design survives. Rounds 1 and 2 found blockers in the *original* draft; round 3 found one in my own
round-2 fix, which is the more useful result — the watermark reset would have shipped a governance system
that meters erosion while appearing to cap it. With A1–A13 frozen, the remaining risk is execution rather
than specification.

---

# Part 2 — Implementation Plan (M0-prime)

## Settled decisions

| Decision | Choice |
|---|---|
| Language | Python 3.11+ |
| Scope | M0-prime: SPEC skeleton, schemas, core, CLI, gate action, conformance harness, examples/lite, dogfood charter, CI, agents + skills layer, read-only MCP |
| Branching | Create `main` from the current review commit; implementation lands on `claude/charter-kit-framework-review-ei8up6` via draft PR |
| Agent/skill distribution | **Both** — portable `agents/` + `skills/` are source of truth; shipped as an installable plugin *and* materialized into `.claude/` with a `--check` drift gate |
| MCP | Read-only in M0 (`charter://state`, `check_budget`, `validate_carveout`); write tools milestone-guarded |
| Quality gates | Strict from day one — `mypy --strict`, broad ruff, core ≥95% branch coverage, dead-code + drift + traceability gates |

### Stack

| Concern | Choice | Rationale |
|---|---|---|
| Packaging | **uv workspace**; dists `charter-core`, `charter-cli`, `charter-mcp`; hatchling backend | One resolver for dev, CI, and the action's install path |
| Domain layer | **pydantic v2**; JSON Schema **generated from models**, committed, byte-diffed in CI | One source of truth for types; the committed schema is what adopters and non-Python implementations pin, and drift becomes impossible |
| Schema validation | `jsonschema` Draft 2020-12 **with `FormatChecker`** | `format: date-time` is annotation-only by default |
| YAML | **ruamel.yaml**, YAML 1.2 core schema, duplicate keys rejected, scalars stay strings | PyYAML silently coerces `no`→`False` and timestamps→`datetime`, and silently drops duplicate keys — all three verified in this environment, all three governance-relevant |
| CLI | typer + rich | Typer's exit code 2 for usage errors aligns with the exit contract |
| Logging | structlog (JSON + console), CLI-only | Core stays pure; the evaluation report is core's observability surface |
| Tests | pytest, hypothesis, pytest-cov (branch), plain JSON goldens | Goldens stay diffable by non-Python implementers |
| Quality | ruff, mypy --strict, **import-linter**, deptry, vulture, interrogate, zizmor | import-linter is what mechanically enforces core purity |
| MCP | FastMCP | Read tools wired straight to core |

**ADR-0002 closes the OPA/conftest question from round 1: rejected.** The work is dominated by
git-derived provenance, total ordering, the report artifact, and the error taxonomy. Rego would still
need a Python fact extractor and would split the `CK-Exxx` registry across two languages. Recorded as a
decision, not relitigated per-lane.

---

## A. Normative semantics frozen before any parallel work

Round 1 left several points "defensible either way; silence is not." Parallel subagents cannot each
choose. These are decided in WP-0 and written into SPEC.md.

- **A1 — Velocity vs. level triggers (the taxonomy everything else hangs off).** `density` is a
  **velocity** trigger: it measures amendment rate, is self-relaxing as the window slides, and needs no
  review baseline. `per_id` and `cumulative` are **level** triggers: they measure stock, and a review
  re-baselines them rather than clearing them. SPEC states this distinction and its justification.
- **A2 — Level triggers ratchet; they never reset (R3-1, replaces round 2's watermarks).** A level
  trigger fires when `level > threshold` **and** `level > baseline(scope)`. `baseline` is set to the
  level observed at the most recent covering `review.closed`, then tracks downward — the minimum level
  observed since, so retirements permanently lower the bar. Derived at check time from the event stream,
  never stored. This terminates (standing still after a review does not re-fire), preserves an absolute
  erosion ceiling (further erosion always re-fires), and keeps monotonicity (adding a carve-out can only
  tighten, retiring can only relax). An open review still blocks all ratification repo-wide — that is a
  hard gate, not a trigger.
- **A3 — Window is a closed trailing interval on UTC instants:** `at - window_days ≤ ts ≤ at`, exact
  `timedelta`, no calendar-day truncation. Boundary inclusivity is config (`window_boundary`, default
  `inclusive`).
- **A4 — Counting mode differs per trigger, deliberately.** Per-ID and cumulative count *concurrent
  active* carve-outs; density counts *lifetime ratifications inside the window* (velocity is not undone
  by a later retirement). SPEC states the asymmetry and its justification.
- **A5 — Zero active non-goals → cumulative ratio is 0** (no boundary to erode), with warning
  `CK-W1003`. Ratio arithmetic is exact `Fraction` with integer cross-multiplication — no float compares
  at the boundary.
- **A6 — Budget-relative closure:** NG-x closes when `active_count(NG-x) > budget(NG-x)`. Budget resolves
  per-NG → config → profile → schema default.
- **A7 — Provenance is `--first-parent` on the default branch only.** First-parent is load-bearing for
  forgery resistance: under a true merge, other walks attribute the file to a topic-branch commit whose
  committer date is attacker-settable via `GIT_COMMITTER_DATE`. Off the default ref, results are
  `provisional: true` and advisory (F4).
- **A8 — Expiry has two derived sources:** `expires_at` on the ratified event (a declaration about the
  future — legal to store) and an attested `carveout.expired` event. Effective expiry = `min(derived, attested)`.
- **A9 — Ledger PR isolation (F11):** a PR adding files under `ledger/` may touch only `ledger/**`,
  `reviews/**`, and generated blocks in `CHARTER.md`. Config `ledger_pr_isolation`, default `true`.
- **A10 — Non-goal lifecycle stays declarative in `charter.yaml`** for v0.1, protected by diff rules
  against the merge base (ids never removed or renumbered, `retired → active` forbidden, text changes
  require a review artifact). Promoting it to events is a documented v0.2 seam. **A9 is what closes the
  denominator-dilution vector** — because a ledger PR may not also touch `charter.yaml`, nobody can add
  trivial non-goals and a carve-out in one atomic change to dodge the cumulative ratio. SPEC must say this
  explicitly; the interaction is load-bearing and non-obvious.
- **A11 — Genesis marker (R3-2).** `charter.yaml` declares `adopted_at` (or `ledger/GENESIS.yaml` records
  it). Events whose derived provenance is at or before the genesis commit are historical: **exempt from
  velocity triggers, still counted by level triggers.** Without this, back-filling existing carve-outs at
  adoption trips density on day one and every new adopter's first experience is a closed path.
- **A12 — Retiring a non-goal cascades its carve-outs to a derived `moot` status (R3-3)**, excluded from
  every count. Otherwise ordinary scope cleanup spikes the cumulative ratio and closes the global path
  with no carve-out proposed.
- **A13 — `draft` status relaxes only trigger-based blocking (R3-4).** Structural checks — schema,
  append-only, referential integrity, render freshness, ledger isolation — stay blocking in every status.
  **CL-3 MUST require `status: ratified`**; a draft repo is capped at CL-2. The report carries `status`
  and `profile`, and conformance claims must render both (`CL-3 (standard, ratified)`); a bare "CL-3" is
  non-conforming.
- **A14 — `charter_version` bump rules are enforced (R3-5)** against the merge base: non-goal added or
  text changed → MINOR required; non-goal removed or narrowed → MAJOR required; carve-out events alone →
  no bump. An unenforced version field would be decoration.

---

## B. Repository layout

```
/
├── SPEC.md                     GENERATED from spec/v0.1/requirements.yaml. RFC 8174, REQ-AREA-NNN anchors
├── spec/v0.1/requirements.yaml Structured normative source: id, text, applicability[CL-1..4], rationale, tests
├── CHARTER.md  charter.yaml    Dogfood charter (status: draft per §8) + declarations
├── README.md CONTRIBUTING.md SECURITY.md LICENSE
├── pyproject.toml uv.lock Makefile .gitattributes .importlinter .pre-commit-config.yaml
│
├── ledger/                     Append-only event files + README (filename grammar, never rename)
├── reviews/                    Review artifacts referenced by review.* events
│
├── schema/                     GENERATED, committed, byte-diffed in CI
│   charter.schema.json · ledger-event.schema.json · evaluation-report.schema.json
│   agent-role.schema.json · conformance-case.schema.json
│
├── packages/
│   ├── core/src/charter_core/  PURE library — no fs, net, subprocess, env, clock, randomness
│   │   version errors diagnostics ids ports settings profiles codec schema_export
│   │   models/{common,charter,events,state,report}.py
│   │   ordering window projection integrity paths verdict approvals evaluate explain
│   │   triggers/{__init__,base,per_id,density,cumulative}.py      registry, not if/elif
│   │   render/{markers,blocks,renderers}.py · agents/{role,materialize}.py · conformance.py
│   ├── cli/src/charter_cli/
│   │   main context exit_codes · obs/{logging,console}.py
│   │   adapters/{git_runner,git_provenance,git_diff,fs_ledger,yaml_io,clock,github_approvals}.py
│   │   commands/{init,lint,check,render,verdict,explain,schema_cmd,agents_cmd,report_cmd,
│   │             conformance_cmd,spec_cmd,version_cmd}.py · templates/
│   └── mcp/src/charter_mcp/    FastMCP: server, resources, tools, guards (read-only in M0)
│
├── actions/charter-gate/       action.yml + scripts/preflight.sh + README + CHANGELOG
│
├── agents/                     Portable roles (source of truth)
│   _shared/{data-not-instructions,verdict-contract}.md
│   charter-guardian.md · amendment-drafter.md · review-facilitator.md
├── skills/                     Portable skills (source of truth) — 5 skills, see §F
├── adapters/claude-code/       adapter.yaml + templates/{agent.md.j2,skill.md.j2}
├── plugin/                     Distributable Claude Code plugin (GENERATED)
│   .claude-plugin/plugin.json · skills/** · agents/**
├── .claude/                    Materialized in-repo (GENERATED, drift-checked)
│   agents/*.md · skills/*/SKILL.md
│
├── conformance/cases/{pure,repo,agents}/<case>/{case.yaml,expected/}
├── examples/lite/              charter.yaml, CHARTER.md, ledger/, gate workflow
├── docs/                       Sphinx+MyST site: start-here/ tutorial/ how-to/ reference/ explanation/
│                               architecture provenance generated-blocks cli-contract agents
│                               threat-model adopting work-packages.yaml compat.yaml adr/0001-0010
│                               error-codes.md + traceability.md + reference/** (GENERATED)
├── governance/                 CODEOWNERS-policy release-policy rfcs/0000-template
└── .github/
    CODEOWNERS dependabot.yml PULL_REQUEST_TEMPLATE/{carveout,review}.md
    workflows/{ci,charter-gate-reusable,dogfood,post-merge-verify,nightly,release}.yml
```

---

## C. charter-core — key contracts

**Purity is mechanically enforced**, three ways: an `.importlinter` forbidden contract (core may not
import `os`, `pathlib`, `subprocess`, `socket`, `httpx`, `structlog`, `typer`, `charter_cli`); an AST-scan
test for `datetime.now`, `time.time`, `random.*`, `open(`, `Path(`; and ruff `flake8-datetimez` repo-wide
plus banned-api scoped to core.

```python
# ports.py — the reuse seam. CLI, MCP, conformance, and tests each construct these differently.
@dataclass(frozen=True, slots=True)
class Provenance:
    commit_sha: str; committed_at: datetime      # tz-aware UTC
    first_parent: bool; provisional: bool

class ProvenanceProvider(Protocol):
    def provenance_for(self, paths: Sequence[LedgerPath]) -> Mapping[LedgerPath, Provenance | None]: ...
    def is_shallow(self) -> bool: ...
    def default_ref(self) -> str: ...

class LedgerSource(Protocol):
    def documents(self) -> Iterator[tuple[LedgerPath, Mapping[str, Any]]]: ...
class DiffSource(Protocol):
    def changed_paths(self, base: str, head: str) -> Sequence[PathChange]: ...   # A/M/D/R
class ApprovalSource(Protocol):          # F6 — interface in M0, live API call in M1
    def approvals_for(self, pr_number: int) -> ApprovalFacts: ...

# settings.py — the "no hard-coded values" guarantee, made auditable
class SettingSource(StrEnum):
    EXPLICIT_CONFIG = "config"; PROFILE = "profile"; SCHEMA_DEFAULT = "schema_default"

@dataclass(frozen=True, slots=True)
class ResolvedSettings:
    density_window_days: int; density_threshold: int
    cumulative_ratio: Fraction; default_carveout_budget: int
    window_boundary: Literal["inclusive", "exclusive"]
    require_review_artifact: bool; ledger_pr_isolation: bool
    approval_policy: ApprovalPolicy
    provenance: Mapping[str, SettingProvenance]      # per-key: value, source, detail

def resolve_settings(*, config: ConfigBlock | None, profile: ProfileName) -> ResolvedSettings: ...
```

Precedence `explicit config > profile preset > schema default` is implemented once and property-tested.
`charter explain settings` prints the provenance map — that is what makes "no hard-coded values"
auditable rather than merely asserted.

```python
# models/events.py — no stored provenance anywhere
class EventKind(StrEnum):
    CARVEOUT_RATIFIED="carveout.ratified"; CARVEOUT_RETIRED="carveout.retired"
    CARVEOUT_EXPIRED="carveout.expired";   REVIEW_OPENED="review.opened"
    REVIEW_CLOSED="review.closed";         CORRECTION="correction"

class Constraints(BaseModel):        # F5 — keyed object, each field min_length 24
    bounding: ConstraintText; mechanism: ConstraintText
    safety: ConstraintText;   sequencing: ConstraintText

LedgerEvent = Annotated[CarveOutRatified | CarveOutRetired | CarveOutExpired
                        | ReviewOpened | ReviewClosed | Correction,
                        Field(discriminator="event_type")]

@dataclass(frozen=True, slots=True)
class ResolvedEvent:
    path: LedgerPath; event: LedgerEvent; provenance: Provenance
    @property
    def event_key(self) -> str: ...   # "CO-1.ratified" — MUST equal the file stem

# ordering / window / projection
def order_key(e: ResolvedEvent) -> tuple[datetime, str, str]: ...    # R2-2 total order
def in_window(ts, *, at, days, boundary) -> bool: ...                # A3
def project(events: Sequence[ResolvedEvent], *, at: datetime) -> LedgerState: ...  # derives
                                    # statuses + watermarks; nothing stored

# triggers — registry with an extension seam, not an if/elif chain
class Trigger(Protocol):
    id: ClassVar[str]
    def evaluate(self, ctx: TriggerContext) -> Sequence[TriggerResult]: ...
TRIGGERS: Final[Registry[Trigger]]
def register(trigger_id: str) -> Callable[[type[Trigger]], type[Trigger]]: ...

@dataclass(frozen=True, slots=True)
class TriggerResult:
    trigger_id: str; fired: bool; scope: TriggerScope
    observed: int | Fraction; threshold: int | Fraction; margin: int | Fraction
    contributing_events: tuple[str, ...]      # causal trace — makes `explain` nearly free
    diagnostics: tuple[Diagnostic, ...]

# verdict.py — THE agent contract (see §F: agents narrate this, they never infer it)
def compute_verdict(path_state: PathState, touched: Sequence[NonGoalId]) -> Verdict: ...

# evaluate.py — the single engine entry point
def evaluate(*, charter: Charter, events: Sequence[ResolvedEvent], at: datetime,
             settings: ResolvedSettings, run_id: str,
             approvals: ApprovalFacts | None = None,
             diff: Sequence[PathChange] | None = None,
             touched_non_goals: Sequence[NonGoalId] = ()) -> EvaluationReport: ...
```

`evaluate` is total — it never raises for policy problems, it returns diagnostics; it raises only on
programmer error. The injected `at` and injected ports are what make it deterministic, reusable across
CLI/action/MCP/tests, and free of hidden state.

**Error registry (`errors.py`)** is the hub the SPEC, exit codes, report schema, fixtures, and
traceability gate all key off. Ranges: `E01xx` version negotiation · `E02xx` charter declarations ·
`E03xx` ledger structure · `E04xx` environment/provenance · `E05xx` referential integrity · `E06xx`
render · `E07xx` policy/trigger · `E08xx` approvals · `E09xx` milestone guards · `W1xxx` warnings. Each
entry carries `code, title, severity, spec_ref, remediation, exit_code`. Two tests bind it: every
`spec_ref` must resolve to a real `REQ-` anchor, and every code must be produced by at least one test or
fixture.

---

## D. Schemas, CLI, and the gate

**`charter.schema.json` — declarations only.** `spec_version`, `charter_version`, `status`, `profile`,
`non_goals[]` (id/text/rationale/status/budget), and a `config` block holding *every* threshold
(`density_window_days` 90, `density_threshold` 3, `cumulative_ratio` 0.5, `default_carveout_budget` 2,
`window_boundary`, `require_review_artifact`, `ledger_pr_isolation`, `approval_policy`). Absent by
design, each with a targeted `CK-E0201` migration hint rather than a generic schema error:
`amendment_path`, `carveouts`, `reviews`, `last_full_review`, `ratified_at`, `commit`, `pr`.

**`ledger-event.schema.json` — discriminated union on `event_type`**, `additionalProperties: false`
throughout, no provenance fields. Filename grammar is normative:
`^ledger/(CO|RV|CR)-[1-9][0-9]*\.(ratified|retired|expired|opened|closed|correction)\.yaml$`, stem must
equal `{id}.{kind}`, unique case-insensitively, no symlinks. `review.closed` derives its scope from the
matching `review.opened` rather than restating it.

**`evaluation-report.schema.json`** (R2-6) carries `run_id`, `evaluated_at`, versions, per-key settings
provenance, facts (events with order indices, counts, watermarks), trigger results, path state, verdict,
diagnostics, result, exit code.

**Generated-block protocol** (R2-5): markers are plain HTML comments
`<!-- charter-kit:begin:<block_id> -->` / `:end:` with **no embedded hash** (a hash is a second source of
truth that can itself drift). Comparison regenerates the body, normalizes CR/CRLF→LF only, compares
bytes. Failure modes each get a code: missing marker `E0601`, duplicate id `E0602`, unbalanced `E0603`,
drift `E0604`, nested `E0605`, unknown id `E0606`. Content outside markers is never touched.

**CLI.** Global flags on every command: `--verbose/-v`, `--debug`, `--quiet`, `--json`, `--no-color`,
`--log-format text|json`, `--run-id`, `--config`, `--profile`, `--at`, `--repo`; each mirrored by a
`CHARTER_*` env var with precedence flag > env > config > profile > schema default.

| Command | Purpose |
|---|---|
| `init` | Scaffold charter.yaml, CHARTER.md, ledger/, gate workflow, CODEOWNERS, PR templates by profile (R2-8) |
| `lint` | No-git checks: schema, filename grammar, §7.1 completeness, referential integrity, forbidden stored-derived keys |
| `check` | Full evaluation: provenance, ordering, triggers, path state, diff rules, render freshness; emits the JSON report |
| `render` | Generated blocks — `--check` or `--write` |
| `verdict` | **The deterministic agent tool** — `PASS` / `VIOLATION(NG-x)` / `REVIEW_REQUIRED` |
| `simulate` | `--with-event <file>` — "would this close the path?" (R3-7: the human surface must be a superset of the agent surface; MCP's `validate_carveout` calls this rather than reimplementing it) |
| `explain` | Causal trace for a trigger, path, setting, or event — including the ratchet baseline and why it did or didn't fire |
| `schema export --check` | Regenerate or drift-check published schemas |
| `agents materialize --check` | Regenerate or drift-check `.claude/` and `plugin/` |
| `report validate\|summary` | Validate a report; render the GitHub step summary (keeps bespoke Python out of the action) |
| `conformance run` | Run the suite; `--update-goldens` regenerates |
| `spec trace --check` | **The gap-analysis command** — REQ → module → test matrix |

Exit codes: `0` OK · `1` VIOLATION (what the gate fails on) · `2` USAGE · `3` INPUT_INVALID ·
`4` ENVIRONMENT (shallow clone, missing git) · `5` SPEC_UNSUPPORTED · `70` INTERNAL. Every non-zero exit
prints at least one `CK-Exxx`; every code is snapshot-tested per command.

**The gate** is a composite action plus a reusable-workflow wrapper. Composite is fast and transparent to
security review, and `uv` gives a pinned hermetic install; composite actions cannot declare
`permissions`, which is exactly why the reusable workflow ships alongside and owns `permissions` and
`fetch-depth: 0`. Steps: preflight (shallow detection → `CK-E0401` with remediation, optional
`--unshallow`, default-ref sanity) → SHA-pinned `setup-uv` → `uv tool install charter-cli==<pinned>` →
`lint` → `check --report` → `report summary --format github >> $GITHUB_STEP_SUMMARY` → upload artifact →
exit with the captured code. Permissions: `contents: read` always; `pull-requests: read` when
`verify-approvals` is on (**this is F6's correction to the draft's `contents: read, checks: write`**);
`issues: write` only in post-merge verification. `post-merge-verify.yml` recomputes state on every push
to the default branch and files an issue on breach (F4).

---

## E. Testing strategy

- **Unit** — table-driven per trigger, plus settings, ordering, window, projection, integrity, verdict,
  approvals, markers, explain, codec dialect, schema export, version negotiation.
- **Property (hypothesis)** — order laws (irreflexive, transitive, total); **monotonicity** (advancing
  `at` never tightens; adding a relaxing event never tightens); window boundary inclusivity; density
  order-invariance; settings precedence; and a **dual-validation agreement** test where every generated
  fixture must be accepted-or-rejected identically by pydantic and by `jsonschema`.
- **Architecture** — core purity AST scan; registry completeness (`set(TRIGGERS) == {per_id, density,
  cumulative}`, each with ≥1 unit test and ≥1 conformance case); every CK code documented.
- **Integration (real git)** — temp repos with pinned `GIT_COMMITTER_DATE`, covering merge/squash/rebase,
  file recreated after delete, shallow clone, rename detection.
- **E2E** — `init → lint → render → check` on `examples/lite` with pinned `--at`.
- **Conformance** — three families of declarative cases with JSON goldens; the portable artifact a
  non-Python implementation would use to claim conformance.

**Conformance cases that matter most** (~55 total):

*Trigger semantics.* `per-id-at-budget` / `per-id-over-budget` (the off-by-one in both directions);
`density-exact-90` paired with an `exclusive`-boundary sibling over identical data, proving the threshold
is configuration and not a constant; `cumulative-boundary` at exactly 1/2 with exact `Fraction`
arithmetic; `retire-frees-budget`, proving both halves of A4's asymmetry in one case;
`same-timestamp-tiebreak`.

*The A2 ratchet — the highest-value cluster in the suite.* `ratchet-no-refire` (review closes at level 3,
level stays 3 → does not re-fire: the deadlock test); `ratchet-further-erosion-refires` (level 4 → fires,
proving the ceiling survives review, which is what round-2's reset design got wrong);
`ratchet-improvement-locks-in` (retire to level 2 → baseline drops, so returning to 3 fires again);
`density-not-ratcheted` (a velocity trigger relaxes purely by window slide, no baseline involved).

*State-model bugs from round 3.* `genesis-backfill` (five carve-outs introduced by the adoption commit →
no density fire, but the cumulative level still sees them — A11); `ng-retire-cascades-moot` (retiring
NG-1 does not spike the ratio — A12); `draft-status-structural-still-blocks` (a `draft` repo with a
malformed ledger event still fails — A13) paired with `draft-caps-at-cl2`;
`charter-version-bump-required` (NG text edited without a MINOR bump → fail — A14).

*Structure and provenance.* `constraints-incomplete` with a `safety: "n/a"` variant that also fails,
proving §7.1 is not checkbox theatre; `provenance-merge-commit`, proving first-parent defeats a forged
`GIT_COMMITTER_DATE` on a topic branch; `shallow-clone`; `ledger-file-renamed`; `mixed-pr-isolation`
(also the denominator-dilution guard per A10); `generated-block-drift`; `crlf-normalization` on Windows CI.

---

## F. Agents and skills — enterprise layer

**The architectural move that makes this safe: the guardian's verdict is a pure core function, not model
judgment.** `compute_verdict(path_state, touched) -> Verdict` is unit-tested Python; `charter verdict`
exposes it; the agent's job is to *call it and narrate the result*, never to infer one. That is what
gives a non-deterministic role a deterministic, golden-tested contract.

**Portable roles** in `agents/` carry YAML frontmatter validated against `agent-role.schema.json`, plus
two shared includes that must appear byte-identically in every role: `_shared/data-not-instructions.md`
(charter prose is DATA, never INSTRUCTIONS — the prompt-injection posture, since non-goal rationale and
carve-out text are contributor-authored) and `_shared/verdict-contract.md` (the verdict grammar and the
"call `charter verdict`, never infer" rule).

**Five skills**, each `skills/<name>/SKILL.md` with progressive-disclosure reference files:
`carveout-authoring` (walks §7.1 to a valid ratified event), `charter-review-facilitation` (evidence pack
to a closable review), `charter-gate-triage` (failing report + CK codes → minimal fix),
`conformance-fixture-authoring`, `adapter-authoring` (new trigger/profile/adapter via the registries).

**Materialization targets — two, from one source:**

- `.claude/agents/<name>.md` — frontmatter `name` (required; lowercase and hyphens, no colons),
  `description` (required), `tools`, `disallowedTools`, `model`, `color`.
- `.claude/skills/<name>/SKILL.md` — frontmatter `description` (the trigger text), optional `name`,
  `allowed-tools`, `disallowed-tools`, `model`, `argument-hint`.
- `plugin/` — `.claude-plugin/plugin.json` (`name`, `description`, `version` tracking SPEC) with
  `skills/` and `agents/` at the **plugin root, not inside `.claude-plugin/`**; validated with
  `claude plugin validate --strict`.

Two constraints from the platform shape the design and must be honored:

1. **Plugin-provided subagents ignore `permissionMode`, `hooks`, and `mcpServers`.** Least privilege
   must therefore be expressed *only* through `tools` / `disallowedTools`, which work identically in
   both targets. A test asserts the guardian's tool allowlist intersects the write-capable deny-list in
   exactly zero places (Invariant 5).
2. **Enterprises may set `disableSkillShellExecution`.** No skill may depend on shell-injection blocks;
   all data comes from `charter verdict` / `explain` / `check --json` invoked as ordinary tool calls.

Governance of these artifacts: CODEOWNERS-routed, versioned with the SPEC, golden-verdict conformance
tested (`cases/agents/`), and drift-gated — `charter agents materialize --check` fails CI if `.claude/`
or `plugin/` diverges from `agents/` and `skills/`. `docs/adopting.md` documents the managed-settings
path for organizations that want to pin the plugin marketplace (`strictKnownMarketplaces`,
`allowedChannelPlugins`).

---

## G. Work packages for parallel subagents

`docs/work-packages.yaml` holds machine-readable path ownership; a CI script asserts every changed path
maps to exactly one WP. **No two packages own the same file.**

**Phase I — contract freeze (sequential, one agent, must merge before anything else starts).**

**WP-0** owns `schema/**`, core's `{version,errors,diagnostics,ids,ports,settings,profiles,codec,
schema_export}.py` and `models/**`, `cli/exit_codes.py`, **all** `pyproject.toml` + `uv.lock` + tool
config, `docs/cli-contract.md`, ADRs 0001–0010, the `spec/v0.1/requirements.yaml` skeleton and its
requirement-ID registry, the A1–A14 decisions, and `docs/work-packages.yaml`. It also declares the complete dependency set — lanes may not add
dependencies; they file a contract amendment to the integration lane. That rule is what prevents
`uv.lock` conflicts across ten parallel branches. Done when `schema export --check` and `mypy --strict`
are green and a contract smoke test constructs every model and every port fake.

**Phase II — parallel lanes, all depending only on WP-0** (points ≈ half an agent-day):

| WP | Owns | Done test | Pts |
|---|---|---|---|
| 1 Engine | ordering, window, projection, integrity, paths, verdict, approvals, evaluate, explain, triggers/**; core unit+property tests | Property tests green; ≥95% branch coverage on owned modules | 8 |
| 2 Render + agent transforms | render/**, agents/** (core), `docs/generated-blocks.md` | `render(render(x)) == render(x)`; all 6 marker failure modes emit their code | 5 |
| 3 CLI commands | main, context, commands/**, obs/**, templates/** | Exit-code snapshot per command; flag-precedence test; e2e on examples/lite | 8 |
| 4 Git/FS adapters | adapters/**, integration tests, `docs/provenance.md` | merge/squash/rebase/recreate/shallow/rename all green | 8 |
| 5 SPEC | `spec/v0.1/requirements.yaml` body, governance/**, CONTRIBUTING, SECURITY | Every CK `spec_ref` resolves; no orphan MUST; SPEC.md regenerates with zero diff | 8 |
| 6 Conformance fixtures | conformance/** | Suite green; every trigger and every CK-E code appears in ≥1 case | 8 |
| 7 Agents + skills | agents/**, skills/**, adapters/claude-code/**, .claude/**, plugin/** | Frontmatter schema-valid; injection preamble byte-identical; least-privilege assertion; materialize --check clean | 6 |
| 8 Action + CI | actions/**, .github/** | `action-smoke` runs the action end-to-end against a temp repo | 6 |
| 9 Examples + dogfood | examples/**, root charter.yaml/CHARTER.md/ledger/ | lint + render --check + check green in both | 4 |
| 10 MCP skeleton | packages/mcp/** | `test_no_write_path` green | 2 |
| 12 Docs | docs/**, spec/v0.1/requirements.yaml + generator, README.md, docs CI | `sphinx-build -W` clean; Sybil examples green; reference-drift zero; spec-lint passing | 8 |

Cross-lane rules stated in every brief: WP-3 and WP-4 share `packages/cli/` but own disjoint subtrees and
neither touches `pyproject.toml`; WP-6 authors goldens against the *report schema*, so if a golden and the
engine disagree the SPEC arbitrates; WP-8 writes workflows against `docs/cli-contract.md` and WP-7 writes
roles against WP-0's frozen `verdict` signature, so neither waits on an implementation lane; WP-5 owns the
normative *source* (`requirements.yaml`) while WP-12 owns the *generator and site*, so they never edit the
same file.

**Phase III — WP-11 integration (sequential):** lock regeneration, coverage tuning, generated docs,
contract-amendment reconciliation, release dry run.

---

## H. CI (strict from day one)

Workflow-level `permissions: {contents: read}`; every third-party action SHA-pinned.

| Job | Content |
|---|---|
| `lint` | ruff check + format (incl. `D` and preview `DOC` rules), `mypy --strict`, `lint-imports`, deptry, vulture, zizmor on workflows |
| `docs` | `sphinx-build -W --keep-going -n`, reference-drift (`git diff --exit-code`), `griffe check` vs. merge base, CLI doc coverage, `lychee --offline`, `spec-lint`, `towncrier check` |
| `test` | py3.11/3.12/3.13 × ubuntu, + macos, + **windows** (the CRLF and path-separator proof) with `HYPOTHESIS_PROFILE=ci` derandomized |
| `coverage` | Branch coverage floors: core ≥95%, cli ≥85%, repo ≥90%; `triggers/`, `ordering`, `window`, `projection` at **100%** |
| `schema-drift` | `charter schema export --check` — the pydantic↔published-schema guarantee |
| `materialization-drift` | `charter agents materialize --check` — `agents/`+`skills/` vs `.claude/`+`plugin/` |
| `conformance` | `charter conformance run` (pure + repo + agents) on ubuntu and windows |
| `traceability` | **`charter spec trace --check`** — the gap-analysis gate (below) |
| `packaging` | `uv build`, then install `charter-cli` into a clean venv **with the workspace absent** and run `charter version` |
| `action-smoke` | Builds a temp repo from examples/lite, runs `uses: ./actions/charter-gate`, asserts exit code + artifact + summary |
| `dogfood` | `charter check` on this repo (draft status → computed, non-blocking, per §8) |

Separate: `post-merge-verify.yml` (F4), `nightly.yml` (mutation testing on triggers/ordering/window with
a tracked score floor, randomized hypothesis, `uv lock --check`, pip-audit), `release.yml` (signed tags,
provenance).

**Gap analysis is a CI gate, not a document.** SPEC sentences carry `REQ-` anchors; tests declare
coverage via `@pytest.mark.req("REQ-LED-004")`; a pytest plugin dumps the marks; `charter spec trace`
joins SPEC anchors + CK `spec_ref`s + collected marks into `docs/traceability.md` (rendered through the
generated-block protocol — dogfooding it). `--check` fails on: any MUST/MUST NOT/SHALL with zero covering
tests; any CK code whose `spec_ref` doesn't resolve or that no test produces; any registered trigger or
profile without a conformance case; any agent role without a golden verdict. A subagent that ships a SPEC
sentence without a test — or a test without a SPEC sentence — is stopped at the PR.

---

## I. Risks specific to this implementation

- **Git provenance.** `--first-parent` is load-bearing for forgery resistance and must never become
  configurable. Use `%cI` (committer), never `%aI` (author dates survive rebase and are user-controlled).
  A file deleted then re-added yields two `A` entries — take the earliest *and* raise `CK-E0303`, since a
  second add is itself evidence of a prior append-only breach. `git log --follow` is deliberately unused:
  rename-following would defeat the no-rename rule. All git access goes through one `git_runner` choke
  point with an argument allowlist, `LC_ALL=C`, explicit timeouts, and never `shell=True`.
- **uv workspace vs. published wheels.** `[tool.uv.sources] workspace = true` is stripped at build time;
  if `charter-core` isn't also a real versioned dependency, the published `charter-cli` wheel is broken
  and nobody notices until an adopter installs it. The `packaging` job exists to catch exactly this.
- **pydantic↔JSON Schema drift.** Pydantic's emitter changes across minors (`Literal`→`const` vs `enum`,
  `$defs` ordering, an OpenAPI-flavoured `discriminator` strict validators ignore). Pin to a minor,
  normalize aggressively on export, commit and byte-diff, and run the dual-validation agreement property
  test so disagreement is a loud failure rather than silent divergence.
- **YAML.** All three hazards were verified live in this environment: `no`→`False`, ISO timestamp→
  `datetime`, and duplicate keys silently last-wins (a duplicate `budget:` quietly changing policy is a
  tampering vector). Locked by a behavioural contract test containing exactly those cases, so the
  guarantee survives a library swap. Also reject anchors/aliases, multi-document streams, and BOM under
  `ledger/`.
- **Typer/Click exit-code collision.** Click reserves 1 for `Abort`; 1 is our `VIOLATION`. `main.py`
  re-maps aborts explicitly so a Ctrl-C never masquerades as a charter violation. Snapshot-tested.
- **Determinism.** Hypothesis profiles registered in `conftest.py` (`ci` derandomized, `nightly`
  randomized at high `max_examples`); counterexamples get pinned into a `monotonicity-witness` fixture
  rather than relying on the gitignored `.hypothesis/` cache.
- **Exact arithmetic.** `cumulative_ratio` parsed as `Fraction(str(value))` and compared by integer
  cross-multiplication — `0.5` would survive float comparison but a configured `0.1` or `0.3` would not.
- **Portability.** macOS case-insensitivity and NFD normalization mean ledger filenames are restricted to
  `[A-Za-z0-9._-]` and compared case-insensitively; symlinks under `ledger/` are rejected because they
  can point outside the repo and defeat the append-only diff.
- **Python floor 3.11** — no PEP 695 syntax; use `TypeAlias`/`TypeVar`.

---

## J. Phasing

| Phase | Content | Pts | Exit gate |
|---|---|---|---|
| P0 Contract freeze | WP-0, sequential | 13 | schema + mypy green; every lane brief written against frozen files |
| P1 Parallel build | WP-1…WP-10, WP-12 | 71 | Each WP's done-test green on its branch |
| P2 Integration | WP-11 | 8 | Full CI green including `packaging` and `action-smoke` |
| P3 Traceability | Close every gap `spec trace` finds; make it required | 5 | Zero orphan MUSTs, zero untested CK codes |
| P4 Hardening | Mutation baseline, threat-model review, cold-start adopter dry run | 5 | A fresh agent can adopt `examples/lite` from docs alone |

≈102 points, 71 of them parallelizable across up to 11 lanes.

---

---

# Part 3 — README and documentation strategy

## The stack decision, and why it is not the obvious one

**Do not use MkDocs + Material.** Material has a **published end-of-life of 2026-11-05** (97 days from
now); `mkdocs` core has had no release since 1.6.1 in August 2024; and its owner plans an incompatible
"MkDocs 2.0" **published under the same PyPI name**, so `pip install mkdocs` is a live supply-chain
hazard. Ruff, uv, pydantic and FastAPI all use it — every one of those was a pre-EOL decision. For a
project whose product *is* governance credibility and whose stated top docs requirement is "must not
rot," adopting a stack with a death date is a self-inflicted rot event.

**Recommended: Sphinx 9 + MyST.** Decisive for this project because three anti-rot mechanisms ship in
core — `linkcheck`, `doctest`, and `coverage` builders — with no plugin to rot; `literalinclude` with
`:start-after:`/`:end-before:` markers lets docs quote tested source instead of copies; `intersphinx` +
`sphinx-codeautolink` turn "this example references a real API" into a *build error*; and it produces PDF,
which a versioned RFC-2119 standard genuinely needs for enterprise audit. Runner-up is **Zensical** (the
official successor, very active) — revisit at 1.0, but today its `mike` support requires a git fork not
published to PyPI, which is disqualifying for a project that gates on reproducible builds.

| Purpose | Package | Note |
|---|---|---|
| Site | `sphinx` 9.1 + `myst-parser` 5.1 + `sphinx-design` | Docs env pinned to py3.13; library stays 3.11+ |
| CLI reference | `sphinxcontrib-typer` 0.9.1 | Best CLI output surveyed; renders SVG preserving rich formatting |
| Schema reference | `sphinx-jsonschema` 1.19.2 | Generate into a gitignored build dir — never commit |
| API | core `autodoc` + `sphinx-autodoc-typehints` | `sphinx-autodoc2` is stale (2023); use `.rst` stubs |
| Example testing | `sybil` 10.1 | MyST-native, runs in the same pytest session with shared fixtures |
| API drift | `griffe` 2.1 (`griffe check`) | Fails PRs on breaking public-API change; needs `fetch-depth: 0` |
| Diagrams | Mermaid | The only option rendering natively on GitHub **and** the site from one fence |
| Demos | `vhs` + `vhs-action` | `.tape` files are reviewable in a diff and regenerable in CI |
| Versioned docs | `sphinx-polyversion` 3.0 | `mike` forces gh-pages branch mode, precluding OIDC deploy |
| Changelog | `towncrier` 25.8 | Author-written fragments — the only mechanism producing "does this affect me?" |
| Links | `lychee` | Split: `--offline` required on PRs, full external nightly → opens an issue |

Also: **drop `interrogate`** from the quality gates (stale since 2024) — ruff's `D` rules plus preview
`DOC` rules cover docstring presence and signature agreement, and Sphinx's `-b coverage` catches
module-level gaps.

## The highest-value structural decision: generate SPEC.md from `requirements.yaml`

Follow the OSPS Baseline pattern. `spec/v0.1/requirements.yaml` holds each requirement as structured
data — `id`, `title`, `text`, `applicability: [CL-1…CL-4]`, `rationale` (non-normative), `tests`,
`status` — and SPEC.md, the conformance-level tables, and the conformance suite index are all **generated**
from it through the same render-freshness gate already built for `CHARTER.md`.

Three things fall out at once: a project whose thesis is "governance should be computable" stops
hand-maintaining its own normative text; **applicability declared per-requirement rather than per-section
makes the conformance suite mechanically derivable** rather than hand-synced; and the traceability matrix
(§H) gains its authoritative left-hand column for free. This is the single strongest differentiating
documentation decision available, and it costs one generator.

Supporting conventions: **RFC 8174 boilerplate, not bare RFC 2119** — the *"when, and only when, they
appear in all capitals"* clause matters enormously for a spec whose surrounding prose also uses "must"
casually. **Stable semantic requirement IDs, never ordinals** (`REQ-LEDGER-003`, not "rule 7") — ordinals
renumber on insertion and silently invalidate every external citation; retire IDs, never reuse them.
Default every section to normative and wrap examples and rationale in labeled *(non-normative)* blocks.
Per-section stability markers, OpenTelemetry-style, so a stable ledger format can ship alongside an
experimental MCP contract. Schema `$id` URLs are permanent and versioned — the one commitment that cannot
be walked back. **`SPEC.md` must be CommonMark-only**: a single MyST directive silently degrades GitHub's
rendering to raw text, and SPEC.md is read in the repo; include it into the site via a stub page and lint
it to reject directive syntax.

## README: the sales archetype, not the gateway

Projects split into *gateway* READMEs (pre-commit's is literally one sentence and a link) and *sales*
READMEs. Gateways work when you are already famous. charter-kit has no adopters — its dominant risk is
platform-before-adopters — so it needs the sales form. Budget: **badges to first runnable command in
≤30 lines** (uv shows install at ~line 15, working code at ~line 30).

Order: badges (max 6, one row) → one-sentence tagline structured as *claim + category + credibility
signal* → **hero GIF that is proof, not decoration** (the gate rejecting an over-budget carve-out, then
passing — uv and ruff both use a captioned benchmark here; the hero exists to make a falsifiable claim) →
"what this is" naming the dual nature explicitly → 60-second quickstart → the worked example (a real
15-line `charter.yaml`, the PR that breaks it, the exact CI failure text) → why this exists (bullets;
prose lives in `/explanation/`) → **how this relates to what you already have** → **what charter-kit does
*not* do** → conformance levels → documentation link map → full install matrix → project status and
`spec_version` policy → security → governance and the RFC process → contributing → prior art and
acknowledgements → license.

Two placement rules from the research: testimonials and adopter walls are bimodal (1–3 quotes early, the
logo wall last) — **reserve those slots and ship none of them until they are real**, because an empty
testimonials section is worse than its absence. And Acknowledgements is a positioning tool, not
politeness: crediting Spec Kit, ADRs, RFC 2119/8174, OPA/conftest, and Keep a Changelog defuses "you're
reinventing X" without ever sounding defensive.

**The positioning section must be a taxonomy table, not a scorecard.** Notably, *none* of uv, ruff, OPA,
Terraform, Nix, pre-commit, Changesets, or semantic-release has a comparison table in its README; the
pattern is a docs page (Vite's `/guide/comparisons`, jj's `git-comparison.md`, Astro's `why-astro`). For
charter-kit a ✅/❌ grid would be actively wrong: `constitution.md`, AGENTS.md, CODEOWNERS, ADRs and RFCs
are **complementary layers, not competitors**, and Spec Kit's users are the best early adopters — you are
shipping their adapter. Use rows = artifact, columns = *what it governs / who enforces it / is it
machine-readable / does charter-kit replace it*, with every cell in the last column reading "No —
complements." The table earns trust precisely because it declines to claim a win. jj's tone is the
template: state the alternative's feature accurately and respectfully, *then* explain the different
approach.

**Ship the "what CI cannot enforce" page early and link it from the README.** F9 flagged CL-3 "Enforced"
as an overclaim; documenting the limit prominently defuses the first bypass-by-semantics incident,
signals architectural maturity, and — for a product whose subject matter *is* honestly declared
boundaries — is the most credible possible demonstration that the method works. It will convert more
enterprise evaluators than any feature list.

## Site information architecture (Diátaxis, plus a fifth axis)

Diátaxis sorts pages on two axes (action↔cognition, acquisition↔application) into tutorial / how-to /
reference / explanation. **A normative spec is not "reference" in the Diátaxis sense** — reference is
*descriptive*, a spec is *prescriptive toward implementers*. Every standards project examined (SLSA,
OpenTelemetry, JSON Schema, in-toto) treats the spec as a **fifth parallel axis** with its own URL
namespace, version numbers, and stability policy, with the four quadrants wrapping around it.

```
/start-here/     Persona router: solo maintainer · platform team · enterprise evaluator · spec implementer
/tutorial/       first-charter · first-carveout          ← exactly two; resist a third
/how-to/         adopt-in-existing-repo · propose-a-carveout · handle-a-closed-path · run-a-review
                 reach-cl-3 (branch settings enumerated) · integrate-with-spec-kit · wire-into-merge-queue
                 verify-release-provenance · build-from-source · upgrade-spec-versions
/reference/      cli · charter-yaml · ledger-events · action · mcp-tools · exit-codes · glossary   [generated]
/explanation/    why-budgeted-non-goals · design-invariants · event-sourced-ledger · clock-and-triggers
                 what-ci-can-and-cannot-enforce ← the F9 page · agents-are-advisory
                 related-work ← the positioning page · threat-model · anti-patterns
/spec/           v0.1/ (frozen) · conformance/ · schemas/ · stability-policy   ← the fifth axis
/conformance/    how to claim a level · public conformance report
/governance/ /security/ /support-policy/ /roadmap/ /changelog/
```

Two deliberate deviations, both defensible: a `/start-here/` persona router (CNCF's rubric explicitly
requires role-organized entry points) that **routes to existing pages rather than creating a fifth silo**
— specifically, resist an `/enterprise/` section, since the enterprise evaluator wants the threat model,
the support policy, and CL-3 setup, all of which already exist elsewhere; and the spec outside the
quadrants. Apply ARID deliberately: the same carve-out example should appear in the tutorial, the how-to,
*and* the spec. Do not factor it out — different quadrants, different jobs.

**A public conformance report** (JSON Schema's [bowtie.report](https://bowtie.report/) model) is the
answer to the badge-hunting risk in the draft's own register, and it works *before* `charter attest`
exists or any GitHub App scope is needed. Worth noting as prior art in the spec's related-work section:
the OpenSSF Best Practices Badge already runs "all SHOULD criteria must be met **or** the rationale for
not implementing documented" — that is charter-kit's carve-out concept, in production, at OpenSSF. It is
the strongest available third-party validation that budgeted exceptions are a real governance primitive.

## Anti-rot mechanisms (the part that matters)

Generated reference can't drift because it's generated — **prose is where docs actually rot**, so the
checks target prose:

1. `sphinx-build -W --keep-going -n` — broken cross-refs, bad directives, and (via `sphinx-codeautolink`
   with `warn_on_failed_resolve`) any example naming an API that no longer exists.
2. **Sybil over `docs/**/*.md`, `SPEC.md`, and `README.md`, running inside the existing pytest session** —
   shared fixtures, one coverage report, one required check.
3. Reference-drift: regenerate CLI + schema reference, `git diff --exit-code`.
4. `griffe check charter_core -a $(git merge-base origin/main HEAD)` — silent public-API breakage.
5. **CLI doc coverage (~40 lines, write it):** introspect the Typer app, collect every command path and
   option string, scan prose for `--flag` tokens; fail on a flag in prose that no longer exists, or a
   command with zero prose mentions. This is the only check that catches prose rot.
6. `lychee --offline` on PRs; full external run nightly opening an issue rather than reddening a PR.
7. `spec-lint`: CommonMark-only assertion on SPEC.md, RFC-2119 keyword check, requirement-ID uniqueness
   and stability (an ID must never be renumbered or reused).
8. `towncrier check --compare-with origin/main`, with a `skip-changelog` label escape.
9. Path-coupled check: a diff touching `schema/**` or `packages/cli/**` with no `docs/**` change and no
   `docs-not-needed` label fails, naming the file that changed — the same enforcement philosophy as
   `charter-gate`.

Traps worth pre-empting: never `literalinclude :lines:` (rots silently on any edit above the range) —
always marker-based; keep `-W` and `linkcheck` in **separate** jobs so an external 503 can't redden a PR;
don't byte-diff VHS GIFs (timing and font rasterization are nondeterministic) — gate on the tape's
commands exiting 0; GitHub's Mermaid lags npm and drops markdown lists in labels, so pin the site version
and stay in the conservative subset; towncrier in a monorepo cannot infer versions, so `package`/`name`
stay empty and `--dir`/`--version` are explicit per build; and `fetch-depth: 0` is now required by
`griffe check` and `sphinx-polyversion` as well as the append-only gate — document it once, in one place.

## Multi-artifact versioning

SPEC, schemas, core, cli, mcp-server and the action version on independent cadences, so a docs version
selector cannot express compatibility. Generate a **compatibility matrix from `compat.yaml`**
(spec_version → version ranges of each distribution), rendered at build time and validated by the same
drift gate. A reader on `charter-cli 1.4` must be able to answer "did SPEC 0.3 change anything for me?"
from one table. Never hand-maintain it.

## Staging — apply the adoption gate to docs too

The dominant risk is platform-before-adopters, and M2+ is already gated on one external CL-3 adopter.
Apply the same discipline here, or the risk simply reappears in Markdown: **M0 docs = README + generated
SPEC.md + `/reference/cli` + one tutorial.** Nothing else. `/how-to/` grows one page per real adopter
question; `/explanation/` grows one page per real objection. The threat model, compliance mapping, and
enterprise checklist arrive with M4. A 40-page docs site with zero adopters is the same failure mode as a
four-package monorepo with zero adopters.

Enterprise artifacts, when they come, are checklist-driven rather than invented: Tier 1 is LICENSE (split
— CC-BY-4.0 for SPEC and schemas so others may quote them, Apache-2.0 for code), SECURITY.md,
CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, versioning/deprecation policy, build-from-source. Tier 2 is the
threat model (sigstore's four-section structure: introduction, **main takeaways near the top**, threat
table sorted by attacker capability, mitigations, explicit out-of-scope), release-provenance verification
instructions with runnable `cosign verify` snippets, support-scope and security-EOL statements, dependency
policy, GOVERNANCE.md, a per-scope permissions rationale (where `pull-requests: read` from F6 gets
justified), `security-insights.yml`, and the OpenSSF Best Practices badge.

**WP-12 (docs)** joins Phase II owning `docs/`, `spec/v0.1/requirements.yaml` + its generator,
`README.md`, and the docs CI workflow — 8 points. Its done-test: `sphinx-build -W` clean, Sybil examples
green, reference-drift zero, and `spec-lint` passing.

---

## K. Verification

End-to-end, in order:

1. `make all` — ruff, mypy --strict, import-linter, deptry, vulture, full pytest with coverage floors.
2. `uv run charter schema export --check` and `uv run charter agents materialize --check` — both must
   produce zero diff.
3. `uv run charter conformance run` — all three case families green.
4. **Fresh-repo e2e:** in a temp dir, `charter init --profile lite` → `charter lint` → `charter render
   --check` → `charter check --at 2026-07-31T00:00:00Z` → exit 0 with a schema-valid report.
5. **Trigger reality check:** add a second and third ratified carve-out to `examples/lite`, re-run
   `charter check`; confirm per-ID closure fires at `budget+1`, `charter verdict --ng NG-1` returns
   `VIOLATION(NG-1)`, and `charter explain trigger per_id` names the contributing events. Then add
   `RV-1.opened` + `RV-1.closed` and confirm the path reopens and does **not** immediately re-fire (A2).
6. **Provenance under real git:** run the `cases/repo/` suite — merge, squash, rebase, recreate-after-
   delete, shallow clone, rename — and confirm the forged-`GIT_COMMITTER_DATE` topic-branch case is
   correctly attributed to the merge commit.
7. **Action smoke:** `act` locally or the `action-smoke` CI job against a temp repo built from
   `examples/lite`; assert exit code, uploaded report artifact, and step summary content.
8. **MCP:** start `charter-mcp`, read `charter://state`, confirm it reports its source commit (R2-7) and
   that `test_no_write_path` proves no write-capable tool is registered.
9. **Agents/skills:** `claude plugin validate ./plugin --strict`; run the `cases/agents/` goldens; confirm
   guardian tool allowlist ∩ write-capable deny-list is empty.
10. **Gap analysis:** `charter spec trace --check` exits 0 — no normative statement without a test, no
    error code without a SPEC reference.
11. **Docs:** `sphinx-build -W --keep-going -n` clean; Sybil examples pass inside the pytest run;
    regenerating the CLI and schema reference produces zero diff; `griffe check` against the merge base
    is clean; the CLI doc-coverage script reports no orphaned flags or undocumented commands;
    `lychee --offline` passes; `spec-lint` confirms SPEC.md is CommonMark-only with unique, stable
    requirement IDs; and regenerating SPEC.md from `requirements.yaml` produces zero diff.

Then: push to `claude/charter-kit-framework-review-ei8up6`, open a draft PR against the new `main`, and
confirm the gate runs on the PR itself (dogfooding, non-blocking while `status: draft`).
