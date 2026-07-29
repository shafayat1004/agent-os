# SPEC.md - agent-os v0.1

Status: normative. This file states the rules the validator checks.

Source design doc: `docs/superpowers/specs/2026-07-29-agent-os-spec-v0.1-design.md`.
Evidence report: `WHITEPAPER.md`.

## 1. What this spec is

agent-os is a repository-owned, model-independent spec for agentic coding.
It ships with a thin validator that checks the spec by machine, not by prose.

This is a pre-codebase bootstrap. You copy agent-os into a target repo before
the agent reads any code in that repo. The normative files ship as skeleton
templates, not filled-in data. As work proceeds, the agent fills in
`STATE.yaml`, appends to `evidence/ledger.ndjson`, and updates the policy
files. The validator checks conformance at every step.

`examples/subject/` shows one populated instance, derived from a real repo.

## 2. Normative artifacts

Six artifacts make up the v0.1 spec surface. Each has a schema or a fixed
format, and the validator checks each one. The grade next to each artifact
is its evidence grade from `WHITEPAPER.md`.

| # | Artifact | What it standardizes | Grade |
|---|---|---|---|
| 1 | `AGENTS.md` | Operative rule file: commands, invariants, forbidden actions, approval gates, scope. No narrative. | A- |
| 2 | `STATE.yaml` | Typed durable task state. Survives context compaction. | A- |
| 3 | `evidence/ledger.ndjson` | Append-only claims with proof, not prose memory. | A |
| 4 | `policies/path-policy.yaml` | Scope allowlist. Checked against a real diff. | A |
| 5 | `skills/index.yaml` | Skill manifest format and lint. No promotion pipeline. | B |
| 6 | `policies/dependency-policy.yaml` | Banned or required dependencies as a checkable rule. | B+ |

### 2.1 `AGENTS.md` format and size budget

`AGENTS.md` has six sections, in this fixed order:

1. Commands
2. Invariants
3. Forbidden
4. Approval gates
5. Scope
6. Conventions (pointer)

Narrative belongs in linked docs, not in `AGENTS.md`.

The file has a size budget. The soft cap is about 150 lines or 1500 tokens.
The validator warns past the soft cap. The hard cap is about 250 lines. The
validator fails past the hard cap. This budget stops rule-file bloat, a
known failure mode for agent context.

`CLAUDE.md`, and any future `.cursor` file, is a pointer file of five lines
or fewer. It points at `AGENTS.md` and adds nothing else. This keeps one
operative source of truth with many entry points, so the spec stays
model-independent.

### 2.2 `STATE.yaml` (task-state schema)

`STATE.yaml` holds typed, durable task state. Its schema lives at
`schemas/task-state.schema.json`. The fields are:

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
verification_status: { format, compile, tests, policy, security }
next_action: string
```

Each field in `verification_status` holds one of: `pass`, `fail`, `n/a`,
`pending`.

A compaction rule applies. When context is shortened, do not summarize away
`acceptance_criteria`, `confirmed_facts`, `decisions`, `failed_hypotheses`,
or `verification_status`. These fields must stay intact.

### 2.3 Evidence ledger (`evidence/ledger.ndjson`)

The ledger is the fact-versus-inference layer. It is append-only. Each line
holds one JSON object, checked against `schemas/evidence.schema.json`:

```json
{ "claim": "", "status": "confirmed|inferred|unverified", "evidence_ref": "",
  "source_type": "tool|file|test|policy|human", "verifier": "", "hash": "", "ts": "" }
```

The caller supplies `ts`. The validator does not generate time, so results
stay deterministic. `hash` is a content hash of the referenced evidence,
when one applies.

To supersede a claim, append a new entry that references the old claim. Do
not mutate or delete a past entry.

### 2.4 `policies/path-policy.yaml`

The path policy states where the agent may edit files, without reading the
whole diff by hand:

```yaml
may_edit: [glob]      # the agent may edit these paths freely
ask_first: [glob]     # these paths need explicit approval first
never: [glob]         # these paths are a hard block
```

`examples/subject/policies/path-policy.yaml` derives this from a real
repo's rules: library and third-party code as `may_edit`, app and suite
code as `ask_first`, and generated or render files as `never`.

### 2.5 `skills/index.yaml` and skill schema

The skill manifest lists each skill's name, version, owner, purpose,
when-to-use text, inputs, outputs, tests, safety constraints, and
provenance. Its schema lives at `schemas/skill.schema.json`.

The validator lints the manifest. It checks that every
`.claude/skills/*/SKILL.md` has a matching manifest entry, that required
fields are present, and that the version string is valid semver.

v0.1 ships the manifest and the lint only. It does not ship a promotion or
benchmark pipeline for skills. See `ROADMAP.md`.

### 2.6 `policies/dependency-policy.yaml`

The dependency policy names banned or required packages, checked against a
target repo's manifests:

```yaml
banned: [{ name: "Moq", reason: "org rule" }, { name: "AutoMapper", reason: "org rule" }]
required: []
ecosystems: [nuget]
```

The lint scans manifest files, such as `*.fsproj`, `*.csproj`,
`packages.config`, or `package.json`, for banned names. The `ecosystems`
list is open. Future ecosystems, such as npm or pip, can extend it.

## 3. Hook contract

The spec states the hook contract. The reference hooks under `hooks/` are
thin wrappers, built to drop into Claude Code hooks and a git pre-commit
hook.

| Hook | Checks | Fail behavior |
|---|---|---|
| `pre-tool` | path-policy on the target path, dependency-policy on manifest edits | block on `never`, warn on `ask_first` |
| `stop-check` | verification_status complete, STATE and ledger valid, no unverified done claim | refuse the success claim |
| `pre-commit` | path-policy on the staged diff, dependency-policy, schema validation | block the commit |

## 4. Validator (`agentos`)

The validator is Python 3, standard library only. It has no third-party
dependencies, so it runs on any macOS or Linux machine, or in CI, with no
install step. This matches the report's guidance to keep tools pinned,
minimal, and deterministic. Schema conformance uses a small hand-rolled
JSON Schema checker, not an external library, so the zero-dependency
guarantee holds.

Subcommands, run as `agentos <subcommand>` or `./bin/agentos <subcommand>`:

- `agentos state [FILE]` checks `STATE.yaml` against the task-state schema.
- `agentos ledger [FILE]` checks each ndjson line against the evidence schema.
- `agentos diff [--staged | A..B]` checks a git diff against the path policy.
  It reports pass or fail plus the exact violations.
- `agentos rules [AGENTS.md]` checks the size and structure of the rule file.
- `agentos skills` lints the skill manifest against `.claude/skills/*`.
- `agentos deps` scans manifests against the dependency policy.
- `agentos all` runs every check. It exits nonzero on any failure.

Each check prints its evidence grade next to its result. Pass `--json` for
machine-readable output, meant for CI.

Exit codes:

- `0` means every check passed.
- `1` means at least one check found a violation.
- `2` means a config or usage error, such as a missing file or a bad flag.

## 5. Repository layout (v0.1, only what is built)

```
agent-os/
├── README.md
├── WHITEPAPER.md
├── SPEC.md
├── ROADMAP.md
├── schemas/
│   ├── task-state.schema.json
│   ├── evidence.schema.json
│   └── skill.schema.json
├── policies/
│   ├── path-policy.yaml
│   └── dependency-policy.yaml
├── templates/                  # skeleton copies for bin/bootstrap
├── examples/
│   └── subject/                # one populated instance, derived from a real repo
├── hooks/
│   ├── pre-tool
│   ├── stop-check
│   └── pre-commit
├── bin/
│   ├── agentos                 # validator entry point
│   └── bootstrap               # copies skeleton artifacts into a target repo
├── agentos/                    # Python stdlib package (the validator)
│   ├── cli.py
│   ├── jsonschema_min.py
│   ├── checks/
│   │   ├── state.py
│   │   ├── ledger.py
│   │   ├── diff.py
│   │   ├── rules.py
│   │   ├── skills.py
│   │   └── deps.py
│   └── grades.py
└── tests/
```

## 6. Non-goals for v0.1

agent-os v0.1 does not build:

- An agent runtime, orchestrator, or model adapter.
- A skill promotion or deprecation pipeline. v0.1 ships a manifest format
  and a lint only.
- A workflow state-machine engine.
- A dashboard, telemetry sink, or knowledge graph.

These stay documented and unbuilt. See `ROADMAP.md` for the gate each one
needs before it gets built.
