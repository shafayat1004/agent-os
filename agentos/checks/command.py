"""Command policy: gate shell tool invocations by command string.

The complement to the path policy (issue #34). The path policy gates the
file_path argument of edit tools. The command policy gates the command
string of shell tools, with the Bash command string as the first
concrete instance. One tool call can fire both checks: the path check on
the target and the command check on the command string. The two are
distinct from issue #10, which detects file writes done through shell
commands and applies path policy to the mutated path after the fact.

The contract mirrors the path policy. Each entry under a tool key can
be a string (the regex pattern) or a mapping with a pattern and an
optional reason. The classifier checks deny first (block, exit 2), then
warn (advisory, exit 1). When an allow list is set and non-empty, a
command that matches no deny, no warn, and no allow pattern is an
outside-scope warning. When the allow list is empty or absent, an
unmatched command is allowed. Tool names are lowercased so one policy
key serves both harnesses (Claude Code sends "Bash", opencode sends
"bash").

A malformed entry (a typo'd key, a non-string non-mapping value) is
never silently accepted: the classifier emits a warning finding so the
operator sees the rule that does not load. A deny rule with a misspelt
key is the worst silent failure mode for a security policy: the operator
believes a command is blocked when it is not. The warning makes it
visible without blocking every command until the typo is fixed.
"""
import re

from agentos import yaml_min
from agentos.result import CheckResult, Finding


def _entry(item):
    """Return (pattern, reason, valid) from a deny/warn/allow list entry.

    An entry is a string (the pattern, no reason) or a mapping with a
    pattern key and an optional reason key. A non-string, non-mapping
    entry, or a mapping without a pattern key, yields (None, None, False)
    so the caller can warn the operator instead of silently skipping.
    """
    if isinstance(item, str):
        return item, None, True
    if isinstance(item, dict):
        pattern = item.get("pattern")
        return pattern, item.get("reason"), pattern is not None
    return None, None, False


def _matches(entries, command):
    """Yield (pattern, reason) for every entry whose regex matches."""
    for item in entries:
        pattern, reason, _valid = _entry(item)
        if pattern is not None and re.search(pattern, command):
            yield pattern, reason


def _invalid_entries(entries):
    """Yield a warning message for each structurally invalid entry."""
    for item in entries:
        _pattern, _reason, valid = _entry(item)
        if not valid:
            yield "unrecognized entry (expected a string or a mapping " \
                  "with a pattern key): %r" % (item,)


def _section(value):
    """Normalize a deny/warn/allow section to a list.

    A missing section (None) is the normal absent case: empty, silent. A
    list passes through. Anything else (a string, a number, a mapping)
    is a malformed section: iterating a string character by character
    would degenerate-match against single characters, so it is rejected
    with a warning and treated as empty.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def classify(policy, tool, command):
    """Classify a command string against the command policy for a tool.

    Returns a CheckResult. A deny match is an error (block). A warn
    match is a warning. When an allow list is set and non-empty, a
    command that matches no list at all is an outside-scope warning.
    Tool names are lowercased so the policy keys are harness-neutral.
    A non-mapping policy (None from an empty file, a list, a scalar)
    is treated as an empty policy so the check fails open.
    """
    tool = (tool or "").lower()
    command = command or ""
    policy = policy if isinstance(policy, dict) else {}
    tools = policy.get("tools") or {}
    tool_policy = tools.get(tool) or {}
    if not isinstance(tool_policy, dict):
        tool_policy = {}
    raw_sections = {"deny": tool_policy.get("deny"),
                    "warn": tool_policy.get("warn"),
                    "allow": tool_policy.get("allow")}
    deny = _section(raw_sections["deny"])
    warn = _section(raw_sections["warn"])
    allow = _section(raw_sections["allow"])
    findings = []
    # Warn the operator about a section whose value is not a list (a
    # string, a number, a mapping) so a typo like `deny: 'rm -rf'` does
    # not silently degenerate-match against single characters.
    for section_name, raw_value in raw_sections.items():
        if raw_value is not None and not isinstance(raw_value, list):
            findings.append(Finding("warn",
                                    "%s: expected a list, got %s; ignored"
                                    % (section_name, type(raw_value).__name__)))
    # Warn the operator about structurally invalid entries in any list
    # so a typo'd deny key does not silently fail to guard.
    for section, entries in (("deny", deny), ("warn", warn),
                             ("allow", allow)):
        for message in _invalid_entries(entries):
            findings.append(Finding("warn",
                                    "%s: %s" % (section, message)))
    for _pattern, reason in _matches(deny, command):
        suffix = " (%s)" % reason if reason else ""
        findings.append(Finding("error",
                                "%s: matches deny rule%s" % (command, suffix)))
        return CheckResult("command", "n/a", findings)
    for _pattern, reason in _matches(warn, command):
        suffix = " (%s)" % reason if reason else ""
        findings.append(Finding("warn",
                                "%s: matches warn rule%s" % (command, suffix)))
    if allow and not findings:
        if not any(_pattern is not None
                   for _pattern, _reason in _matches(allow, command)):
            findings.append(Finding("warn",
                                    "%s: outside declared scope" % command))
    return CheckResult("command", "n/a", findings)


def check_command(policy_path, tool, command):
    """Load the policy file and classify the command. Raises on error."""
    with open(policy_path) as policy_file:
        policy = yaml_min.load(policy_file.read())
    return classify(policy, tool, command)
