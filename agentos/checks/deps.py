import os
from agentos import yaml_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_MANIFESTS = (".fsproj", ".csproj", "package.json", "packages.config")

# Directories skipped by default: version control, vendored dependencies, and
# build output. They hold restored or generated manifests, not source the
# repo owns, so a scan of them is slow and reports false positives. The policy
# `ignore` list adds to this set.
_DEFAULT_IGNORE = (
    ".git", ".hg", ".svn",
    "node_modules", "bower_components", "vendor", "packages",
    ".venv", "venv", "__pycache__", ".tox",
    "bin", "obj", "dist", "build", "target",
)


def check_deps(policy_path, root):
    with open(policy_path) as fh:
        policy = yaml_min.load(fh.read())
    banned = [b["name"] for b in policy.get("banned", []) or []]
    ignore = set(_DEFAULT_IGNORE) | set(policy.get("ignore", []) or [])
    findings = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ignore)
        for name in sorted(files):
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
