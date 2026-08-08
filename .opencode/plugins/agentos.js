// agent-os opencode plugin (installed by `agentos init`).
// Enforcement adapter: blocks edits to never paths, blocks shell
// commands that match a deny rule, refuses done claims while STATE.yaml
// or evidence/ledger.ndjson is invalid, and appends a trace line after
// each tool call.
// Resolution: a vendored bin/agentos in this repo wins. Otherwise the
// shared checkout recorded below is used. null means this repo is vendored.
import { existsSync, readFileSync } from "node:fs"

const SHARED = null
const EDIT_TOOLS = new Set(["edit", "write", "multiedit", "patch"])
const TEST_COMMAND = "python3 -m unittest discover -s tests"

// Cheap fast-path for the idle handler: read the stop_readiness line
// straight out of STATE.yaml with a regex, so a non-done turn never
// spawns the validator (and never runs the test suite). The validator
// itself remains authoritative and re-checks readiness with its own
// yaml parser; this is only a pre-filter. Fail-open to enforcement:
// a missing or unreadable STATE, or a missing field, falls through to
// the validator rather than skipping it.
const isClaimingDone = (stateFile) => {
  try {
    const match = readFileSync(stateFile, "utf8")
      .match(/^stop_readiness:\s*(\S+)/m)
    if (!match) return true  // no field: let the validator decide
    return match[1].trim().toLowerCase() === "ready"
  } catch (error) {
    return true  // unreadable/missing: let the validator fail open
  }
}

export const AgentOS = async ({ $, client, directory, worktree }) => {
  const root = worktree || directory
  const vendored = root + "/bin/agentos"
  const agentos = existsSync(vendored) ? vendored : SHARED
  if (!agentos) return {}  // no validator reachable: stay out of the way
  const run = async (args) => {
    const result = await $`${agentos} ${args}`.nothrow().quiet().cwd(root)
    return { code: result.exitCode,
             text: result.stderr.toString() + result.stdout.toString() }
  }
  const nudged = new Map()  // sessionID -> failure fingerprint already sent
  const pending = new Map()  // callID -> { tool, args } awaiting completion
  return {
    "tool.execute.before": async (input, output) => {
      if (input.callID) {
        if (pending.size > 200) pending.clear()
        pending.set(input.callID, { tool: input.tool, args: output.args || {} })
      }
      // Path policy: gate the file_path argument of edit tools.
      if (EDIT_TOOLS.has(input.tool)) {
        const target = output.args.filePath || output.args.notebookPath
        if (target) {
          const { code, text } = await run(["check-path", target])
          if (code === 2) {
            throw new Error(text.trim() || "agent-os: path policy blocks this edit")
          }
          if (code === 1 && text.trim()) {
            await client.app.log({ body: { service: "agent-os", level: "warn",
                                           message: text.trim() } })
          }
        }
      }
      // Command policy: gate the command string of shell tools (#34).
      // The Bash command string is the first concrete instance. This is
      // the complement to the path check: one tool call can fire both.
      if (input.tool === "bash") {
        const command = output.args.command
        if (command) {
          const { code, text } = await run(["check-command", "--tool", "bash",
                                            "--command", command])
          if (code === 2) {
            throw new Error(text.trim() || "agent-os: command policy blocks this command")
          }
          if (code === 1 && text.trim()) {
            await client.app.log({ body: { service: "agent-os", level: "warn",
                                           message: text.trim() } })
          }
        }
      }
    },
    "tool.execute.after": async (input) => {
      const seenCall = pending.get(input.callID) || { tool: input.tool, args: {} }
      if (input.callID) pending.delete(input.callID)
      const target = seenCall.args.filePath || seenCall.args.notebookPath
        || seenCall.args.command || ""
      try {
        await run(["hook-post-tool", "--tool", String(seenCall.tool || ""),
                   "--target", String(target)])
      } catch (error) {
        // Trace only: a session is never blocked by its own log.
      }
    },
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const sessionID = event.properties && event.properties.sessionID
      if (!sessionID) return
      // Not a done claim: skip the validator spawn entirely so idle
      // stays cheap while stop_readiness is blocked (the common case;
      // templates ship blocked and you flip to ready only at task end).
      if (!isClaimingDone(root + "/STATE.yaml")) return
      const { code, text } = await run(["done", "--run-tests", TEST_COMMAND])
      if (code !== 2) return
      const fingerprint = text.trim()
      if (nudged.get(sessionID) === fingerprint) return  // one toast per failure
      nudged.set(sessionID, fingerprint)
      // Advisory only: never start a new AI turn from inside the idle event.
      // A turn-starting prompt API awaits a full turn, which deadlocks the
      // TUI when called from the handler of the event that marks the prior
      // turn done. The git pre-commit hook remains the hard gate. `done`
      // is the explicit completion gate: it rejects a missing or blocked
      // stop_readiness, so a prose claim cannot bypass the verdict.
      const message = "agent-os refuses the done claim:\n" + fingerprint +
        "\nSet stop_readiness: ready and fix STATE.yaml or the ledger, then stop again."
      try {
        await client.app.log({ body: { service: "agent-os", level: "error",
                                       message } })
      } catch (error) { /* best effort: the log may be unavailable */ }
      try {
        await client.tui.showToast({ body: { message, variant: "error" } })
      } catch (error) { /* TUI may be headless; the log already recorded it */ }
    },
  }
}
