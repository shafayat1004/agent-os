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
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)
    with open(path) as state_file:
        text = state_file.read()
    try:
        state_data = yaml_min.load(text)
    except yaml_min.YamlError as error:
        return CheckResult("state", grade_for("state"),
                           [Finding("error", "cannot load %s: %s" % (path, error))])
    for error in jsonschema_min.validate(state_data, schema):
        findings.append(Finding("error", error))
    return CheckResult("state", grade_for("state"), findings)
