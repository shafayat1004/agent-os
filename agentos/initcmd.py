"""`agentos init`: one-shot greenfield wiring.

Presence of the artifacts is not enough: an agent follows the rules only when
the rule file is in the context the harness loads, and violations are blocked
only when the hooks are registered. This command does the wiring that users
otherwise skip, which produces a repo that looks governed but is not.

It does four things, all non-destructive (an existing file is never
overwritten):
  1. copy the skeleton templates (via bootstrap)
  2. write a CLAUDE.md pointer at AGENTS.md
  3. install a git pre-commit hook that runs the validator
  4. write Claude Code hook wrappers and print the settings snippet to paste
"""
import json
import os
import stat

from agentos.bootstrap import bootstrap

_POINTER = "# Project rules\n\nAll agent rules live in AGENTS.md. Read it before you act.\n"


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
        'cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0\n'
        'exec "%s" diff --staged\n' % agentos_bin)


def _stop_check(agentos_bin):
    return (
        "#!/bin/sh\n"
        "# agent-os Stop wrapper (installed by `agentos init`).\n"
        'cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0\n'
        '"%s" state || exit 1\n'
        'exec "%s" ledger\n' % (agentos_bin, agentos_bin))


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


def _settings_snippet(dest):
    pre_tool = os.path.join(dest, ".claude", "hooks", "agentos-pre-tool")
    stop = os.path.join(dest, ".claude", "hooks", "agentos-stop-check")
    return json.dumps({
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit|Write|MultiEdit",
                 "hooks": [{"type": "command", "command": pre_tool}]}
            ],
            "Stop": [
                {"hooks": [{"type": "command", "command": stop}]}
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
    _write_if_absent(os.path.join(dest, "CLAUDE.md"), _POINTER, report)
    _write_if_absent(os.path.join(dest, ".claude", "hooks", "agentos-pre-tool"),
                     _pre_tool(agentos_bin), report, executable=True)
    _write_if_absent(os.path.join(dest, ".claude", "hooks", "agentos-stop-check"),
                     _stop_check(agentos_bin), report, executable=True)

    git_hooks = os.path.join(dest, ".git", "hooks")
    if os.path.isdir(git_hooks):
        _write_if_absent(os.path.join(git_hooks, "pre-commit"),
                         _pre_commit(agentos_bin), report, executable=True)
    else:
        report("no .git, skipped pre-commit", git_hooks)

    return {"dest": dest, "agentos_bin": agentos_bin,
            "settings_snippet": _settings_snippet(dest)}
