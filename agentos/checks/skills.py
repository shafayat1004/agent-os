import json
import os
from agentos import yaml_min, jsonschema_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SCHEMA = os.path.join(_ROOT, "schemas", "skill.schema.json")


def check_skills(index_path, skills_dir, schema_path=None):
    schema_path = schema_path or _DEFAULT_SCHEMA
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)
    with open(index_path) as index_file:
        text = index_file.read()
    try:
        index = yaml_min.load(text) or {}
    except yaml_min.YamlError as error:
        return CheckResult("skills", grade_for("skills"),
                           [Finding("error", "cannot load %s: %s" % (index_path, error))])
    entries = index.get("skills", []) or []
    findings = []
    indexed_names = set()
    for entry_index, entry in enumerate(entries):
        for error in jsonschema_min.validate(entry, schema):
            findings.append(Finding("error", "skills[%d]: %s" % (entry_index, error)))
        if isinstance(entry, dict) and "name" in entry:
            indexed_names.add(entry["name"])
    if os.path.isdir(skills_dir):
        for skill_dir in sorted(os.listdir(skills_dir)):
            if os.path.isfile(os.path.join(skills_dir, skill_dir, "SKILL.md")):
                if skill_dir not in indexed_names:
                    findings.append(
                        Finding("warn", "skill '%s' has no index entry" % skill_dir))
    return CheckResult("skills", grade_for("skills"), findings)
