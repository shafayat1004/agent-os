# agent-os

A repository-owned, model-independent spec for agentic coding, plus a thin
validator that checks it by machine.

Read `SPEC.md` for the normative rules: the six artifacts, the hook
contract, and the validator's subcommands and exit codes. Read
`ROADMAP.md` for the modules the spec leaves unbuilt, and the gate each one
needs before work starts. Read `WHITEPAPER.md` for the evidence behind the
design choices.

## Quick start

Copy the skeleton artifacts into a target repo:

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

Add `--json` to any subcommand for machine-readable output. Exit code `0`
means every check passed. Exit code `1` means a check found a violation.
Exit code `2` means a config or usage error.

`agentos` needs Python 3.8 or later and no third-party packages.

See `examples/subject/` for one populated instance, derived from a real
repo.
