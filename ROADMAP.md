# ROADMAP.md - agent-os future modules

Status: documented, not built. Each module lists its evidence grade and the
gate it must pass before work starts. A gate is the measurement or proof
that must exist first. Building ahead of the gate repeats the mistake
`WHITEPAPER.md` warns against: a large system built before its parts are
proven.

See `SPEC.md` for the six modules already built in v0.1.

| Module | Grade | Gate to build |
|---|---|---|
| Skill promotion and deprecation pipeline | Emerging | A skill regression suite and a retrieval-frequency metric both exist |
| Context accounting (retrieved versus used) | B+ | Instrumentation that logs retrieval and its effect on the diff exists |
| Workflow state-machine engine | Emerging | At least three workflows run stable as YAML the validator checks |
| Telemetry and dashboard | Mostly custom | A metrics schema and a trace sink are chosen |
| Knowledge or architecture graph | Weak | Repo self-analysis output stays stable enough to persist |
| Model adapters (Codex, OpenCode, and others) | Not applicable yet | At least one non-Claude agent adopts the v0.1 spec |
| Memory promotion and pruning | Emerging | A memory quality score, covering usefulness, staleness, and contradiction, is defined |

## How to read this table

Each row names a module the design considered and chose not to build in
v0.1. The grade shows how strong the evidence is today, based on the
research in `WHITEPAPER.md`. Higher grades mean stronger current support.
Lower grades, or an emerging label, mean the idea is plausible but not yet
proven.

The gate states what must be true before work on that module starts. Most
gates ask for a measurement, an instrumentation point, or a track record
across real workflows. None of the gates are met yet. When one is met, add
the module to `SPEC.md` as a new normative artifact.

## Why the list stops here

v0.1 keeps its scope narrow on purpose. It builds six checkable artifacts
and one validator, and it leaves the rest for later. This avoids the
pattern `WHITEPAPER.md` calls out as harmful: start with a huge everything
and let the agent sort it out. Each module above waits for its own
evidence before it earns a place in the spec.
