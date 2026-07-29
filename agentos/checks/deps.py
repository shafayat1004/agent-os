import os
from agentos import yaml_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_MANIFESTS = (".fsproj", ".csproj", "package.json", "packages.config")


def check_deps(policy_path, root):
    with open(policy_path) as fh:
        policy = yaml_min.load(fh.read())
    banned = [b["name"] for b in policy.get("banned", []) or []]
    findings = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(_MANIFESTS) and name not in _MANIFESTS:
                continue
            full = os.path.join(dirpath, name)
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read().lower()
            except OSError:
                continue
            for pkg in banned:
                if pkg.lower() in text:
                    findings.append(
                        Finding("error", "%s: banned dependency '%s'" % (full, pkg)))
    return CheckResult("deps", grade_for("deps"), findings)
