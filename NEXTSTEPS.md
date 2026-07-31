# Next steps

Where charter-kit actually is, and what's next. For the full historical plan
(rounds 1-3 peer review, A1-A14 normative decisions, the original phase
breakdown), see `docs/implementation-plan-m0.md`. This file is the current,
living summary; that one is the record of how the design got here.

## Blocked, waiting on a repository setting

**S4 (git adapters + CLI) cannot start until this repository's default
branch is `main`.** Provenance derivation walks `--first-parent` history
from the *default ref* — building and testing that logic against a feature
branch would produce answers the real thing wouldn't, and the correction
would either be wasted work or (worse) a false sense that S4 is done. This
is a repository setting, not something fixable from inside a session:
Settings → General → Default branch, on `github.com/ianshank/CHARTER.md`.
**This is unaffected by the branching model below** — the default branch
must still become `main`, never `dev`, since `main` is the release branch
in that model.

Once that's flipped, S4 is the very next thing:

- **Adapters** (`packages/cli/src/charter_cli/adapters/` or similar) —
  `--first-parent` (never configurable — this is what makes provenance
  forgery-resistant), `%cI` committer time (never `%aI` author time, which a
  contributor controls), one `git_runner` choke point with an argument
  allowlist and `LC_ALL=C`, real-git integration tests covering merge,
  squash, rebase, a file recreated after delete, and shallow clones.
- **CLI** (`packages/cli/src/charter_cli/main.py`, wiring up
  `[project.scripts] charter = "charter_cli.main:app"`, which is currently
  declared but points at a module that doesn't exist yet) — `init`, `lint`,
  `check`, `render`, `verdict`, `explain`, `simulate --with-event`, `schema
  export --check`.
- **Observability** — `structlog`, JSON + console output, `--verbose
  /--debug/--quiet` plus `CHARTER_LOG_LEVEL`, `run_id` on every record. Core
  stays pure and logs nothing (enforced structurally by import-linter and
  the AST purity test); the `EvaluationReport` and its diagnostics *are*
  core's observability surface. This only belongs in `charter_cli`, and
  can't be meaningfully built before the commands it would instrument exist.

## Branching model

`main`/`qa`/`dev` branches now exist, GitFlow-lite (`feature|fix|claude/*`
→ `dev` → `qa` → `main`). See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the
contributor-facing flow and commit convention, and
[`BRANCHING.md`](BRANCHING.md) for the exact required-checks and
branch-protection settings — which still need to be applied by hand in
GitHub's Settings UI, since no available tool can configure them
automatically.

## Unblocked, not yet done

**S5 — self-enforcement.** The gate action (composite + reusable workflow),
`post-merge-verify.yml`, and — the actual headline milestone — **charter-kit
evaluating its own charter in CI**. `charter.yaml` and `CHARTER.md` for this
repository now exist (see below) and validate against the real `Charter`
model, but nothing can *run* `charter check` against them until S4 lands.

**S6 — remaining defects and artifacts.** Most of what was tracked here has
been cleared in this pass (see `CHANGELOG.md`) — including `CODEOWNERS`,
`CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, and `GOVERNANCE.md`,
which landed alongside the branching model above rather than waiting for a
CLI to exist. What's left:
- A `Dockerfile` + `.dockerignore` — deliberately not built yet. The console
  script (`charter`) points at `charter_cli.main:app`, which doesn't exist;
  a container packaging an unrunnable CLI would be actively misleading
  rather than useful. Build this alongside S4, not before it.
- `examples/lite` — a worked example repository, useful once `init`/`check`
  are real commands to run against it.
- ADRs, `docs/work-packages.yaml`, `docs/cli-contract.md`,
  `spec/v0.1/requirements.yaml` (the `REQ-` registry every `CK-` diagnostic's
  `spec_ref` points at, which doesn't exist as a standalone artifact yet —
  today the requirement ids are only implicitly defined by their use in
  `errors.py` and the tests).

## Explicitly out of scope for now

Not overlooked — deliberately not built, because building them now would be
premature or actively misleading:

- **The MCP server, OpenSpec/Copilot adapters, and the enterprise profile
  beyond what `profiles.py` already has.** The scope gate from the original
  plan stands: these stay unbuilt until at least one repository other than
  this one runs the gate as a required check. That's the primary defense
  against the platform-before-adopters risk this project could fall into.
- **`.claude/` agents, skills, or hooks.** No such convention exists in this
  repository today; inventing one without a concrete need would be
  speculative scaffolding nobody asked for. `CLAUDE.md` covers the
  repository-level context a session actually needs.
- **NumPy, or any numerical-computing dependency.** This is a governance
  engine over exact `Fraction` arithmetic and pydantic models — there is no
  numerical workload here for NumPy to serve.

## Verification, once S4 lands

The plan's original acceptance criteria still stand:

1. `make all` green — lint, types, import contracts, coverage ≥95%, schema
   drift, deptry, vulture, pip-audit.
2. Fresh temp repo: `init → lint → render --check → check --at <pinned>` →
   exit 0, schema-valid report.
3. Trigger reality: per-ID fires at `budget+1`; `verdict --ng NG-1` →
   `VIOLATION(NG-1)`; `explain trigger per_id` names the contributing
   events; a review close reopens the path and does not re-fire at an
   unchanged level.
4. Provenance under real git, including a forged `GIT_COMMITTER_DATE`
   correctly attributed to the merge commit rather than trusted.
5. Wheels install by explicit path into a clean venv, workspace absent,
   `Requires-Dist: charter-kit-core`.
6. `git ls-remote --symref origin HEAD` → `refs/heads/main`.
7. **The gate runs green against charter-kit's own charter.**
