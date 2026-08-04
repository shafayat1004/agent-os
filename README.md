# agent-os

agent-os is a repository-owned, model-independent spec for agentic coding,
plus a zero-dependency validator that checks it by machine. It exists
because the evidence in `WHITEPAPER.md` says agent failures are workflow
failures, not prompt failures: agents claim done without proof, hold
context they never use, and follow rules that nothing enforces. A repository
adopts agent-os before the agent reads any code, and gets six checkable
artifacts, from typed task state to an append-only proof log, plus hooks
that block a `never` path and refuse an unverified done claim. Only what
the evidence grades strongly. The rest waits on `ROADMAP.md`,
with a gate per module.

Supported agents: opencode, Codex, and Cursor read `AGENTS.md` natively.
Claude Code, Gemini CLI, and Copilot get pointer files. Enforcement ships
for Claude Code (hooks), opencode (a plugin), and every git flow (a
pre-commit hook).

Read `SPEC.md` for the normative rules: the six artifacts, the hook
contract, and the validator's subcommands and exit codes. Read
`ROADMAP.md` for the modules the spec leaves unbuilt, and the gate each one
needs before work starts. Read `WHITEPAPER.md` for the evidence behind the
design choices.

## Quick start

You need Python 3.8 or later. There is no install step and no dependency
to fetch.

```bash
git clone https://github.com/shafayat1004/agent-os.git
```

### Set up a new codebase

One command wires everything:

```bash
cd your-repo
/path/to/agent-os/bin/agentos init
```

That is the whole setup. The git pre-commit hook, the Claude Code
hooks, and the opencode plugin are active right away: a `never` path
blocks the edit, an invalid `STATE.yaml` blocks the done claim. Then,
when you have a minute:

1. Fill in the `Commands` section of `AGENTS.md` (build, test).
2. Narrow `policies/path-policy.yaml` when some paths need approval.
3. Commit the new files, so your team and every agent share them.

### Set up an existing codebase

The same command, same safety: `init` never overwrites a file that
exists, and it is safe to run again.

```bash
cd your-repo
/path/to/agent-os/bin/agentos init
```

What happens to what you already have:

- An existing `CLAUDE.md` or `AGENTS.md` stays as it is. If your rules
  live in `CLAUDE.md` today, move them into the `AGENTS.md` sections and
  let `CLAUDE.md` become the pointer. One rule file, many entry points.
- An existing `.claude/settings.json` stays as it is. `init` prints a
  hook snippet to merge into it.
- An existing git `pre-commit` hook stays as it is. To merge by hand,
  add these two lines to it:

  ```sh
  "/path/to/agent-os/bin/agentos" diff --staged || exit 1
  "/path/to/agent-os/bin/agentos" deps || exit 1
  ```
- Not a git repository yet: everything works except the pre-commit hook,
  which `init` skips. Run `git init` and run `agentos init` again to
  get it.

### What `init` gives you

- `AGENTS.md`, the operative rule file every supported agent reads,
  plus pointer files (`CLAUDE.md`, `GEMINI.md`,
  `.github/copilot-instructions.md`) for the harnesses that need one.
- `STATE.yaml` and `evidence/ledger.ndjson`, the task state and the
  proof log the Stop adapters check.
- `policies/`, `skills/index.yaml`, the rule inputs for the checks.
- Active enforcement: a git pre-commit hook, Claude Code PreToolUse,
  PostToolUse, PreCompact, and Stop hooks registered in
  `.claude/settings.json`, and an opencode plugin in `.opencode/plugins/`.

The adapters call the agent-os checkout by absolute path, so keep the
clone around. To vendor agent-os into your repository instead, see the
deployment models in `SPEC.md` section 3.

### Prove it works

```bash
/path/to/agent-os/bin/agentos all
```

Exit code `0` means every check passed. Exit code `1` means a check
found a violation. Exit code `2` means a config or usage error.

The folder alone does not make an agent obey the rules. The agent reads
the rules only when `CLAUDE.md` points at `AGENTS.md`, and the hooks
block a violation only when they are active. `init` does both. The Claude
Code hooks exit 2 on a violation, the one code Claude Code blocks on.

agent-os runs on its own rules. This repository carries the same six
artifacts, and `./bin/agentos all` passes here.
`tests/test_self_governance.py` keeps that true.

### Continuous integration

GitHub Actions runs on every pull request and every push to `main`.
The workflow in `.github/workflows/ci.yml` does three things:

- runs the unit test suite (`python3 -m unittest discover -s tests`),
- runs the validator on this repository (`./bin/agentos all`),
- and checks that the opencode adapter still parses (`node --check`).

Each step is a named status check, so a failure names the step that
broke. The matrix covers Python 3.9, 3.11, and 3.13, the supported
range. You can skip local hooks. You cannot skip CI, so CI is the authority
on repository health.

### Claim done

To claim a task done, run `./bin/agentos done`. It always runs the
verification gate:

- `STATE.yaml` and `evidence/ledger.ndjson` must be valid against their
  schemas.
- `stop_readiness` must be `ready`. A missing or `blocked` value is
  rejected with an actionable reason, not silently allowed.
- `acceptance_criteria` must be non-empty.
- Every `verification_status` field must be `pass` or `n/a`. When a
  `policies/verification.yaml` is present, `done` runs `verify` first. A failed verifier or a config that cannot load refuses the claim, it
  never falls back to the self-reported value.
- The test command, when given with `--run-tests CMD`, must exit 0.

A prose claim is not a done claim. The harness stop event
(`agentos hook-stop`) is different: it fires on every turn end and gates
only when the agent declares `stop_readiness: ready`, so an agent that
pauses to ask a question is not claiming done. `done` is the explicit
finalization command that no agent can bypass by leaving readiness unset.

### Verify with real commands

`agentos verify` reads `policies/verification.yaml`, runs each configured
command (`format`, `compile`, `tests`, `policy`, `security`), derives the
status from the exit code, records the command, the exit code, a
timestamp, and an output hash in `evidence/ledger.ndjson`, and writes the
derived status into `STATE.yaml`. `agentos done` runs `verify` first when
a config is present, so the verdict comes from execution, not a
self-reported value. `agentos init` detects common test commands
(unittest, npm test, make test) and wires the repository-conformance check as
`policy`. A `null` or omitted command marks that verifier unavailable
(status `n/a`). A command value that is not a string is a config error.
A timeout or a non-runnable command is a `fail`.

To copy only the skeleton artifacts, without the wiring:

```bash
/path/to/agent-os/bin/bootstrap /path/to/target-repo
```

Run single checks against your repository's files:

```bash
/path/to/agent-os/bin/agentos state STATE.yaml
/path/to/agent-os/bin/agentos ledger evidence/ledger.ndjson
/path/to/agent-os/bin/agentos diff --staged
/path/to/agent-os/bin/agentos deps
/path/to/agent-os/bin/agentos skills
/path/to/agent-os/bin/agentos rules AGENTS.md
```

Two more subcommands serve the Claude Code hooks and are not run by
hand: `hook-pre-tool` reads a tool call as JSON on stdin and exits 2 to
block a `never` path, and `hook-stop` exits 2 to refuse a done claim
when `STATE.yaml` or the ledger is invalid.

Two subcommands are the completion protocol: `agentos verify` runs the
configured project verifiers and writes the derived status into
`STATE.yaml`, and `agentos done` is the explicit completion gate that
runs the verdict and rejects a missing or blocked `stop_readiness`. See
"Claim done" and "Verify with real commands" above.

Put `--json` before the subcommand for machine-readable output, for
example `./bin/agentos --json state STATE.yaml`.

See `examples/subject/` for one populated instance, derived from a real
repository.
