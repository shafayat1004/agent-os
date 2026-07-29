import json
import os
from agentos import jsonschema_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SCHEMA = os.path.join(_ROOT, "schemas", "evidence.schema.json")


def check_ledger(path, schema_path=None):
    schema_path = schema_path or _DEFAULT_SCHEMA
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)
    findings = []
    with open(path) as ledger_file:
        lines = ledger_file.read().splitlines()
    for line_number, line in enumerate(lines, start=1):
        if line.strip() == "":
            continue
        try:
            record = json.loads(line)
        except ValueError:
            findings.append(Finding("error", "line %d: not valid JSON" % line_number))
            continue
        for error in jsonschema_min.validate(record, schema):
            findings.append(Finding("error", "line %d: %s" % (line_number, error)))
    return CheckResult("ledger", grade_for("ledger"), findings)
