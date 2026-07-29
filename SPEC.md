# SPEC.md - agent-os v0.2

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

Extra sections may follow the six required ones. The skeleton template adds
an operating procedure section that tells the agent how to maintain the
other artifacts.

Narrative belongs in linked docs, not in `AGENTS.md`.

The file has a size budget, checked by line count. The soft cap is about
150 non-blank lines. The validator warns past the soft cap. The hard cap is
about 250 non-blank lines. The validator fails past the hard cap. This
budget stops rule-file bloat, a known failure mode for agent context.

`CLAUDE.md`, and any future `.cursor` file, is a pointer file of five lines
or fewer. It points at `AGENTS.md` and adds nothing else. This keeps one
operative source of truth with many entry points, so the spec stays
model-independent. The validator does not currently check this pointer
file. The five-line limit is a convention the agent follows, not a rule
`agentos` enforces in v0.1.

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

The validator checks `never` first, then `ask_first`, then `may_edit`. A
path no glob matches is reported as outside declared scope, a warning.
The skeleton template ships `may_edit: ["*"]`, so a new repo starts open
and the warnings start to mean something once the lists fill in.

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
| `pre-tool` | path-policy on the tool call's target path, read from the hook's stdin JSON (`agentos hook-pre-tool`) | exit 2 (block) on `never`; exit 1 (warn) on `ask_first` or an undeclared path |
| `pre-commit` | path-policy and dependency-policy on the staged diff (`agentos diff --staged`, `agentos deps`) | block the commit (any nonzero exit) |
| `stop-check` | STATE and ledger valid against their schemas (`agentos hook-stop`) | exit 2 (refuse the success claim) |

Claude Code and the validator use different exit-code contracts. The
validator exits 1 on a violation. A Claude Code PreToolUse or Stop hook
blocks only on exit 2; any other nonzero code is a non-blocking warning.
The `hook-pre-tool` and `hook-stop` subcommands do this mapping. Both
fail open with exit 0 on a config error: a guardrail that cannot load its
inputs must not wedge the editor. A git pre-commit hook blocks on any
nonzero exit, so `pre-commit` calls the plain validator subcommands.

`pre-tool` does not check dependency-policy. `pre-commit` does not run
schema validation. `stop-check` does not itself cross-check a "done" claim
against `verification_status`. "No unverified done claim" is a convention
the agent follows when it reports success, not a check `agentos` enforces
in v0.2.

Two deployment models exist. In the vendored model, the target repo
carries its own copy of `bin/agentos` and the `agentos/` package, and the
reference hooks under `hooks/` find them with `git rev-parse`. agent-os
uses this model on itself. In the init model, `agentos init` writes hooks
that point at one shared agent-os checkout by absolute path; that checkout
becomes a permanent dependency of every repo it wires. Both models use
`$CLAUDE_PROJECT_DIR` paths in `.claude/settings.json`, so the settings
file is safe to commit.

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
- `agentos deps` scans manifests against the dependency policy. It skips
  version control, vendored dependencies, and build output by default
  (`node_modules`, `.git`, `bin`, `obj`, `dist`, `build`, `packages`, and
  similar). The policy `ignore` list adds more directory names to skip.
- `agentos all` runs every check. It exits nonzero on any failure.
- `agentos init [DEST]` wires a repo for use. It copies the skeleton
  artifacts, writes a `CLAUDE.md` pointer at `AGENTS.md`, installs a git
  `pre-commit` hook, writes the Claude Code hook wrappers under
  `.claude/hooks/`, and writes `.claude/settings.json` when that file
  does not exist. When it does exist, init prints a snippet to merge. It
  never overwrites a file that exists.
- `agentos hook-pre-tool` serves the Claude Code PreToolUse hook. It
  reads the tool call JSON on stdin and checks the target path against
  the path policy. Exit 2 blocks, exit 1 warns, exit 0 allows.
- `agentos hook-stop` serves the Claude Code Stop hook. It checks STATE
  and the ledger. Exit 2 refuses the done claim, exit 0 allows it.

Each check prints its evidence grade next to its result. Pass `--json` for
machine-readable output, meant for CI.

Exit codes:

- `0` means every check passed.
- `1` means at least one check found a violation.
- `2` means a config or usage error, such as a missing file or a bad flag.

## 5. Repository layout (v0.2, only what is built)

```
agent-os/
├── README.md
├── WHITEPAPER.md
├── SPEC.md
├── ROADMAP.md
├── AGENTS.md                   # operative rules for work on agent-os itself
├── CLAUDE.md                   # pointer at AGENTS.md
├── STATE.yaml                  # live task state for work on agent-os itself
├── evidence/
│   └── ledger.ndjson           # claims with proof, for agent-os itself
├── .claude/
│   ├── settings.json           # the repo's own Claude Code hook registration
│   └── skills/
├── schemas/
│   ├── task-state.schema.json
│   ├── evidence.schema.json
│   └── skill.schema.json
├── policies/
│   ├── path-policy.yaml        # policy for the agent-os repo itself
│   └── dependency-policy.yaml
├── skills/
│   └── index.yaml
├── templates/                  # skeleton copies for bin/bootstrap and agentos init
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
│   ├── hooks.py                # Claude Code hook subcommands, exit-code mapping
│   ├── initcmd.py              # agentos init
│   ├── bootstrap.py
│   ├── yaml_min.py
│   ├── jsonschema_min.py
│   ├── pathmatch.py
│   ├── gitutil.py
│   ├── result.py
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

### 5.1 Self-governance

agent-os governs its own codebase with the same artifacts it defines. The
repo root carries a populated `AGENTS.md`, `STATE.yaml`, evidence ledger,
policies, skill index, and `.claude/settings.json`, and the reference
hooks under `hooks/` run against the repo's own `bin/agentos`.
`tests/test_self_governance.py` is the self-compile gate: it runs
`agentos all` on the repo itself and on a fresh init destination, and
both must exit 0.

## 6. Non-goals for v0.2

agent-os v0.2 does not build:

- An agent runtime, orchestrator, or model adapter.
- A skill promotion or deprecation pipeline. v0.1 ships a manifest format
  and a lint only.
- A workflow state-machine engine.
- A dashboard, telemetry sink, or knowledge graph.

These stay documented and unbuilt. See `ROADMAP.md` for the gate each one
needs before it gets built.
