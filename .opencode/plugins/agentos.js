// agent-os opencode plugin (installed by `agentos init`).
// Enforcement adapter: blocks edits to never paths, refuses done claims
// while STATE.yaml or evidence/ledger.ndjson is invalid, and appends a
// trace line after each tool call.
// Resolution: a vendored bin/agentos in this repo wins. Otherwise the
// shared checkout recorded below is used. null means this repo is vendored.
import { existsSync } from "node:fs"

const SHARED = null
const EDIT_TOOLS = new Set(["edit", "write", "multiedit", "patch"])
const TEST_COMMAND = "python3 -m unittest discover -s tests"

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
      if (!EDIT_TOOLS.has(input.tool)) return
      const target = output.args.filePath || output.args.notebookPath
      if (!target) return
      const { code, text } = await run(["check-path", target])
      if (code === 2) {
        throw new Error(text.trim() || "agent-os: path policy blocks this edit")
      }
      if (code === 1 && text.trim()) {
        await client.app.log({ body: { service: "agent-os", level: "warn",
                                       message: text.trim() } })
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
      const { code, text } = await run(["hook-stop", "--run-tests", TEST_COMMAND])
      if (code !== 2) return
      const fingerprint = text.trim()
      if (nudged.get(sessionID) === fingerprint) return  // no repeat loops
      nudged.set(sessionID, fingerprint)
      try {
        await client.session.prompt({
          path: { id: sessionID },
          body: { parts: [{ type: "text", text:
            "agent-os refuses the done claim:\n" + fingerprint +
            "\nFix STATE.yaml or evidence/ledger.ndjson, then stop again." }] },
        })
      } catch (error) {
        // Best effort: the git pre-commit hook still enforces.
      }
    },
  }
}
