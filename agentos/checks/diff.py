from agentos import yaml_min
from agentos.pathmatch import matches
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding


def classify(policy, files):
    never_patterns = policy.get("never", []) or []
    ask_first_patterns = policy.get("ask_first", []) or []
    may_edit_patterns = policy.get("may_edit", []) or []
    findings = []
    for path in files:
        if any(matches(path, pattern) for pattern in never_patterns):
            findings.append(Finding("error", "%s: matches never rule" % path))
        elif any(matches(path, pattern) for pattern in ask_first_patterns):
            findings.append(Finding("warn", "%s: requires approval (ask_first)" % path))
        elif any(matches(path, pattern) for pattern in may_edit_patterns):
            continue
        else:
            findings.append(Finding("warn", "%s: outside declared scope" % path))
    return CheckResult("diff", grade_for("diff"), findings)


def check_diff(policy_path, files):
    with open(policy_path) as policy_file:
        policy = yaml_min.load(policy_file.read())
    return classify(policy, files)
