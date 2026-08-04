"""Custom checks from policies/custom-checks.yaml.

Each check runs a shell command and grades the result. A check with
on_fail: error blocks agentos done (same as a built-in check). A check
with on_fail: warn reports but does not block.

The file is optional; absent means no custom checks.
"""
import os
import subprocess

from agentos.result import CheckResult, Finding
from agentos.yaml_min import load, YamlError

_GRADE = "A"


def check_custom(policy_path, root="."):
    """Run custom checks and return a CheckResult."""
    if not os.path.exists(policy_path):
        return CheckResult(name="custom", grade=_GRADE, findings=[])

    try:
        with open(policy_path) as handle:
            config = load(handle.read())
    except (YamlError, OSError) as error:
        return CheckResult(name="custom", grade=_GRADE,
                           findings=[Finding("error",
                                "cannot parse %s: %s" % (policy_path, error))])

    checks = config.get("checks", []) if isinstance(config, dict) else []
    if not checks:
        return CheckResult(name="custom", grade=_GRADE, findings=[])

    findings = []
    for check in checks:
        name = check.get("name", "unnamed")
        command = check.get("command")
        if not command:
            findings.append(Finding("error", "%s: no command" % name))
            continue
        on_fail = check.get("on_fail", "error")
        try:
            result = subprocess.run(
                command, shell=True, cwd=root,
                capture_output=True, text=True, timeout=300)
            passed = (result.returncode == 0)
        except subprocess.TimeoutExpired:
            findings.append(Finding("error", "%s: timed out" % name))
            continue
        except OSError as error:
            findings.append(Finding("error", "%s: %s" % (name, error)))
            continue
        if passed:
            findings.append(Finding("info", "%s: pass" % name))
        else:
            level = on_fail if on_fail in ("error", "warn") else "error"
            detail = result.stderr.strip() or result.stdout.strip()
            msg = "%s: fail (exit %d)" % (name, result.returncode)
            if detail:
                msg += " - %s" % detail[:200]
            findings.append(Finding(level, msg))

    return CheckResult(name="custom", grade=_GRADE, findings=findings)
