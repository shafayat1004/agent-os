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
    with open(policy_path) as policy_file:
        policy = yaml_min.load(policy_file.read())
    banned_packages = [entry["name"] for entry in policy.get("banned", []) or []]
    ignored_dirs = set(_DEFAULT_IGNORE) | set(policy.get("ignore", []) or [])
    findings = []
    for dirpath, subdirs, files in os.walk(root):
        subdirs[:] = sorted(name for name in subdirs if name not in ignored_dirs)
        for name in sorted(files):
            if not name.endswith(_MANIFESTS):
                continue
            manifest_path = os.path.join(dirpath, name)
            try:
                with open(manifest_path, encoding="utf-8", errors="replace") as manifest:
                    contents = manifest.read().lower()
            except OSError:
                continue
            for package in banned_packages:
                if package.lower() in contents:
                    findings.append(Finding(
                        "error", "%s: banned dependency '%s'" % (manifest_path, package)))
    return CheckResult("deps", grade_for("deps"), findings)
