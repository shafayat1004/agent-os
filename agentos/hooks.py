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
import shlex
import subprocess
import sys
import time

from agentos import yaml_min
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


def run_pre_tool(stdin_text, policy_path, cwd, err=None):
    """Check a Claude Code PreToolUse tool call against the path policy.

    Reads the hook JSON from stdin. Exit 2 blocks the edit (never match),
    exit 1 warns without blocking (ask_first or undeclared path), exit 0
    allows. Missing or malformed input fails open.
    """
    err = err or sys.stderr
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        return 0  # input we cannot parse is not a violation: fail open
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if target is None:
        return 0
    return _classify_paths([target], policy_path, cwd, err)


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
