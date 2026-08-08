# SPEC.md - agent-os (release 0.6.0)

Status: normative. This file states the rules the validator checks.

Source design doc: `docs/superpowers/specs/2026-07-29-agent-os-spec-v0.1-design.md`.
Evidence report: `WHITEPAPER.md`.

## 1. What this spec is

agent-os is a repository-owned, model-independent spec for agentic coding.
It ships with a thin validator that checks the spec by machine, not by prose.

Model-independent means concretely: `AGENTS.md` is the one rule file, and
opencode, Codex, and Cursor read it natively. Pointer files carry the
rules to the harnesses that need one (`CLAUDE.md`, `GEMINI.md`,
`.github/copilot-instructions.md`). Enforcement adapters exist for Claude
Code (hooks), opencode (a plugin), and any git flow (a pre-commit hook).
See section 3.

This is a pre-codebase bootstrap. You copy agent-os into a target repository before
the agent reads any code in that repository. The normative files ship as skeleton
templates, not filled-in data. As work proceeds, the agent fills in
`STATE.yaml`, appends to `evidence/ledger.ndjson`, and updates the policy
files. The validator checks conformance at every step.

`examples/subject/` shows one populated instance, derived from a real repository.

## 2. Normative artifacts

Six artifacts make up the normative spec surface. Each has a schema or a
fixed format, and the validator checks each one. The grade next to each
artifact is its evidence grade from `WHITEPAPER.md`.

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

The file has a size budget. Line count checks it. The soft cap is about
150 non-blank lines. The validator warns past the soft cap. The hard cap is
about 250 non-blank lines. The validator fails past the hard cap. This
budget stops rule-file bloat, a known failure mode for agent context.

Pointer files (`CLAUDE.md`, `GEMINI.md`,
`.github/copilot-instructions.md`, and any future equivalent) are five
lines or fewer. Each points at `AGENTS.md` and adds nothing else. This
keeps one operative source of truth with many entry points, so the spec
stays model-independent. The validator does not currently check these
pointer files. The five-line limit is a convention the agent follows,
not a rule `agentos` enforces in 0.4.

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
stop_readiness: ready | blocked   # optional
criteria: [{ id: string, statement: string, status: active | obsolete }]   # optional
task_started: <ISO 8601 UTC>   # optional
```

Each field in `verification_status` holds one of: `pass`, `fail`, `n/a`,
`pending`.

Set `stop_readiness: ready` to claim done. That is the trigger for the
verdict gates in section 3: the stop adapters then grade
`acceptance_criteria` and `verification_status`, and run the configured
test command. Any other value, or an absent field, means no done claim,
and the stop adapters check schema validity only. A mid-task stop stays
free: an agent that pauses to ask a question does not claim done.

An explicit completion command, `agentos done`, complements the stop
event. It always invokes the verdict gate: it rejects a missing,
blocked, or malformed `stop_readiness` with an actionable reason, not
a silent allow. The stop event (`agentos hook-stop`) fires on every
turn end. It gates only on a voluntary `ready`, so an agent that pauses
to ask a question does not claim done. `done` is the finalization
command that no agent can bypass by leaving readiness unset. A prose
claim is not a done claim.

A compaction rule applies. When the context shortens, do not summarize away
`acceptance_criteria`, `confirmed_facts`, `decisions`, `failed_hypotheses`,
or `verification_status`. These fields must stay intact.

`criteria` is an optional list of acceptance criteria with stable ids. When
present, a ledger entry may set `criterion` to one of these ids to link a
proof to the criterion it satisfies. The ledger check then verifies that
every `active` criterion has at least one confirmed proof. A criterion with
`status: obsolete` is a retired requirement and needs no proof.
`acceptance_criteria` stays the human-readable list the verdict gate checks
for non-empty. `criteria` adds the linkage the ledger grades.

`task_started`, when set, is an ISO 8601 UTC timestamp. A ledger entry with
`ts` earlier than `task_started` is stale. A stale live proof blocks the
done claim.

### 2.3 Evidence ledger (`evidence/ledger.ndjson`)

The ledger is the fact-versus-inference layer. It is append-only. Each line
holds one JSON object, checked against `schemas/evidence.schema.json`:

```json
{ "claim": "", "status": "confirmed|inferred|unverified", "evidence_ref": "",
  "source_type": "tool|file|test|policy|human", "verifier": "", "hash": "", "ts": "",
  "version": 1, "id": "", "criterion": "", "supersedes": "" }
```

The caller supplies `ts`. The validator does not generate time, so results
stay deterministic. `hash` is a content hash of the referenced evidence,
when one applies.

To supersede a claim, append a new entry that references the old claim. Do
not mutate or delete a past entry.

An entry without `version` is v0 (legacy): the validator checks its shape
against this schema only. An entry with `version: 1` is v1 and must
also pass the semantic layer. The layer requires a non-empty `claim`
and `evidence_ref`, an ISO 8601 UTC `ts`, a non-empty `verifier` when
`status` is `confirmed`, and a non-empty `hash` when `source_type` is
`test` or `tool` and `status` is `confirmed`. The `version` enum is `[1]`. Any other integer is a config
error. The validator never weakens the v0 bar. V1 is extra strictness an
entry opts into.

`criterion` references an `id` in `STATE.yaml` `criteria`. When STATE has
`criteria`, a v1 entry's `criterion` must name a real id. The ledger check
reports every `active` criterion with no confirmed proof.

`supersedes` references a line number (for a v0 entry, which has no id) or
an id (for a v1 entry). A superseded entry is history and the validator
does not grade its drift. To migrate a v0 entry to v1, append a v1 entry
that re-states the claim and sets `supersedes` to the old line number. Do
not edit or delete the old line.

For a v1 entry with `source_type: file`, the validator resolves
`evidence_ref` as a path and, when the entry sets `hash`, recomputes the file hash.
An unresolvable path or a hash mismatch raises an error for a live
proof of an active criterion (it blocks the done claim). It raises a
warning for a free-standing fact. It stays silent when the entry
supersedes another or its criterion retires. A live proof has an
active `criterion` id and no later `supersedes` names its `id`.

### 2.4 `policies/path-policy.yaml`

The path policy states where the agent may edit files, without reading the
whole diff by hand:

```yaml
may_edit: [glob]      # the agent may edit these paths freely
ask_first: [glob]     # these paths need explicit approval first
never: [glob]         # these paths are a hard block
```

The validator checks `never` first, then `ask_first`, then `may_edit`. The validator reports a path no glob matches as outside declared
scope, a warning.
The skeleton template ships `may_edit: ["*"]`, so a new repository starts open
and the warnings start to mean something once the lists fill in.

`examples/subject/policies/path-policy.yaml` derives this from a real
repository's rules: library and third-party code as `may_edit`, app and suite
code as `ask_first`, and generated or render files as `never`.

### 2.5 `skills/index.yaml` and skill schema

The skill manifest lists each skill's name, version, owner, purpose,
when-to-use text, inputs, outputs, tests, safety constraints, and
provenance. Its schema lives at `schemas/skill.schema.json`.

The validator lints the manifest. It checks that every
`.claude/skills/*/SKILL.md` has a matching manifest entry, that required
fields are present, and that the version string is valid semver.

v0.1 shipped the manifest and the lint only. It does not ship a promotion or
benchmark pipeline for skills. See `ROADMAP.md`.

The `ste-writing` skill ships a vendored domain glossary
(`.claude/skills/ste-writing/glossary.json`) as a data asset. The
glossary holds doc-verified controlled terminology for 16 software,
SRE, and DevOps domains. Its sync discipline is a custom check, documented
in section 3.3.

### 2.6 `policies/dependency-policy.yaml`

The dependency policy names banned or required packages, checked against a
target repository's manifests:

```yaml
banned: [{ name: "Moq", reason: "org rule" }, { name: "AutoMapper", reason: "org rule" }]
required: []
ecosystems: [nuget]
```

The lint scans manifest files, such as `*.fsproj`, `*.csproj`,
`packages.config`, or `package.json`, for banned names. The `ecosystems`
list is open. Future ecosystems, such as npm or pip, can extend it.

## 3. Hook contract and harness adapters

The checks are harness-neutral. Each coding agent gets a thin adapter
that calls them. The reference hooks under `hooks/` are the Claude Code
and git adapters for a vendored install. The opencode adapter is one
plugin file. `agentos init` writes all three.

| Adapter | Fires on | Checks | Fail behavior |
|---|---|---|---|
| git `pre-commit` (`hooks/pre-commit`) | commit | path-policy and dependency-policy on the staged diff (`agentos diff --staged`, `agentos deps`) | block the commit (any nonzero exit) |
| Claude Code PreToolUse (`.claude/hooks/agentos-pre-tool`) | Edit, Write, MultiEdit | path-policy on the tool call's target path, read from stdin JSON (`agentos hook-pre-tool`) | exit 2 (block) on `never`. Exit 1 (warn) on `ask_first` or an undeclared path |
| Claude Code PostToolUse (`.claude/hooks/agentos-post-tool`) | every tool call | none. Appends the tool and target to `evidence/trace.ndjson` (`agentos hook-post-tool`) | none: instrumentation, exit 0 always |
| Claude Code PreCompact (`.claude/hooks/agentos-pre-compact`) | compaction | none. Prints a reminder to refresh STATE.yaml, plus any STATE schema errors (`agentos hook-pre-compact`) | none: advisory, exit 0 always |
| Claude Code Stop (`.claude/hooks/agentos-stop-check`) | session stop | STATE and ledger valid against their schemas. When STATE sets `stop_readiness: ready`, also the verdict gates (`agentos hook-stop`) | exit 2 (refuse the success claim) |
| opencode `tool.execute.before` (`.opencode/plugins/agentos.js`) | edit, write, multiedit, patch | path-policy on the target path (`agentos check-path`) | throw (block) on `never`. Log a warning on `ask_first` |
| opencode `tool.execute.after` (same plugin) | every tool call | none. Appends the tool and target to the trace (`agentos hook-post-tool`) | none: instrumentation, errors ignored |
| opencode `session.idle` (same plugin) | session idle | `agentos done` when `stop_readiness: ready` (skips the spawn otherwise) | refuse the done claim with an actionable reason. Advisory toast and log (the git pre-commit hook is the hard gate) |

Claude Code and the validator use different exit-code contracts. The
validator exits 1 on a violation. A Claude Code PreToolUse or Stop hook
blocks only on exit 2. Any other nonzero code is a non-blocking warning.
The `hook-pre-tool` and `hook-stop` subcommands do this mapping, and the
opencode plugin maps exit 2 to a thrown error, which is how opencode
blocks a tool call. All adapters fail open on a config error: a
guardrail that cannot load its inputs must not wedge the editor. A git
pre-commit hook blocks on any nonzero exit, so `pre-commit` calls the
plain validator subcommands.

`pre-tool` and the opencode edit check do not check dependency-policy.
`pre-commit` does not run schema validation. The verdict gates run only
when STATE sets `stop_readiness: ready`. Then the stop adapters refuse
the done claim (exit 2) unless `acceptance_criteria` is non-empty and
every `verification_status` field is `pass` or `n/a`. An adapter may
also pass `--run-tests CMD`. The gate then runs CMD and refuses the
claim when CMD exits nonzero. Without the flag, the verdict values stay
self-reported. The flag is repository wiring, not a validator default: only
the repository knows its test command.

The trace file `evidence/trace.ndjson` is local instrumentation, not a
seventh artifact. No check grades it, and it belongs in `.gitignore`.
Its purpose is the context-accounting work in `ROADMAP.md`.

Two deployment models exist. In the vendored model (the default in 0.4.0),
`agentos init` copies `bin/`, `agentos/`, `schemas/`, and `VERSION` into
the target repository under `.agent-os/`. The generated hook wrappers and the
opencode plugin reference this vendored copy with relative paths, so a
fresh clone works without an external agent-os checkout. In the shared
model (`agentos init --shared PATH`), the generated adapters point at one
shared agent-os checkout by absolute path. That checkout becomes a
permanent dependency of every repository it wires, and the model is not
portable. Both models use `$CLAUDE_PROJECT_DIR` paths in
`.claude/settings.json`, so the settings file is safe to commit.

`agentos upgrade` refreshes the vendored runtime (`.agent-os/`) from a
release tarball, leaving user-owned files (`AGENTS.md`, `STATE.yaml`,
`evidence/`, `policies/`, `skills/`, `.claude/settings.json`,
`.opencode/plugins/agentos.js`) untouched. The hook wrappers and opencode
plugin are adapter glue: upgrade overwrites them. The `.agent-os/hooks/`
extension directories (section 3.1) are user-owned and never overwritten.

### 3.1 Hook extension directories

A repository that needs checks the native schema cannot express (example: block
edits to `App/Core/` unless a confirmation file exists, run a formatter
after every edit, refuse done unless someone updates the changelog) adds
shell scripts to hook extension directories:

```
.agent-os/hooks/
├── pre-tool.d/        # runs after the built-in path-policy check
│   └── block-app-core.sh
├── post-tool.d/       # runs after the built-in trace append
│   └── run-formatter.sh
└── stop.d/            # runs after the built-in verdict gate
    └── require-changelog.sh
```

The built-in hook wrapper runs its check first, then every executable
file in the sibling `.d` directory, in sorted filename order. The
exit-code contract is the same as the built-in hooks: exit 2 blocks or
refuses, exit 1 warns, exit 0 passes. A directory that is absent or
empty is a no-op. `agentos upgrade` never touches `.d` contents.
`agentos doctor` reports which extension scripts are present.

### 3.2 Custom checks in `agentos all`

A repository that needs its own checks as graded lines in the `agentos all`
output adds them to `policies/custom-checks.yaml`:

```yaml
checks:
  - name: changelog-updated
    command: "git diff --name-only HEAD | grep -q CHANGELOG"
    expect: pass
    grade: A
    on_fail: error
```

`agentos all` runs these after the six built-in checks. Each prints
`[PASS] name (grade A)` or `[FAIL] name (grade A)`. A failing
`on_fail: error` check blocks `agentos done`. A `warn` check does not.
The file is optional. Absent means no custom checks. `agentos upgrade`
never overwrites it.

### 3.3 Skill data provenance: the ste-writing glossary

The `ste-writing` skill comes from the upstream `agent-skills`
repository. Its domain glossary is data, not code, so a separate discipline
governs when an update is necessary.

Two checks live in `.claude/skills/ste-writing/scripts/glossary-sync.py`.
The script imports the standard library only, so it keeps the
zero-dependency guarantee.

The regular check (`glossary-sync.py --check`) runs in `agentos all`
as a custom check with `on_fail: warn`. It makes no network call. It
validates the glossary structure and compares the local content hash
against a pinned provenance file
(`.claude/skills/ste-writing/glossary.provenance.json`). The hash
covers the normative term content and excludes volatile metadata, such
as the `generated` date. A mismatch means the local glossary drifted
from its last deliberate sync. The check warns, it does not block
`agentos done`, because a stale glossary does not break the validator.

The necessity check (`glossary-sync.py --check-upstream`) is on demand
or in a CI cron. It fetches the upstream glossary, compares the
normative term content, and reports whether an update is absolutely
necessary. An update is necessary only when term content changes: terms
added, removed, or modified. A difference confined to volatile metadata is not
necessary. The report lists the domains and terms that differ.

`glossary-sync.py --pin` rewrites the provenance file after a
deliberate sync. It records the upstream commit SHA, the sync date, the
content hash, and the skill version. Run it after pulling a glossary
update from upstream, so the regular check stays green.

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
- `agentos init [DEST]` wires a repository for use. By default it vendors the
  runtime (`.agent-os/`) into the target so the install is portable. With
  `--shared PATH`, it writes adapters that point at a shared checkout.
  It copies the skeleton artifacts. It writes pointer files at
  `AGENTS.md` (`CLAUDE.md`, `GEMINI.md`,
  `.github/copilot-instructions.md`). It installs a git `pre-commit`
  hook, writes the Claude Code hook wrappers under `.claude/hooks/`,
  writes the opencode plugin under `.opencode/plugins/`, and writes
  `.claude/settings.json` when that file does not exist. When it does
  exist, init prints a snippet to merge. It never overwrites a file
  that exists.
- `agentos upgrade [--to VERSION] [--check]` refreshes the vendored
  runtime in `.agent-os/` from a release tarball. Without `--to`, it
  fetches the latest release. `--check` compares the local `VERSION`
  against the latest release tag and reports only. Upgrade overwrites
  adapter glue (hook wrappers, opencode plugin) and never touches
  user-owned files. When a schema `schema_version` is higher than the
  data conforms to, the registered migrator runs.
- `agentos doctor` audits enforcement wiring: vendored runtime present
  and version matches, `.claude/settings.json` references the hooks,
  `.opencode/plugins/agentos.js` present, `core.hooksPath` set and
  pre-commit executable, `AGENTS.md` present and valid. Reports a
  per-harness matrix. Exit 0 = all wired, exit 1 = something broken.
- `agentos --version` prints the release version, schema versions, and
  adapter protocol version.
- `agentos hook-pre-tool` serves the Claude Code PreToolUse hook. It
  reads the tool call JSON on stdin and checks the target path against
  the path policy. Exit 2 blocks, exit 1 warns, exit 0 allows.
- `agentos hook-stop` serves the Claude Code Stop hook and the opencode
  idle check. It checks STATE and the ledger. Exit 2 refuses the done
  claim, exit 0 allows it. When STATE sets `stop_readiness: ready`, it
  also grades the verdict gates: non-empty `acceptance_criteria`, every
  `verification_status` field at `pass` or `n/a`, and the command given
  with `--run-tests CMD`, when the adapter passes one, must exit 0.
- `agentos hook-post-tool` serves the Claude Code PostToolUse hook and
  the opencode `tool.execute.after` event. It appends one JSON line,
  with timestamp, tool, and target, to the trace file (default
  `evidence/trace.ndjson`). Exit 0 always.
- `agentos hook-pre-compact` serves the Claude Code PreCompact hook. It
  prints a reminder to refresh STATE.yaml before compaction, plus any
  STATE schema errors. Exit 0 always.
- `agentos check-path FILE...` checks one or more paths against the path
  policy with the editor-time contract: exit 2 on `never`, exit 1 on
  `ask_first` or an undeclared path, exit 0 otherwise. Harness adapters,
  such as the opencode plugin, call this.
- `agentos verify` reads `policies/verification.yaml`, runs each
  configured command (`format`, `compile`, `tests`, `policy`,
  `security`), derives the status from the exit code, records the
  command, exit code, timestamp, and an output hash in
  `evidence/ledger.ndjson`, and writes the derived status into
  `STATE.yaml`. A `null` or omitted command marks that verifier
  unavailable (status `n/a`). A timeout or a non-runnable command is a
  fail. The verdict comes from execution, not a self-reported value.
  Each verifier value can be a string (the command) or a mapping. A
  mapping holds a `command` key and an optional `assert` block. After a
  zero exit, the assert block checks the captured output. The `contains`
  key lists strings that must be present. The `excludes` key lists
  strings that must be absent. A failed assert marks the verifier fail.
  The ledger records the pattern as `assert missing: "..."` or
  `assert forbidden: "..."`.   This catches a false green: a verifier
  that exits 0 without doing the work. A nonzero exit is still a fail.
  The assert does not run in that case. When the assert is not a
  mapping, or when a list entry is not a string, the config is invalid
  (exit 2).
- `agentos done` is the explicit completion gate. It runs the verdict
  gate unconditionally: STATE and the ledger must hold valid data,
  `stop_readiness` must read `ready` (the gate rejects a missing or
  blocked value with an actionable reason), `acceptance_criteria` must be
  non-empty, every `verification_status` field must read `pass` or `n/a`,
  and the command given with `--run-tests CMD`, when passed, must exit 0.
  When a `policies/verification.yaml` is present, `done` runs `verify`
  first, so execution derives the status. `--no-verify` trusts
  the self-reported status.

Each check prints its evidence grade next to its result. Pass `--json` for
machine-readable output, meant for CI.

Exit codes:

- `0` means every check passed.
- `1` means at least one check found a violation.
- `2` means a config or usage error, such as a missing file or a bad flag.

## 5. Repository layout (0.5.0, built items only)

```
agent-os/
├── README.md
├── WHITEPAPER.md
├── SPEC.md
├── ROADMAP.md
├── AGENTS.md                   # operative rules for work on agent-os itself
├── CLAUDE.md                   # pointer at AGENTS.md (Claude Code)
├── GEMINI.md                   # pointer at AGENTS.md (Gemini CLI)
├── .github/
│   └── copilot-instructions.md # pointer at AGENTS.md (Copilot)
├── STATE.yaml                  # live task state for work on agent-os itself
├── evidence/
│   ├── ledger.ndjson           # claims with proof, for agent-os itself
│   └── trace.ndjson            # local tool-call log, gitignored, not graded
├── .claude/
│   ├── settings.json           # the repo's own Claude Code hook registration
│   └── skills/
├── .opencode/
│   └── plugins/
│       └── agentos.js          # the repo's own opencode adapter
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
│   ├── post-tool
│   ├── pre-compact
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
│   ├── version.py              # release, schema, and adapter protocol versions
│   ├── yaml_min.py
│   ├── jsonschema_min.py
│   ├── pathmatch.py
│   ├── gitutil.py
│   ├── result.py
│   ├── upgrade.py              # agentos upgrade (tarball fetch + refresh)
│   ├── doctor.py               # agentos doctor (enforcement audit)
│   ├── checks/
│   │   ├── state.py
│   │   ├── ledger.py
│   │   ├── diff.py
│   │   ├── rules.py
│   │   ├── skills.py
│   │   ├── deps.py
│   │   └── custom.py           # policies/custom-checks.yaml runner
│   └── grades.py
├── VERSION                     # release semver (source of truth for the tag)
└── tests/
```

### 5.1 Self-governance

agent-os governs its own codebase with the same artifacts it defines. The
repository root carries a populated `AGENTS.md`, `STATE.yaml`, evidence ledger,
policies, skill index, and pointer files. The repository commits both
enforcement adapters: `.claude/settings.json` for Claude Code and
`.opencode/plugins/agentos.js` for opencode. The reference hooks under
`hooks/` run against the repository's own `bin/agentos`.
`tests/test_self_governance.py` is the self-compile gate: it runs
`agentos all` on the repository itself and on a fresh init destination, and
both must exit 0.

## 6. Non-goals for 0.5.0

agent-os 0.5.0 does not build:

- An agent runtime, orchestrator, or model adapter.
- A skill promotion or deprecation pipeline. The manifest format and
  lint shipped early and stay as-is.
- A workflow state-machine engine.
- A dashboard, telemetry sink, or knowledge graph.

These stay documented and unbuilt. See `ROADMAP.md` for the gate each one
needs before anyone builds them.

## 7. Versioning

Three version dimensions exist. They are independent and named
distinctly so no ambiguity arises between the spec surface, the CLI
release, and the schemas.

| Dimension | Source of truth | Form | Bumped when |
|---|---|---|---|
| Release version | `VERSION` file at repository root | one semver, the git tag | any shipped change |
| Schema version | `schema_version` integer at the top of each schema file | additive, per file | someone adds or removes a schema field, or changes its type |
| Adapter protocol | `ADAPTER_PROTOCOL` integer in `agentos/version.py` | one integer | the hook stdin/stdout contract or exit-code mapping changes |

`agentos --version` reports all three: `agentos 0.5.0 (schema
evidence=1, skill=1, task-state=1; adapter protocol 1)`.

### Compatibility rules

- A schema `schema_version` bump is additive: a validator that knows
  version N accepts data written for version N or lower. A migrator
  upgrades older data when a higher version arrives.
- An adapter protocol bump means a generated hook wrapper or opencode
  plugin from an older release may not work with a newer runtime.
  `agentos upgrade` refreshes the adapter glue.
- The release version follows semver. In the 0.x line, a minor bump
  marks a feature addition. A patch bump marks a fix.

### Release discipline

Every merge that ships gets a GitHub release with a semver tag and
release notes. The release attaches a tarball of the `.agent-os/` tree
for `agentos upgrade` to fetch.
