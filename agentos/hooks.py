"""Harness adapters: `agentos check-path`, `hook-pre-tool`, `hook-stop`.

The checks themselves are harness-neutral. Each coding agent harness gets
a thin adapter that calls them: Claude Code hooks, an opencode plugin, or
a git pre-commit hook. The adapters share one exit-code contract for
editor-time checks: exit 2 means a hard violation the harness must block
on, exit 1 means a warning, and exit 0 means allow. A config error fails
open with exit 0: a guardrail that cannot load its inputs must say so and
get out of the way. It must never wedge the editor.
"""
import json
import os
import sys

from agentos.checks import diff as diff_check
from agentos.checks import ledger as ledger_check
from agentos.checks import state as state_check
from agentos.yaml_min import YamlError


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
