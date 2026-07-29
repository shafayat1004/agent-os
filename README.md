# agent-os

A repository-owned, model-independent spec for agentic coding, plus a thin
validator that checks it by machine.

Read `SPEC.md` for the normative rules: the six artifacts, the hook
contract, and the validator's subcommands and exit codes. Read
`ROADMAP.md` for the modules the spec leaves unbuilt, and the gate each one
needs before work starts. Read `WHITEPAPER.md` for the evidence behind the
design choices.

## Quick start

For a new repo, wire everything in one step:

```bash
./bin/agentos init /path/to/target-repo
```

`init` copies the skeleton artifacts, writes a `CLAUDE.md` pointer at
`AGENTS.md`, installs a git `pre-commit` hook, and writes the Claude Code
hook wrappers. It then prints a settings snippet to paste into
`.claude/settings.json`. `init` never overwrites a file that exists, so it
is safe to run again.

The folder alone does not make an agent obey the rules. The agent reads the
rules only when `CLAUDE.md` points at `AGENTS.md`, and a violation is
blocked only when the hooks are active. `init` does both.

To copy only the skeleton artifacts, without the wiring:

```bash
./bin/bootstrap /path/to/target-repo
```

Run the validator against your repo's files:

```bash
./bin/agentos state STATE.yaml
./bin/agentos ledger evidence/ledger.ndjson
./bin/agentos diff --staged
./bin/agentos deps
./bin/agentos skills
./bin/agentos rules AGENTS.md
./bin/agentos all
```

Put `--json` before the subcommand for machine-readable output, for
example `./bin/agentos --json state STATE.yaml`. Exit code `0` means every
check passed. Exit code `1` means a check found a violation. Exit code `2`
means a config or usage error.

`agentos` needs Python 3.8 or later and no third-party packages.

See `examples/subject/` for one populated instance, derived from a real
repo.
