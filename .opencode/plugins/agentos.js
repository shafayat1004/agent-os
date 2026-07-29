// agent-os opencode plugin (installed by `agentos init`).
// Enforcement adapter: blocks edits to never paths and refuses done claims
// while STATE.yaml or evidence/ledger.ndjson is invalid.
// Resolution: a vendored bin/agentos in this repo wins. Otherwise the
// shared checkout recorded below is used. null means this repo is vendored.
import { existsSync } from "node:fs"

const SHARED = null
const EDIT_TOOLS = new Set(["edit", "write", "multiedit", "patch"])

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
  return {
    "tool.execute.before": async (input, output) => {
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
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const sessionID = event.properties && event.properties.sessionID
      if (!sessionID) return
      const { code, text } = await run(["hook-stop"])
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
