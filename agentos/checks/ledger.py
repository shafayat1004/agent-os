"""Evidence-ledger check: schema shape plus a v1 semantic layer.

v0 entries (no `version` field) are checked against the schema only. This
is the legacy bar and it never weakens. v1 entries (`version: 1`) opt into
a stricter semantic bar: non-empty claim and evidence_ref, an ISO 8601 UTC
timestamp, a non-empty verifier when confirmed, a non-empty hash for a
confirmed test or tool entry, a criterion that names a real id in STATE,
and, for file entries, a resolvable path and a matching content hash.

Drift on a live proof (a confirmed entry that proves an active criterion)
blocks the done claim: the done gate refuses on any error-level finding.
Drift on a free-standing fact is a warning. A superseded entry, or an entry
whose criterion is obsolete, is history and the validator stays silent on
its drift. The cross-reference summary reports every active STATE criterion
that has no confirmed live proof.
"""
import hashlib
import json
import os
import re

from agentos import jsonschema_min, yaml_min
from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SCHEMA = os.path.join(_ROOT, "schemas", "evidence.schema.json")

_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _load_state(state_file):
    """Return (criteria_by_id, task_started) from STATE, or (None, None).

    None for the whole result means no cross-reference is possible: the
    file is missing, unreadable, or not a mapping. A present but empty
    criteria list yields an empty dict, which still triggers the coverage
    summary (with no criteria to cover).
    """
    if not state_file or not os.path.exists(state_file):
        return None, None
    try:
        with open(state_file) as source:
            data = yaml_min.load(source.read())
    except (OSError, yaml_min.YamlError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    criteria = {}
    for item in data.get("criteria") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            criteria[item["id"]] = item.get("status", "active")
    task_started = data.get("task_started")
    if not isinstance(task_started, str):
        task_started = None
    return criteria, task_started


def _superseded_set(lines):
    """Return (superseded line numbers, superseded ids) from a first pass.

    A `supersedes` value that is all digits names a line number (the form a
    v0 migration uses, since v0 entries have no id). Any other value names
    a v1 entry id.
    """
    superseded_lines = set()
    superseded_ids = set()
    for line in lines:
        if line.strip() == "":
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        reference = record.get("supersedes") if isinstance(record, dict) else None
        if not isinstance(reference, str) or reference == "":
            continue
        if reference.isdigit():
            superseded_lines.add(int(reference))
        else:
            superseded_ids.add(reference)
    return superseded_lines, superseded_ids


def _file_path_from_ref(evidence_ref, root):
    """Return the file path inside evidence_ref, or None.

    evidence_ref for a file entry is `path` or `path:line`. A trailing
    `:digits` is stripped as a line suffix. The path is resolved relative
    to root when it is not absolute.
    """
    if not isinstance(evidence_ref, str) or evidence_ref == "":
        return None
    path = evidence_ref
    if ":" in path:
        head, tail = path.rsplit(":", 1)
        if tail.isdigit() and head:
            path = head
    return path if os.path.isabs(path) else os.path.join(root, path)


def _file_hash(path):
    """Return the sha256 hex of a file, or None when unreadable."""
    try:
        sha = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except OSError:
        return None


def check_ledger(path, schema_path=None, state_file=None, root=None):
    schema_path = schema_path or _DEFAULT_SCHEMA
    root = root or "."
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)
    findings = []
    with open(path) as ledger_file:
        lines = ledger_file.read().splitlines()
    criteria, task_started = _load_state(state_file)
    superseded_lines, superseded_ids = _superseded_set(lines)

    live_proofs = {}
    for line_number, line in enumerate(lines, start=1):
        if line.strip() == "":
            continue
        try:
            record = json.loads(line)
        except ValueError:
            findings.append(Finding("error", "line %d: not valid JSON" % line_number))
            continue
        schema_errors = list(jsonschema_min.validate(record, schema))
        for error in schema_errors:
            findings.append(Finding("error", "line %d: %s" % (line_number, error)))
        # The semantic layer applies to v1 entries only. v0 entries (no
        # version field) keep the legacy schema-only bar.
        if record.get("version") != 1:
            continue
        # A malformed v1 line already produced schema errors; skip the
        # semantic layer to avoid redundant messages.
        if schema_errors:
            continue
        is_superseded = (line_number in superseded_lines
                         or (isinstance(record.get("id"), str)
                             and record["id"] in superseded_ids))
        if is_superseded:
            continue  # history: schema-only, drift stays silent
        criterion_id = record.get("criterion")
        criterion_status = None
        if criterion_id is not None and criteria is not None:
            criterion_status = criteria.get(criterion_id)
        is_live_proof = (criterion_status == "active"
                         and isinstance(criterion_id, str))
        is_obsolete = (criterion_status == "obsolete")

        # Structural v1 checks apply to every non-superseded v1 entry,
        # including entries whose criterion is obsolete. These are
        # well-formedness checks, not drift.
        if not str(record.get("claim", "")).strip():
            findings.append(Finding("error",
                "line %d: v1 entry has an empty claim" % line_number))
        if not str(record.get("evidence_ref", "")).strip():
            findings.append(Finding("error",
                "line %d: v1 entry has an empty evidence_ref" % line_number))
        timestamp = record.get("ts", "")
        if not isinstance(timestamp, str) or not _TS_PATTERN.match(timestamp):
            findings.append(Finding("error",
                "line %d: v1 entry ts is not ISO 8601 UTC" % line_number))
        if (record.get("status") == "confirmed"
                and not str(record.get("verifier", "")).strip()):
            findings.append(Finding("error",
                "line %d: v1 confirmed entry has an empty verifier" % line_number))
        if (record.get("status") == "confirmed"
                and record.get("source_type") in ("test", "tool")
                and not str(record.get("hash", "")).strip()):
            findings.append(Finding("error",
                "line %d: v1 confirmed %s entry has an empty hash"
                % (line_number, record.get("source_type"))))
        if criterion_id is not None and criteria is not None:
            if criterion_id not in criteria:
                findings.append(Finding("error",
                    "line %d: v1 entry criterion '%s' is not in STATE criteria"
                    % (line_number, criterion_id)))
        if is_live_proof and record.get("status") == "confirmed":
            live_proofs[criterion_id] = True

        # Drift checks: skip entries whose criterion is retired. A retired
        # requirement has no live proof obligation, so its evidence is
        # historical and drift is not actionable.
        if is_obsolete:
            continue
        drift_level = "error" if is_live_proof else "warning"
        if record.get("source_type") == "file":
            candidate = _file_path_from_ref(record.get("evidence_ref", ""), root)
            if candidate is None or not os.path.exists(candidate):
                findings.append(Finding(drift_level,
                    "line %d: v1 file evidence_ref '%s' does not resolve"
                    % (line_number, record.get("evidence_ref", ""))))
            else:
                stored_hash = record.get("hash")
                if isinstance(stored_hash, str) and stored_hash.strip():
                    actual_hash = _file_hash(candidate)
                    if actual_hash is not None and actual_hash != stored_hash:
                        findings.append(Finding(drift_level,
                            "line %d: v1 file evidence_ref '%s' hash mismatch"
                            " (stored %s, actual %s)"
                            % (line_number, record.get("evidence_ref", ""),
                               stored_hash[:12], actual_hash[:12])))
        if (task_started and isinstance(timestamp, str)
                and _TS_PATTERN.match(timestamp) and timestamp < task_started):
            findings.append(Finding(drift_level,
                "line %d: v1 entry ts %s is before task_started %s (stale)"
                % (line_number, timestamp, task_started)))

    # Cross-reference summary: every active STATE criterion needs a
    # confirmed live proof. An uncovered criterion blocks the done claim
    # (it surfaces as an error finding the done gate refuses on).
    if criteria is not None:
        for criterion_id, status in criteria.items():
            if status != "active":
                continue
            if not live_proofs.get(criterion_id):
                findings.append(Finding("error",
                    "criterion '%s': no confirmed live proof in the ledger"
                    % criterion_id))
    return CheckResult("ledger", grade_for("ledger"), findings)
