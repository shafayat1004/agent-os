"""`agentos init`: one-shot greenfield wiring.

Presence of the artifacts is not enough: an agent follows the rules only when
the rule file is in the context the harness loads, and violations are blocked
only when the enforcement adapter is registered. This command does the wiring
that users otherwise skip, which produces a repo that looks governed but is
not.

The wiring is harness-neutral. `AGENTS.md` is the rule file every supported
agent reads (opencode, Codex, and Cursor read it natively). Pointer files
cover the harnesses that need one (Claude Code, Gemini CLI, Copilot).
Enforcement adapters cover Claude Code (hooks), opencode (plugin), and any
git flow (pre-commit).

It does these things, all non-destructive (an existing file is never
overwritten):
  1. copy the skeleton templates (via bootstrap)
  2. write pointer files (CLAUDE.md, GEMINI.md, copilot-instructions.md)
     at AGENTS.md
  3. install a git pre-commit hook that runs the validator
  4. write Claude Code hook wrappers plus .claude/settings.json when that
     file does not exist (when it does, print a snippet to merge)
  5. write the opencode plugin under .opencode/plugins/
"""
import json
import os
import shlex
import stat

from agentos.bootstrap import bootstrap

_POINTER = "# Project rules\n\nAll agent rules live in AGENTS.md. Read it before you act.\n"

# Rule-file pointers for the harnesses that do not read AGENTS.md natively.
_POINTERS = ("CLAUDE.md", "GEMINI.md",
             os.path.join(".github", "copilot-instructions.md"))

_OPENCODE_PLUGIN = """// agent-os opencode plugin (installed by `agentos init`).
// Enforcement adapter: blocks edits to never paths, refuses done claims
// while STATE.yaml or evidence/ledger.ndjson is invalid, and appends a
// trace line after each tool call.
// Resolution: a vendored bin/agentos in this repo wins. Otherwise the
// shared checkout recorded below is used. null means this repo is vendored.
import { existsSync, readFileSync } from "node:fs"

const SHARED = %s
const EDIT_TOOLS = new Set(["edit", "write", "multiedit", "patch"])

// Cheap fast-path for the idle handler: read the stop_readiness line
// straight out of STATE.yaml with a regex, so a non-done turn never
// spawns the validator. The validator itself remains authoritative and
// re-checks readiness with its own yaml parser; this is only a
// pre-filter. Fail-open to enforcement: a missing or unreadable STATE,
// or a missing field, falls through to the validator rather than
// skipping it.
const isClaimingDone = (stateFile) => {
  try {
    const match = readFileSync(stateFile, "utf8")
      .match(/^stop_readiness:\\s*(\\S+)/m)
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
// Not a done claim: skip the validator spawn entirely so idle
      // stays cheap while stop_readiness is blocked (the common case;
      // templates ship blocked and you flip to ready only at task end).
      if (!isClaimingDone(root + "/STATE.yaml")) return
      const { code, text } = await run(["done"])
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
      const message = "agent-os refuses the done claim:\\n" + fingerprint +
        "\\nSet stop_readiness: ready and fix STATE.yaml or the ledger, then stop again."
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
"""


def _opencode_plugin(agentos_bin):
    return _OPENCODE_PLUGIN % json.dumps(agentos_bin)


def _pre_commit(agentos_bin):
    return (
        "#!/bin/sh\n"
        "# agent-os pre-commit hook (installed by `agentos init`).\n"
        'AGENTOS="%s"\n'
        '"$AGENTOS" diff --staged || exit 1\n'
        '"$AGENTOS" deps || exit 1\n' % agentos_bin)


def _pre_tool(agentos_bin):
    return (
        "#!/bin/sh\n"
        "# agent-os PreToolUse wrapper (installed by `agentos init`).\n"
        "# Blocks (exit 2) when the edit target matches a never rule.\n"
        'cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0\n'
        'exec "%s" hook-pre-tool\n' % agentos_bin)


def _stop_check(agentos_bin):
    return (
        "#!/bin/sh\n"
        "# agent-os Stop wrapper (installed by `agentos init`).\n"
        "# Refuses the done claim (exit 2) when STATE or ledger is invalid.\n"
        "# Extra arguments pass through, for example --run-tests.\n"
        'cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0\n'
        'exec "%s" hook-stop "$@"\n' % agentos_bin)


def _post_tool(agentos_bin):
    return (
        "#!/bin/sh\n"
        "# agent-os PostToolUse wrapper (installed by `agentos init`).\n"
        "# Appends the tool call to the trace log. Never blocks.\n"
        'cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0\n'
        'exec "%s" hook-post-tool\n' % agentos_bin)


def _pre_compact(agentos_bin):
    return (
        "#!/bin/sh\n"
        "# agent-os PreCompact wrapper (installed by `agentos init`).\n"
        "# Reminds the agent to refresh STATE.yaml. Never blocks.\n"
        'cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0\n'
        'exec "%s" hook-pre-compact\n' % agentos_bin)


def _detect_test_command(dest):
    """Best-effort detection of the repo test command, or None."""
    if os.path.isdir(os.path.join(dest, "tests")):
        return "python3 -m unittest discover -s tests"
    package_json = os.path.join(dest, "package.json")
    if os.path.exists(package_json):
        try:
            with open(package_json) as source:
                scripts = (json.load(source) or {}).get("scripts") or {}
            if isinstance(scripts, dict) and scripts.get("test"):
                return "npm test"
        except (OSError, ValueError):
            pass
    makefile = os.path.join(dest, "Makefile")
    if os.path.exists(makefile):
        try:
            with open(makefile) as source:
                for line in source:
                    if line.startswith("test:") or line.startswith("test "):
                        return "make test"
        except OSError:
            pass
    return None


def _verification_config(dest, agentos_bin):
    """Build policies/verification.yaml, detecting common commands."""
    tests = _detect_test_command(dest)
    # The agentos all command is the repo-conformance check; quote the bin
    # path so a path with spaces still runs.
    policy = "%s all" % shlex.quote(agentos_bin)
    tests_line = ("  tests: " + json.dumps(tests)) if tests else "  tests: null"
    lines = [
        "# Verification commands (agentos verify executes these and writes",
        "# the result into STATE.yaml verification_status). Each is optional;",
        "# a null or omitted line marks that verifier unavailable (status n/a).",
        "commands:",
        "  format: null",
        "  compile: null",
        tests_line,
        "  policy: " + json.dumps(policy),
        "  security: null",
        "timeout: 600",
    ]
    return "\n".join(lines) + "\n"


def _write_if_absent(path, content, report, executable=False):
    if os.path.exists(path):
        report("skip existing", path)
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as output_file:
        output_file.write(content)
    if executable:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    report("created", path)
    return True


def _settings_snippet():
    # $CLAUDE_PROJECT_DIR keeps the settings file portable, so a repo can
    # commit it and every clone resolves the wrappers to its own checkout.
    return json.dumps({
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit|Write|MultiEdit",
                 "hooks": [{"type": "command",
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/agentos-pre-tool"}]}
            ],
            "PostToolUse": [
                {"matcher": "*",
                 "hooks": [{"type": "command",
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/agentos-post-tool"}]}
            ],
            "PreCompact": [
                {"matcher": "manual|auto",
                 "hooks": [{"type": "command",
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/agentos-pre-compact"}]}
            ],
            "Stop": [
                {"hooks": [{"type": "command",
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/agentos-stop-check"}]}
            ],
        }
    }, indent=2)


def run_init(dest, agentos_root, report=None):
    report = report or (lambda action, path: None)
    dest = os.path.abspath(dest)
    if os.path.exists(dest) and not os.path.isdir(dest):
        raise OSError("destination is not a directory: %s" % dest)
    agentos_bin = os.path.join(os.path.abspath(agentos_root), "bin", "agentos")

    bootstrap(os.path.join(agentos_root, "templates"), dest, report)
    for pointer_name in _POINTERS:
        _write_if_absent(os.path.join(dest, pointer_name), _POINTER, report)
    _write_if_absent(os.path.join(dest, ".claude", "hooks", "agentos-pre-tool"),
                     _pre_tool(agentos_bin), report, executable=True)
    _write_if_absent(os.path.join(dest, ".claude", "hooks", "agentos-stop-check"),
                     _stop_check(agentos_bin), report, executable=True)
    _write_if_absent(os.path.join(dest, ".claude", "hooks", "agentos-post-tool"),
                     _post_tool(agentos_bin), report, executable=True)
    _write_if_absent(os.path.join(dest, ".claude", "hooks", "agentos-pre-compact"),
                     _pre_compact(agentos_bin), report, executable=True)
    _write_if_absent(os.path.join(dest, ".opencode", "plugins", "agentos.js"),
                     _opencode_plugin(agentos_bin), report)
    _write_if_absent(os.path.join(dest, "policies", "verification.yaml"),
                     _verification_config(dest, agentos_bin), report)
    settings_written = _write_if_absent(
        os.path.join(dest, ".claude", "settings.json"),
        _settings_snippet() + "\n", report)

    git_hooks = os.path.join(dest, ".git", "hooks")
    if os.path.isdir(git_hooks):
        _write_if_absent(os.path.join(git_hooks, "pre-commit"),
                         _pre_commit(agentos_bin), report, executable=True)
    else:
        report("no .git, skipped pre-commit", git_hooks)

    return {"dest": dest, "agentos_bin": agentos_bin,
            "settings_snippet": _settings_snippet(),
            "settings_written": settings_written}
