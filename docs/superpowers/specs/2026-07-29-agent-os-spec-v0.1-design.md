# agent-os v0.1 - A research-graded spec for agentic coding, with a thin validator

Date: 2026-07-29
Status: approved (design), pre-implementation
Branch: draft/initial

## 1. Purpose

Define a **repository-owned, model-independent specification** for agentic coding, plus a
**thin runnable validator** that proves the spec is machine-checkable rather than prose.

The design is deliberately narrow. It codifies the patterns that the `subject/` repo (a mature
brownfield F#/Fable codebase) already proved *organically*, strips the antipatterns the accompanying
research report (`WHITEPAPER.md`) grades as harmful, and adds the two primitives that report grades
**A / A-** and calls the biggest ecosystem gaps: **typed durable task state** and an **evidence ledger**.

Everything the report grades *emerging or lower* (skill-promotion pipelines, workflow engines,
dashboards, knowledge graphs, model adapters, memory pruning, telemetry) is documented in the roadmap
and **left unbuilt** until it can be measured. Building all of it at once is the exact anti-pattern the
report warns against ("start with a huge everything and let the agent figure it out").

### 1.1 Framing: this is a pre-codebase bootstrap

agent-os is the **structure an agent sets up before it reads any repository code**. You copy it into a
target repo (greenfield or brownfield) as the operating layer. The normative artifacts ship as
**skeleton templates**, not filled-in data. Real content arrives later: as work proceeds in the target
repo, the agent populates and updates `STATE.yaml`, appends to `evidence/ledger.ndjson`, and refines the
policies. The validator checks conformance at every step.

So the deliverable is two things at once: a **spec** (the schemas + the format) and a **copy-in
scaffold** (the skeleton files + a `bootstrap` step + the zero-dep validator). `examples/subject/` shows
one populated instance derived from a real repo. This matches the report's "pre-codebase setup"
guidance: create the rule file, durable-state schema, evidence ledger, and policy layer first, then
point the agent at the code.

## 2. Non-goals (v0.1)

- No agent runtime, orchestrator, or model adapters.
- No skill *promotion/deprecation pipeline* (only a manifest format + lint).
- No workflow state-machine engine.
- No dashboard, telemetry sink, or knowledge graph.
- No claim of being "Terraform/Kubernetes for agents." That is a category claim earned by adoption
  after solving one narrow thing well, not declared at v0.1.

## 3. What `subject/` already proves (design inputs)

Confirmed by inspection of `/Volumes/HomeX/shafayat/Code/subject`:

- **Verifier-first is real, not prose**: `scripts/verify-done.sh` (catches Fable "Skipped compilation"
  false-greens), `scripts/ci-gate.sh`, `scripts/symptom-match.sh`.
- **Machine enforcement exists**: `scripts/forbidden-path-guard.sh` wired as a PreToolUse hook
  (`.claude/settings.json`) *and* a git pre-commit hook; a second hook blocks direct `dotnet fable`.
- **Skill library**: 19 skills under `.claude/skills/*/SKILL.md` (+ `scripts/`).
- **Scope + org rules**: framework-only (do not touch `App*`/`Suite*`), no Moq/AutoMapper, no em-dash.

### Antipatterns present (each maps to a report finding)

1. **Rule-file bloat** - `CLAUDE.md` is ~230 lines mixing operative rules with narrative; a large docs
   site is the "single source of truth." Report: large context files reduce success (A-, avoid).
2. **Prose memory, no evidence discipline** - engineering-log + codemem store prose; no
   fact-vs-inference, no provenance/hash, no supersede/staleness. Report: A-graded biggest gap.
3. **No typed durable STATE** - task state lives in conversation + prose; nothing survives compaction as
   a machine-readable object. Report: A- gap.
4. **Skills have no lifecycle** - no versioning, tests, or governance. Report: emerging, governance req'd.

## 4. Normative artifacts (v0.1 spec surface)

Six artifacts. Each has a JSON Schema (or documented format) under `schemas/` and is checked by the
validator. Grade = report evidence grade.

| # | Artifact | Standardizes | Grade |
|---|---|---|---|
| 1 | `AGENTS.md` format + size budget | Operative rule-file: commands, invariants, forbidden actions, approval gates, scope. No narrative. Canonical `AGENTS.md`; `CLAUDE.md` is a thin pointer for Claude Code. | A- |
| 2 | `STATE.yaml` + `schemas/task-state.schema.json` | Typed durable task state, compaction-safe. | A- |
| 3 | `evidence/ledger.ndjson` + `schemas/evidence.schema.json` | Append-only claims with provenance. | A |
| 4 | `policies/path-policy.yaml` | Scope allowlist enforceable against a diff. | A |
| 5 | `skills/index.yaml` + `schemas/skill.schema.json` | Skill *manifest* format + lint (no pipeline). | B |
| 6 | `policies/dependency-policy.yaml` | Banned/required dependencies as a checkable rule. | B+ |

### 4.1 `AGENTS.md` format + size budget

- Sections (fixed, in order): `Commands`, `Invariants`, `Forbidden`, `Approval gates`, `Scope`,
  `Conventions (pointer)`. Narrative belongs in linked docs, not here.
- **Size budget**: soft cap ~150 lines / ~1500 tokens for the operative file. Validator warns past soft
  cap, fails past a hard cap (~250 lines). This directly counters antipattern #1.
- `CLAUDE.md` (and future `.cursor`/other) is a ≤5-line pointer to `AGENTS.md` - one operative source,
  many entry points → model-independence.

### 4.2 `STATE.yaml` (task-state schema)

Typed fields (trimmed from the report's schema to decision-critical memory only):

```yaml
task_id: string
goal: string
risk_class: read-only | reversible | irreversible | deploy
scope_in: [glob]
scope_out: [glob]
acceptance_criteria: [string]
confirmed_facts: [{ fact: string, evidence_ref: string }]
assumptions: [string]
decisions: [{ decision: string, rationale: string }]
failed_hypotheses: [{ hypothesis: string, failure_signal: string }]
open_questions: [string]
changed_files: [path]
verification_status: { format, compile, tests, policy, security }  # each: pass|fail|n/a|pending
next_action: string
```

Compaction rule: `acceptance_criteria`, `confirmed_facts`, `decisions`, `failed_hypotheses`,
`verification_status` MUST NOT be summarized away.

### 4.3 Evidence ledger (`evidence/ledger.ndjson`)

One JSON object per line, append-only. This is the fact-vs-inference layer subject/ lacks.

```json
{ "claim": "", "status": "confirmed|inferred|unverified", "evidence_ref": "",
  "source_type": "tool|file|test|policy|human", "verifier": "", "hash": "", "ts": "" }
```

`ts` supplied by the caller (validator does not generate time). `hash` = content hash of the referenced
evidence when applicable. Supersede = append a new entry referencing the old claim (never mutate).

### 4.4 `policies/path-policy.yaml`

```yaml
may_edit: [glob]      # agent may edit freely
ask_first: [glob]     # requires explicit approval (warn)
never: [glob]         # hard block (fail)
```

Derived for v0.1 from subject/'s real rules: `Lib*`, `LibUi*`, `ThirdParty`, `Meta/*` → may_edit;
`App*`, `Suite*` → ask_first; `_autogenerated_`, `*.render`, `*.typext.fs`, stray `*.fs.js` → never.

### 4.5 `skills/index.yaml` + skill schema

Manifest format only (name, version, owner, purpose, when_to_use, inputs, outputs, tests,
safety_constraints, provenance). Lint checks: every `.claude/skills/*/SKILL.md` has a manifest entry;
required fields present; version is semver. **No promotion/benchmark pipeline in v0.1.**

### 4.6 `policies/dependency-policy.yaml`

```yaml
banned: [{ name: "Moq", reason: "org rule" }, { name: "AutoMapper", reason: "org rule" }]
required: []          # e.g. pinned versions, optional in v0.1
ecosystems: [nuget]   # extensible: npm, pip...
```

Lint scans manifests (`*.fsproj`/`*.csproj`, `packages.config`, `package.json`) for banned names.

## 5. Hook contract (documented; thin reference impls)

The spec defines the contract; the reference implementation ships thin wrappers so it drops into
Claude Code hooks + git pre-commit exactly as subject/ already does.

| Hook | Checks | Fail behavior |
|---|---|---|
| `pre-tool` | path-policy on the target path; dependency-policy on manifest edits | block (`never`) / warn (`ask_first`) |
| `stop-check` | verification_status complete; STATE + ledger valid; no unverified "done" | refuse success claim |
| `pre-commit` | path-policy on staged diff; dependency-policy; schema validation | block commit |

## 6. Validator (`agentos validate`)

- **Language**: Python 3 **stdlib only** (no third-party deps) → runs on any macOS/Linux/CI without
  install. Rationale: portability + the report's "pinned, minimal-dependency, deterministic" ethos.
  JSON Schema conformance is a small hand-rolled checker (Draft-07 subset we actually use), not an
  external lib, to keep the zero-dep guarantee.
- **Subcommands**:
  - `validate state [FILE]` - STATE.yaml vs task-state schema.
  - `validate ledger [FILE]` - each ndjson line vs evidence schema.
  - `validate diff [--staged | A..B]` - git diff vs path-policy → pass/fail + exact violations.
  - `validate rules [AGENTS.md]` - size/structure lint.
  - `validate skills` - manifest lint vs `.claude/skills/*`.
  - `validate deps` - dependency-policy scan.
  - `validate all` - run every check; nonzero exit on any failure.
- Each check prints its **evidence grade**. Machine-readable `--json` output for CI.
- Exit codes: `0` pass, `1` violation, `2` config/usage error.

## 7. Repository layout (v0.1 - only what is built)

```
agent-os/
├── README.md
├── WHITEPAPER.md
├── SPEC.md                     # normative spec (this design, distilled)
├── ROADMAP.md                  # graded, unbuilt future modules
├── AGENTS.md                   # example operative rule-file (self-hosting)
├── schemas/
│   ├── task-state.schema.json
│   ├── evidence.schema.json
│   └── skill.schema.json
├── policies/
│   ├── path-policy.yaml
│   └── dependency-policy.yaml
├── examples/
│   └── subject/                # path-policy + AGENTS.md derived from the real subject repo
├── hooks/
│   ├── pre-tool
│   ├── stop-check
│   └── pre-commit
├── bin/
│   ├── agentos                 # validator entry point
│   └── bootstrap               # copies skeleton artifacts into a target repo
├── agentos/                    # Python stdlib package (validator)
│   ├── __init__.py
│   ├── cli.py
│   ├── jsonschema_min.py       # tiny Draft-07-subset checker, zero-dep
│   ├── checks/
│   │   ├── state.py
│   │   ├── ledger.py
│   │   ├── diff.py
│   │   ├── rules.py
│   │   ├── skills.py
│   │   └── deps.py
│   └── grades.py               # maps checks -> report evidence grades
└── tests/
    └── ...                     # fixtures + golden cases per check
```

## 8. Roadmap (documented, unbuilt - each has a "gate to build")

| Module | Grade | Gate to build (what must be measured first) |
|---|---|---|
| Skill promotion/deprecation pipeline | Emerging | Skill regression suite + retrieval-frequency metric exist |
| Context accounting (retrieved vs used) | B+ | Instrumentation to log retrieval + influence on diff |
| Workflow state-machine engine | Emerging | ≥3 workflows proven stable as YAML the validator checks |
| Telemetry / dashboard | 🔴 mostly-custom | A metrics schema + a trace sink chosen |
| Knowledge / architecture graph | 🟡 | Repo self-analysis output stable enough to persist |
| Model adapters (Codex/OpenCode) | n/a | v0.1 spec adopted by ≥1 non-Claude agent |
| Memory promotion/pruning ("git GC for memory") | Emerging | Memory quality scoring (usefulness/staleness/contradiction) defined |

## 9. Testing strategy

- Every check has fixtures: at least one passing and one failing case, asserted via golden output.
- `validate diff` tested against a synthetic git range and against the derived `examples/subject/`
  path-policy.
- Zero-dep guarantee tested: validator runs under a bare `python3` with no site-packages.
- Determinism: same inputs → identical `--json` output (no timestamps generated internally).

## 10. Evidence mapping (traceability to WHITEPAPER.md)

| v0.1 artifact | Report support |
|---|---|
| AGENTS.md size budget | "Evaluating AGENTS.md" - big rule files reduce success (A-) |
| STATE.yaml | Durable-state schema recommendation (A-) |
| Evidence ledger | "distinguish fact from inference"; biggest gap (A) |
| path-policy + hooks | pre_tool_call / tool allowlist (A) |
| dependency-policy | org rule + tool-policy enforcement (B+) |
| skill manifest | executable/versioned skills; registry grounding (B) |
| validator (deterministic, zero-dep) | "determinism must be operationalized"; verifier-first (A) |
```
