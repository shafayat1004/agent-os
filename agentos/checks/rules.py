from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_REQUIRED = ["Commands", "Invariants", "Forbidden", "Approval gates", "Scope"]


def check_rules(path, soft=150, hard=250):
    with open(path) as fh:
        text = fh.read()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    findings = []
    n = len(lines)
    if n > hard:
        findings.append(Finding("error", "rule file has %d lines, over hard cap %d"
                                % (n, hard)))
    elif n > soft:
        findings.append(Finding("warn", "rule file has %d lines, over soft cap %d"
                                % (n, soft)))
    lowered = text.lower()
    for section in _REQUIRED:
        if section.lower() not in lowered:
            findings.append(Finding("warn", "missing section '%s'" % section))
    return CheckResult("rules", grade_for("rules"), findings)
