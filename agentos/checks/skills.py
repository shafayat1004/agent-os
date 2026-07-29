import json
import os
from agentos import yaml_min, jsonschema_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SCHEMA = os.path.join(_ROOT, "schemas", "skill.schema.json")


def check_skills(index_path, skills_dir, schema_path=None):
    schema_path = schema_path or _DEFAULT_SCHEMA
    with open(schema_path) as fh:
        schema = json.load(fh)
    with open(index_path) as fh:
        index = yaml_min.load(fh.read()) or {}
    entries = index.get("skills", []) or []
    findings = []
    names = set()
    for i, entry in enumerate(entries):
        for err in jsonschema_min.validate(entry, schema):
            findings.append(Finding("error", "skills[%d]: %s" % (i, err)))
        if isinstance(entry, dict) and "name" in entry:
            names.add(entry["name"])
    if os.path.isdir(skills_dir):
        for sub in sorted(os.listdir(skills_dir)):
            if os.path.isfile(os.path.join(skills_dir, sub, "SKILL.md")):
                if sub not in names:
                    findings.append(
                        Finding("warn", "skill '%s' has no index entry" % sub))
    return CheckResult("skills", grade_for("skills"), findings)
