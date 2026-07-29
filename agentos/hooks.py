"""Claude Code hook entry points: `agentos hook-pre-tool`, `agentos hook-stop`.

These subcommands carry the Claude Code exit-code contract, which differs
from the validator contract. A PreToolUse or Stop hook blocks only on exit
code 2. Any other nonzero code is a non-blocking warning shown to the
user. So the mapping here is: a policy violation exits 2, a warning exits
1, and a config error exits 0. A guardrail that cannot load its inputs
must say so and fail open. It must never wedge the editor.
"""
import json
import os
import sys

from agentos.checks import diff as diff_check
from agentos.checks import ledger as ledger_check
from agentos.checks import state as state_check
from agentos.yaml_min import YamlError


def _edit_target(payload, cwd):
    """The repo-relative path the tool call wants to write, or None."""
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
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


def run_pre_tool(stdin_text, policy_path, cwd, err=None):
    """Check a PreToolUse tool call against the path policy.

    Reads the hook JSON from stdin. Exit 2 blocks the edit (never match),
    exit 1 warns without blocking (ask_first or undeclared path), exit 0
    allows. Missing or malformed input fails open.
    """
    err = err or sys.stderr
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        return 0  # input we cannot parse is not a violation: fail open
    target = _edit_target(payload, cwd)
    if target is None:
        return 0
    try:
        result = diff_check.check_diff(policy_path, [target])
    except (FileNotFoundError, OSError, YamlError) as error:
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


def run_stop(state_file, ledger_file, err=None):
    """Refuse a done claim when STATE or the ledger is invalid.

    Exit 2 blocks the stop, exit 0 allows it. Missing artifacts fail open:
    a repo without the files has no done-claim contract to enforce.
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
    if not failures:
        return 0
    print("agent-os: STATE or ledger invalid; fix this before the done claim:",
          file=err)
    for finding in failures:
        print("  %s" % finding.message, file=err)
    return 2
