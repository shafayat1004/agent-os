from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_REQUIRED = ["Commands", "Invariants", "Forbidden", "Approval gates", "Scope",
             "Conventions"]


def _headings(text):
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("## "):
            out.append(s[3:].strip())
    return out


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
    # Match required sections against '##' headings only, so a section name in
    # body text cannot count as present. A heading may extend the name (for
    # example "Conventions (pointer)"), so match on prefix.
    heads = [h.lower() for h in _headings(text)]
    positions = {}
    for section in _REQUIRED:
        sl = section.lower()
        pos = next((i for i, h in enumerate(heads)
                    if h == sl or h.startswith(sl + " ")), None)
        if pos is None:
            findings.append(Finding("warn", "missing section '%s'" % section))
        else:
            positions[section] = pos
    present = [s for s in _REQUIRED if s in positions]
    if present != sorted(present, key=positions.get):
        findings.append(Finding("warn", "sections out of required order: expected %s"
                                % ", ".join(_REQUIRED)))
    return CheckResult("rules", grade_for("rules"), findings)
