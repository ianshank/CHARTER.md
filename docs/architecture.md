# Architecture

C4-style diagrams of the system as it actually exists today — not the
aspirational end state. Where a box represents something not yet built, it's
labeled "planned" and grayed out; nothing here pretends S4 has already
happened. See `NEXTSTEPS.md` for what's blocked and why.

Diagrams use plain Mermaid flowcharts rather than Mermaid's native
`C4Context`/`C4Container` diagram types, since GitHub's renderer support for
those lags behind Mermaid's own releases — a flowchart styled into C4's
levels renders reliably everywhere a flowchart does.

## Level 1 — System context

Who and what interacts with charter-kit, and how — today, that's a
developer with the Python library directly, since there is no CLI yet.

```mermaid
flowchart TB
    maintainer["Repository maintainer<br/>(person)"]
    reviewer["Code reviewer<br/>(person)"]

    subgraph today["charter-kit -- what exists today"]
        engine["charter_core<br/>pure evaluation engine<br/>(Python library)"]
        schemas["schema/*.json<br/>published JSON Schemas"]
    end

    subgraph planned["charter-kit -- planned (S4/S5, blocked)"]
        cli["charter_cli<br/>CLI + git adapters<br/>(not yet runnable)"]
        gate["GitHub Action gate<br/>(not yet built)"]
    end

    git[("Git history<br/>(commits, --first-parent)")]

    maintainer -->|"imports charter_core directly,<br/>as in README.md"| engine
    maintainer -.->|"planned: charter init / check"| cli
    reviewer -.->|"planned: PASS / VIOLATION / REVIEW_REQUIRED<br/>on every PR"| gate
    cli -.->|"planned: reads --first-parent history<br/>for ratification provenance"| git
    gate -.->|"planned"| cli
    engine -->|"validates against"| schemas

    classDef planned fill:#eee,stroke:#999,color:#666,stroke-dasharray: 4 3
    class cli,gate planned
```

## Level 2 — Containers

The two packages in the `uv` workspace, and what's actually implemented in
each.

```mermaid
flowchart TB
    subgraph core["packages/core -- charter_core (built)"]
        direction TB
        models["models/<br/>Charter, LedgerEvent union,<br/>EvaluationReport (pydantic)"]
        codec["codec.py<br/>safe YAML decode<br/>(no anchors/aliases/duplicate keys)"]
        engineMods["ordering · window · projection ·<br/>integrity · triggers/ · paths ·<br/>verdict · evaluate · explain"]
        settings["settings.py<br/>SETTING_SPECS: the one<br/>declarative source of every threshold"]
        ports["ports.py<br/>Protocols: ProvenanceProvider,<br/>LedgerSource, DiffSource, ApprovalSource, Clock"]
        errors["errors.py<br/>CK diagnostic registry"]
    end

    subgraph cli["packages/cli -- charter_cli (scaffolded only)"]
        direction TB
        exitcodes["exit_codes.py (built)"]
        commands["main.py + commands/<br/>(planned, S4 -- does not exist)"]
        adapters["git/filesystem adapters<br/>implementing charter_core.ports<br/>(planned, S4 -- does not exist)"]
        obs["structlog observability<br/>(planned, S4)"]
    end

    schemaFiles[("schema/*.json<br/>generated from models/,<br/>dual-validation tested")]

    codec --> models
    models --> engineMods
    settings --> engineMods
    engineMods --> errors
    models -->|"schema_export.py generates"| schemaFiles

    commands -.->|"planned: calls"| engineMods
    adapters -.->|"planned: implements"| ports
    commands -.-> adapters
    commands -.-> obs

    classDef planned fill:#eee,stroke:#999,color:#666,stroke-dasharray: 4 3
    class commands,adapters,obs planned
```

**The one hard rule this diagram exists to make visible:** nothing in
`packages/core` imports anything from `packages/cli`, and nothing in
`charter_core` performs I/O. Both are enforced structurally --
`.importlinter` fails the build on the first, an AST scan in
`tests/architecture/test_core_purity.py` fails it on the second. This isn't
a convention documented and hoped for; it's a compile-time-equivalent gate.

## Level 3 — Components: the evaluation pipeline

What actually happens inside `evaluate()`, the single function every future
surface (CLI, Action, MCP server) will call and the one that exists and is
tested today.

```mermaid
flowchart LR
    charter["Charter<br/>(validated pydantic model)"]
    events["Sequence[ResolvedEvent]<br/>(ledger events + provenance)"]
    at["at: datetime<br/>(the evaluation instant)"]

    negotiate["version.negotiate()<br/>spec_version compatibility"]
    integrity["integrity.check_integrity()<br/>referential checks"]
    project["projection.project()<br/>--> LedgerState<br/>(carve-out/review lifecycle,<br/>A2 ratchet baselines)"]
    triggers["triggers.evaluate_all()<br/>per_id · density · cumulative"]
    paths["paths.compute_path_state()<br/>per-non-goal + global closure"]
    verdict["verdict.compute_verdict()<br/>PASS / VIOLATION / REVIEW_REQUIRED"]
    report["EvaluationReport<br/>(facts, triggers, verdict, diagnostics,<br/>exit_code)"]

    charter --> negotiate
    charter --> integrity
    events --> integrity
    charter --> project
    events --> project
    at --> project
    project --> triggers
    triggers --> paths
    project --> paths
    paths --> verdict
    negotiate -->|"unsupported major:<br/>short-circuits here"| report
    integrity --> report
    triggers --> report
    verdict --> report

    explain["explain.py<br/>renders TriggerResult / PathState /<br/>ResolvedSettings / LedgerState<br/>into a causal narrative --<br/>no recomputation"]
    report -.->|"same computed state,<br/>read afterward"| explain
```

Every arrow in this diagram corresponds to a real function call you can find
in `packages/core/src/charter_core/evaluate.py`; nothing here is aspirational.

## Data model: the ledger

```mermaid
flowchart TB
    charterYaml["charter.yaml<br/>declarations only:<br/>non_goals[], config, profile, status"]

    subgraph ledger["ledger/*.yaml -- one file per event, append-only"]
        ratified["CO-1.ratified.yaml"]
        retired["CO-1.retired.yaml"]
        opened["RV-1.opened.yaml"]
        closed["RV-1.closed.yaml"]
        correction["CR-1.correction.yaml"]
    end

    provenance["Provenance<br/>(commit_sha, committed_at, first_parent)<br/>derived from git history,<br/>never a field in the file itself"]

    charterYaml -->|"non_goal id referenced by"| ratified
    ratified -->|"terminates"| retired
    opened -->|"terminates"| closed
    correction -.->|"annotates a prior event,<br/>never the future --<br/>see test_integrity.py"| ratified

    ledger -->|"filename + git history resolve to"| provenance
    provenance --> project2["projection.project()"]
```

Nothing about a carve-out's or review's status is stored in the ledger
itself: `active`/`retired`/`expired`/`moot`, and every count and baseline,
are derived fresh by `projection.py` at evaluation time. See the module
docstrings in `packages/core/src/charter_core/projection.py` and
`packages/core/src/charter_core/models/state.py` for why -- an append-only
ledger with derived-not-stored status is what lets a status change without
rewriting history.
