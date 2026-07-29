from agentos import yaml_min
from agentos.pathmatch import matches
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding


def classify(policy, files):
    never = policy.get("never", []) or []
    ask = policy.get("ask_first", []) or []
    edit = policy.get("may_edit", []) or []
    findings = []
    for path in files:
        if any(matches(path, p) for p in never):
            findings.append(Finding("error", "%s: matches never rule" % path))
        elif any(matches(path, p) for p in ask):
            findings.append(Finding("warn", "%s: requires approval (ask_first)" % path))
        elif any(matches(path, p) for p in edit):
            continue
        else:
            findings.append(Finding("warn", "%s: outside declared scope" % path))
    return CheckResult("diff", grade_for("diff"), findings)


def check_diff(policy_path, files):
    with open(policy_path) as fh:
        policy = yaml_min.load(fh.read())
    return classify(policy, files)
