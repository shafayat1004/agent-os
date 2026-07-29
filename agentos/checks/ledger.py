import json
import os
from agentos import jsonschema_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SCHEMA = os.path.join(_ROOT, "schemas", "evidence.schema.json")


def check_ledger(path, schema_path=None):
    schema_path = schema_path or _DEFAULT_SCHEMA
    with open(schema_path) as fh:
        schema = json.load(fh)
    findings = []
    with open(path) as fh:
        lines = fh.read().splitlines()
    for i, line in enumerate(lines, start=1):
        if line.strip() == "":
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            findings.append(Finding("error", "line %d: not valid JSON" % i))
            continue
        for err in jsonschema_min.validate(obj, schema):
            findings.append(Finding("error", "line %d: %s" % (i, err)))
    return CheckResult("ledger", grade_for("ledger"), findings)
