import json
import os
from agentos import yaml_min, jsonschema_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SCHEMA = os.path.join(_ROOT, "schemas", "task-state.schema.json")


def check_state(path, schema_path=None):
    schema_path = schema_path or _DEFAULT_SCHEMA
    findings = []
    with open(schema_path) as fh:
        schema = json.load(fh)
    try:
        with open(path) as fh:
            data = yaml_min.load(fh.read())
    except (OSError, yaml_min.YamlError) as e:
        return CheckResult("state", grade_for("state"),
                           [Finding("error", "cannot load %s: %s" % (path, e))])
    for err in jsonschema_min.validate(data, schema):
        findings.append(Finding("error", err))
    return CheckResult("state", grade_for("state"), findings)
