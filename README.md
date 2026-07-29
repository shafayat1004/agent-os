# agent-os

A repository-owned, model-independent spec for agentic coding, plus a thin
validator that checks it by machine.

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
- Not a git repo yet: everything works except the pre-commit hook,
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
clone around. To vendor agent-os into your repo instead, see the
deployment models in `SPEC.md` section 3.

### Prove it works

```bash
/path/to/agent-os/bin/agentos all
```

Exit code `0` means every check passed. Exit code `1` means a check
found a violation. Exit code `2` means a config or usage error.

The folder alone does not make an agent obey the rules. The agent reads
the rules only when `CLAUDE.md` points at `AGENTS.md`, and a violation
is blocked only when the hooks are active. `init` does both. The Claude
Code hooks exit 2 on a violation, the one code Claude Code blocks on.

agent-os runs on its own rules. This repo carries the same six
artifacts, and `./bin/agentos all` passes here.
`tests/test_self_governance.py` keeps that true.

To copy only the skeleton artifacts, without the wiring:

```bash
/path/to/agent-os/bin/bootstrap /path/to/target-repo
```

Run single checks against your repo's files:

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

Put `--json` before the subcommand for machine-readable output, for
example `./bin/agentos --json state STATE.yaml`.

See `examples/subject/` for one populated instance, derived from a real
repo.
