"""Harness adapters: the hook subcommands.

The checks themselves are harness-neutral. Each coding agent harness gets
a thin adapter that calls them: Claude Code hooks, an opencode plugin, or
a git pre-commit hook. The adapters share one exit-code contract for
editor-time checks: exit 2 means a hard violation the harness must block
on, exit 1 means a warning, and exit 0 means allow. A config error fails
open with exit 0: a guardrail that cannot load its inputs must say so and
get out of the way. It must never wedge the editor.

Two adapters are not gates at all. `hook-post-tool` is a trace recorder
and `hook-pre-compact` is an advisory nudge; both exit 0 always.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

from agentos import yaml_min
from agentos.checks import command as command_check
from agentos.checks import diff as diff_check
from agentos.checks import ledger as ledger_check
from agentos.checks import state as state_check


def _repo_relative(target, cwd):
    """The target path made repo-relative, or None when out of scope."""
    if not target:
        return None
    if not os.path.isabs(target):
        return target
    # realpath both sides: the hook's cwd and the tool's file_path may
    # resolve symlinks differently (macOS /var versus /private/var).
    relative = os.path.relpath(os.path.realpath(target), os.path.realpath(cwd))
    if relative == ".." or relative.startswith(".." + os.sep):
        return None  # outside the repo: outside this policy's jurisdiction
    return relative


def _classify_paths(targets, policy_path, cwd, err):
    """Classify repo-relative paths against the path policy.

    Returns the worst exit code across the targets: 2 on a never match,
    1 on ask_first or an undeclared path, 0 otherwise.
    """
    relatives = [relative for relative in
                 (_repo_relative(target, cwd) for target in targets)
                 if relative is not None]
    if not relatives:
        return 0
    try:
        result = diff_check.check_diff(policy_path, relatives)
    except (FileNotFoundError, OSError, yaml_min.YamlError) as error:
        print("agent-os: cannot enforce path policy (%s); allowing" % error,
              file=err)
        return 0
    for finding in result.findings:
        print("agent-os %s: %s" % (finding.level, finding.message), file=err)
    if any(finding.level == "error" for finding in result.findings):
        return 2
    if result.findings:
        return 1
    return 0


def run_check_path(paths, policy_path, cwd, err=None):
    """Check one or more paths against the path policy.

    Harness-neutral form of the pre-edit check: any adapter (opencode
    plugin, shell alias, CI step) can call it. Exit 2 blocks, exit 1
    warns, exit 0 allows.
    """
    return _classify_paths(paths, policy_path, cwd, err or sys.stderr)


def _classify_command(tool, command, policy_path, err):
    """Classify a command string against the command policy.

    Returns the exit code: 2 on a deny match, 1 on a warn match or an
    undeclared command (when an allow list is set), 0 otherwise. Fails
    open on a missing, malformed, or unparseable policy.
    """
    if not command:
        return 0
    try:
        result = command_check.check_command(policy_path, tool, command)
    except (FileNotFoundError, OSError, yaml_min.YamlError,
           re.error) as error:
        print("agent-os: cannot enforce command policy (%s); allowing"
              % error, file=err)
        return 0
    for finding in result.findings:
        print("agent-os %s: %s" % (finding.level, finding.message), file=err)
    if any(finding.level == "error" for finding in result.findings):
        return 2
    if result.findings:
        return 1
    return 0


def run_check_command(tool, command, policy_path, err=None):
    """Check a command string against the command policy.

    Harness-neutral form of the pre-shell check: the opencode plugin and
    the Claude Code PreToolUse wrapper both call this. Exit 2 blocks,
    exit 1 warns, exit 0 allows.
    """
    return _classify_command(tool, command, policy_path, err or sys.stderr)


def run_pre_tool(stdin_text, path_policy, command_policy, cwd, err=None):
    """Check a Claude Code PreToolUse tool call against both policies.

    Reads the hook JSON from stdin. The path policy gates the
    file_path or notebook_path argument of edit tools (exit 2 on a never
    match). The command policy gates the command string of shell tools,
    with the Bash command string as the first concrete instance (exit 2
    on a deny match). The two checks are complementary: one tool call
    can fire both, and the worst exit code wins. Missing or malformed
    input fails open.
    """
    err = err or sys.stderr
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        return 0  # input we cannot parse is not a violation: fail open
    tool_input = payload.get("tool_input") or {}
    tool_name = payload.get("tool_name") or payload.get("tool") or ""
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    command = tool_input.get("command")
    path_code = (_classify_paths([target], path_policy, cwd, err)
                 if target is not None else 0)
    command_code = (_classify_command(tool_name, command, command_policy, err)
                    if command is not None else 0)
    return max(path_code, command_code)


_VERDICT_GREEN = ("pass", "n/a")


def _read_state_fields(state_file):
    """The parsed STATE mapping, or None when it is missing or unreadable."""
    try:
        with open(state_file) as source:
            return yaml_min.load(source.read())
    except (OSError, yaml_min.YamlError):
        return None


def _verdict_gate(state_data, run_tests, err):
    """Grade a claimed done. Returns 2 when any proof gate fails."""
    blocks = []
    if not state_data.get("acceptance_criteria"):
        blocks.append("acceptance_criteria is empty: no done definition")
    verification = state_data.get("verification_status") or {}
    not_green = ["%s: %s" % (name, value)
                 for name, value in verification.items()
                 if value not in _VERDICT_GREEN]
    if not_green:
        blocks.append("verification_status not green: " + ", ".join(not_green))
    if run_tests:
        try:
            completed = subprocess.run(shlex.split(run_tests),
                                       capture_output=True, text=True,
                                       timeout=600)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            blocks.append("test command could not run (%s): %s"
                          % (run_tests, error))
        else:
            if completed.returncode != 0:
                output_lines = (completed.stdout + completed.stderr).strip()
                tail = output_lines.splitlines()[-10:]
                blocks.append("test command failed (%s):\n    %s"
                              % (run_tests, "\n    ".join(tail)))
    if not blocks:
        return 0
    print("agent-os: done claim refused, proof gates failed:", file=err)
    for block in blocks:
        print("  %s" % block, file=err)
    return 2


def run_stop(state_file, ledger_file, run_tests=None, err=None):
    """Refuse a done claim that lacks proof.

    Two layers. The always-on layer: STATE and the ledger must be
    schema-valid. The verdict layer: when STATE sets stop_readiness to
    "ready", the agent is claiming done, so acceptance_criteria must be
    non-empty, every verification_status field must be pass or n/a, and
    the configured test command, when given, must exit 0. Exit 2 refuses
    the claim, exit 0 allows it. Missing artifacts fail open: a repo
    without the files has no done-claim contract to enforce.

    This is the harness stop event. It fires on every turn end, so the
    verdict gate runs only when the agent declares readiness. An agent
    that pauses to ask a question is not claiming done. For an explicit
    completion claim that cannot be bypassed, use `agentos done` instead.
    """
    err = err or sys.stderr
    try:
        results = [state_check.check_state(state_file),
                   ledger_check.check_ledger(ledger_file)]
    except (FileNotFoundError, OSError) as error:
        print("agent-os: cannot check the done claim (%s); allowing" % error,
              file=err)
        return 0
    failures = [finding for result in results for finding in result.findings
                if finding.level == "error"]
    if failures:
        print("agent-os: STATE or ledger invalid; fix this before the done claim:",
              file=err)
        for finding in failures:
            print("  %s" % finding.message, file=err)
        return 2
    state_data = _read_state_fields(state_file)
    if not isinstance(state_data, dict):
        return 0
    readiness = state_data.get("stop_readiness")
    if not isinstance(readiness, str) or readiness.strip().lower() != "ready":
        return 0
    return _verdict_gate(state_data, run_tests, err)


def run_done(state_file, ledger_file, run_tests=None, verify_config=None,
             err=None):
    """Refuse a completion claim that lacks proof (issue #8).

    The explicit finalization gate. Unlike `run_stop` (the harness stop
    event, which fires every turn and gates only on a voluntary
    stop_readiness: ready), a `done` claim ALWAYS invokes the verdict
    gate. Missing or blocked readiness is rejected with an actionable
    reason, not silently allowed. This closes the bypass where an agent
    leaves stop_readiness unset, claims completion in prose, and stops
    without the verification gate running.

    Layer 1 (always on): STATE and the ledger must be schema-valid.
    Layer 2 (readiness): stop_readiness must be exactly "ready"; an
    absent, blocked, or malformed value is rejected with the fix the
    agent needs to take.
    Layer 3 (verifiers, when configured): when a verification config is
    present, run it first so the verdict comes from execution, not
    self-reported status. A nonzero exit from the verifiers (a failed
    command or a config error) refuses the claim; the gate never relies
    on the STATE writeback succeeding. The config timeout applies, same
    as on the `agentos verify` path.
    Layer 4 (verdict): non-empty acceptance_criteria, every
    verification_status field pass or n/a, and the test command, when
    given, exits 0.

    A missing verify config is a no-op (fresh repos stay self-reported),
    not an error. Missing STATE/ledger fail open, same as run_stop.
    """
    err = err or sys.stderr
    try:
        results = [state_check.check_state(state_file),
                   ledger_check.check_ledger(ledger_file)]
    except (FileNotFoundError, OSError) as error:
        print("agent-os: cannot check the done claim (%s); allowing" % error,
              file=err)
        return 0
    failures = [finding for result in results for finding in result.findings
                if finding.level == "error"]
    if failures:
        print("agent-os: STATE or ledger invalid; fix this before the done claim:",
              file=err)
        for finding in failures:
            print("  %s" % finding.message, file=err)
        return 2
    state_data = _read_state_fields(state_file)
    if not isinstance(state_data, dict):
        return 0
    readiness = state_data.get("stop_readiness")
    readiness_ready = (isinstance(readiness, str)
                       and readiness.strip().lower() == "ready")
    if not readiness_ready:
        reason = _readiness_reason(readiness)
        print("agent-os: done claim refused: %s" % reason, file=err)
        return 2
    if verify_config and os.path.exists(verify_config):
        from agentos.verify import run_verify
        # timeout None: the config timeout applies, same as the verify CLI.
        verify_exit = run_verify(verify_config, state_file, ledger_file,
                                 timeout=None, err=err)
        if verify_exit == 2:
            print("agent-os: done claim refused: the verification config "
                  "did not load (see the error above). Fix %s, or pass "
                  "--no-verify to trust self-reported status."
                  % verify_config, file=err)
            return 2
        if verify_exit != 0:
            print("agent-os: done claim refused: a configured verifier "
                  "failed (see the summary above). Fix the failure, or "
                  "pass --no-verify to trust self-reported status.",
                  file=err)
            return 2
        state_data = _read_state_fields(state_file)
        if not isinstance(state_data, dict):
            state_data = {}
    return _verdict_gate(state_data, run_tests, err)


def _readiness_reason(readiness):
    """Actionable reason text for a non-ready completion claim."""
    if readiness is None:
        return ("stop_readiness is not set. To claim done, set "
                "stop_readiness: ready in STATE.yaml. For a mid-task pause "
                "set stop_readiness: blocked.")
    if not isinstance(readiness, str) or readiness.strip() == "":
        return ("stop_readiness is empty. To claim done, set "
                "stop_readiness: ready in STATE.yaml.")
    value = readiness.strip().lower()
    if value == "blocked":
        return ("stop_readiness is blocked. A done claim requires "
                "stop_readiness: ready. Set it to ready when the task is "
                "complete, or keep blocked for a mid-task pause.")
    return ("stop_readiness is '%s'; expected ready or blocked. Set "
            "stop_readiness: ready to claim done." % readiness)


_TRACE_FIELD_LIMIT = 200


def run_post_tool(stdin_text, trace_file, tool=None, target=None, err=None):
    """Append one tool-call record to the trace log. Never blocks.

    This is instrumentation, not a gate: the trace feeds the
    context-accounting work on the roadmap. The tool and target come
    from flags when given, else from the tool call JSON on stdin. Any
    failure, malformed input or an unwritable file, still exits 0: a
    session must never be wedged by its own log.
    """
    err = err or sys.stderr
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        payload = {}
    tool_input = payload.get("tool_input") or {}
    tool = tool or payload.get("tool_name") or payload.get("tool") or ""
    target = (target or tool_input.get("file_path")
              or tool_input.get("notebook_path") or tool_input.get("command")
              or "")
    if not tool and not target:
        return 0
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "tool": str(tool)[:_TRACE_FIELD_LIMIT],
                  "target": str(target)[:_TRACE_FIELD_LIMIT]}
    try:
        os.makedirs(os.path.dirname(trace_file) or ".", exist_ok=True)
        with open(trace_file, "a") as trace:
            trace.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as error:
        print("agent-os: trace not written (%s)" % error, file=err)
    return 0


_REFRESH_FIELDS = ("goal", "next_action", "acceptance_criteria",
                   "confirmed_facts", "decisions", "failed_hypotheses",
                   "open_questions", "verification_status")


def run_pre_compact(state_file, out=None, err=None):
    """Advisory nudge before compaction. Never blocks.

    Compaction is where durable state earns its keep: the agent should
    refresh STATE.yaml first, so the summary does not carry the load.
    Prints the reminder plus any current STATE schema errors. Exit 0
    always: a reminder must not stop a compaction.
    """
    out = out or sys.stdout
    print("agent-os: compaction is about to run. Refresh STATE.yaml first so "
          "durable state survives: %s." % ", ".join(_REFRESH_FIELDS),
          file=out)
    try:
        result = state_check.check_state(state_file)
    except (FileNotFoundError, OSError):
        return 0  # no STATE file: nothing to grade, nothing to remind about
    errors = [finding.message for finding in result.findings
              if finding.level == "error"]
    if errors:
        print("agent-os: STATE.yaml is currently invalid:", file=out)
        for message in errors:
            print("  %s" % message, file=out)
    return 0
