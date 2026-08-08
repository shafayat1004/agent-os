"""`agentos verify`: run the configured project verifiers and derive status.

The verdict values in STATE.yaml (format, compile, tests, policy, security)
are normally self-reported. This module runs real commands and writes the
derived status back, so the verdict comes from execution, not a trusted
assertion. The commands and the timeout live in a repository-owned config,
`policies/verification.yaml`, validated here (not via the task-state schema,
so no schemas/ edit is needed). Each run records one ledger line with the
command, the exit code (or timeout note), an output hash, and a timestamp.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time

from agentos import yaml_min

# The five verification_status fields the task-state schema requires. The
# order is fixed so the summary and the writeback stay deterministic.
_VERIFIERS = ("format", "compile", "tests", "policy", "security")
_VERDICT_PASS = "pass"
_VERDICT_FAIL = "fail"
_VERDICT_NA = "n/a"


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_config(config_path, err):
    """Load the verification config, or return (None, exit_code).

    A missing config is not an error: a fresh repo has no verifiers wired
    yet, so verify is a no-op that reports skipped. An unreadable or
    malformed config is a hard error (exit 2): the repo claims verification
    it cannot run.
    """
    if not os.path.exists(config_path):
        print("agent-os: no verification config at %s; skipped." % config_path,
              file=err)
        return None, 0
    try:
        with open(config_path) as source:
            text = source.read()
    except OSError as error:
        print("agent-os: cannot read verification config: %s" % error,
              file=err)
        return None, 2
    try:
        config = yaml_min.load(text)
    except yaml_min.YamlError as error:
        print("agent-os: cannot load verification config: %s" % error,
              file=err)
        return None, 2
    if not isinstance(config, dict):
        print("agent-os: verification config is not a mapping", file=err)
        return None, 2
    return config, None


def _check_assert(output, assert_block):
    """Check content assertions against verifier output (issue #35).

    Returns (passed, detail) where detail names the failed pattern so
    the ledger records why the verifier failed, not just that it failed.
    A missing contains pattern yields 'assert missing: "pattern"'; a
    matched excludes pattern yields 'assert forbidden: "pattern"'. An
    assert block with no contains or no excludes is a no-op (passed).
    """
    contains = assert_block.get("contains") or []
    excludes = assert_block.get("excludes") or []
    for pattern in contains:
        if pattern not in output:
            return (False, 'assert missing: "%s"' % pattern)
    for pattern in excludes:
        if pattern in output:
            return (False, 'assert forbidden: "%s"' % pattern)
    return (True, "exit=0")


def _run_one(name, command, timeout, err, assert_block=None):
    """Run one verifier command. Returns (status, evidence_ref, hash, summary).

    status is one of _VERDICT_PASS, _VERDICT_FAIL, _VERDICT_NA. A null or
    empty command means unavailable (n/a); a non-string command is
    rejected as a config error by the caller. A nonzero exit, a timeout,
    or a command that cannot start all count as a fail; the evidence_ref
    records which one happened so the ledger stays auditable.

    When an assert block is present and the command exits 0, the captured
    stdout plus stderr is checked against the assert contains and
    excludes lists. A failed assert (a missing contains pattern or a
    matched excludes pattern) marks the verifier fail with the specific
    pattern in evidence_ref. This catches the false green where a
    verifier exits 0 without doing the work.
    """
    if not command:
        return (_VERDICT_NA, "no command configured", "", "n/a  (no command)")
    try:
        completed = subprocess.run(shlex.split(command),
                                   capture_output=True, text=True,
                                   timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        output = (expired.stdout or "") + (expired.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        artifact = hashlib.sha256(output.encode("utf-8")).hexdigest()
        return (_VERDICT_FAIL, "timeout after %ds" % timeout, artifact,
                "fail  (timeout)  %s" % command)
    except (OSError, ValueError) as error:
        return (_VERDICT_FAIL, "not runnable: %s" % error, "",
                "fail  (not runnable)  %s" % command)
    output = (completed.stdout or "") + (completed.stderr or "")
    artifact = hashlib.sha256(output.encode("utf-8")).hexdigest()
    if completed.returncode != 0:
        return (_VERDICT_FAIL, "exit=%d" % completed.returncode, artifact,
                "fail  (exit %d)  %s" % (completed.returncode, command))
    if assert_block:
        passed, detail = _check_assert(output, assert_block)
        if not passed:
            return (_VERDICT_FAIL, detail, artifact,
                    "fail  (assert)  %s" % command)
    return (_VERDICT_PASS, "exit=0", artifact,
            "pass  (exit 0)  %s" % command)


def _ledger_record(name, status, evidence_ref, command, artifact):
    """Build one ndjson record matching schemas/evidence.schema.json keys.

    The exit code and timeout note go inside evidence_ref, not as extra
    JSON keys: the evidence schema sets additionalProperties false.
    """
    if status == _VERDICT_PASS:
        record_status = "confirmed"
    elif status == _VERDICT_NA:
        record_status = "unverified"
    else:
        record_status = "unverified"
    return {
        "claim": "verifier %s %s" % (name, status),
        "status": record_status,
        "evidence_ref": evidence_ref,
        "source_type": "test",
        "verifier": command or "",
        "hash": artifact,
        "ts": _now(),
    }


def _append_ledger(ledger_file, record, err):
    try:
        directory = os.path.dirname(ledger_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(ledger_file, "a") as ledger:
            ledger.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as error:
        print("agent-os: ledger not written (%s)" % error, file=err)


def _writeback_status(state_file, derived, err):
    """Write the derived verdicts into STATE.yaml verification_status.

    A scoped text replacement preserves every other field and the file
    formatting. The block runs from the `verification_status:` line to the
    next top-level key (a line that starts at column 0 with a non-space
    char). Each `  <name>: <old>` line inside it is rewritten. When the
    block or a field is absent, fall back to a minimal full rewrite of the
    file from the parsed mapping (handles the rare state file that uses a
    different shape).
    """
    try:
        with open(state_file) as source:
            text = source.read()
    except OSError as error:
        print("agent-os: cannot write back status (%s)" % error, file=err)
        return
    new_text = _replace_block(text, derived)
    if new_text is None:
        new_text = _full_rewrite(state_file, text, derived, err)
    if new_text is None:
        return
    try:
        with open(state_file, "w") as output:
            output.write(new_text)
    except OSError as error:
        print("agent-os: cannot write back status (%s)" % error, file=err)


_BLOCK_FIELD = re.compile(r"^(\s{2,})([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\S.*)$")


def _replace_block(text, derived):
    """Rewrite the verification_status block in place, or return None."""
    lines = text.splitlines()
    block_start = None
    for index, line in enumerate(lines):
        if line.rstrip() == "verification_status:":
            block_start = index
            break
    if block_start is None:
        return None
    block_indent = None
    end = len(lines)
    for index in range(block_start + 1, len(lines)):
        line = lines[index]
        if line.strip() == "":
            continue
        if not line.startswith(" "):
            end = index
            break
        if block_indent is None:
            block_indent = len(line) - len(line.lstrip(" "))
    if block_indent is None:
        block_indent = 2
    replaced = {}
    for index in range(block_start + 1, end):
        line = lines[index]
        match = _BLOCK_FIELD.match(line)
        if not match:
            continue
        indent, name, _old = match.group(1), match.group(2), match.group(3)
        if name not in derived:
            continue
        lines[index] = "%s%s: %s" % (indent, name, derived[name])
        replaced[name] = True
    if set(replaced.keys()) != set(derived.keys()):
        return None  # a field was missing: fall back to full rewrite
    if text.endswith("\n") and not lines:
        lines.append("")
    result = "\n".join(lines)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def _full_serialize(value, indent=0):
    """Minimal YAML serializer for the types STATE.yaml uses."""
    pad = "  " * indent
    if isinstance(value, dict):
        out = []
        for key, val in value.items():
            if isinstance(val, (dict, list)):
                out.append("%s%s:" % (pad, key))
                out.append(_full_serialize(val, indent + 1))
            else:
                out.append("%s%s: %s" % (pad, key, _full_scalar(val)))
        return "\n".join(out)
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                inner = _full_serialize(item, indent + 1).lstrip()
                out.append("%s- %s" % (pad, inner))
            else:
                out.append("%s- %s" % (pad, _full_scalar(item)))
        return "\n".join(out)
    return "%s%s" % (pad, _full_scalar(value))


def _full_scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)


def _full_rewrite(state_file, text, derived, err):
    try:
        data = yaml_min.load(text)
    except yaml_min.YamlError as error:
        print("agent-os: cannot rewrite STATE.yaml (%s)" % error, file=err)
        return None
    if not isinstance(data, dict):
        return None
    status = data.get("verification_status")
    if not isinstance(status, dict):
        status = {}
    for name, value in derived.items():
        status[name] = value
    data["verification_status"] = status
    return _full_serialize(data) + "\n"


def _validate_assert(name, assert_block):
    """Validate an assert block. Returns an error message string or None.

    An assert block must be a mapping with optional contains and
    excludes keys. Each key, when present, must hold a list of strings.
    A non-mapping assert or a non-list entry is a config error: the
    subset parser raises rather than silently accepting a shape it does
    not support (per AGENTS.md).
    """
    if not isinstance(assert_block, dict):
        return "verification assert '%s' is not a mapping" % name
    for key in ("contains", "excludes"):
        values = assert_block.get(key)
        if values is None:
            continue
        if not isinstance(values, list):
            return ("verification assert '%s' %s is not a list"
                    % (name, key))
        for item in values:
            if not isinstance(item, str):
                return ("verification assert '%s' %s has a non-string "
                        "entry" % (name, key))
    return None


def run_verify(config_path, state_file, ledger_file, timeout=600, err=None):
    """Run the configured verifiers and write the derived status back.

    Returns 0 when every configured verifier is pass or n/a, 1 when any
    configured verifier failed, and 2 on a config error. A missing config
    is a no-op (exit 0), so a fresh repo still passes.
    """
    err = err or sys.stderr
    config, load_error = _load_config(config_path, err)
    if config is None:
        return load_error
    commands = config.get("commands") or {}
    if not isinstance(commands, dict):
        print("agent-os: verification config 'commands' is not a mapping",
              file=err)
        return 2
    configured_timeout = config.get("timeout", 600)
    if not isinstance(configured_timeout, int) or isinstance(configured_timeout,
                                                              bool):
        configured_timeout = 600
    # A CLI timeout overrides the config so an operator can shorten a run
    # without editing the file. None means the CLI left it to the config.
    if timeout is not None:
        configured_timeout = timeout

    derived = {}
    records = []
    summaries = []
    any_fail = False
    for name in _VERIFIERS:
        entry = commands.get(name)
        assert_block = None
        if isinstance(entry, dict):
            # Issue #35: a mapping value carries a command plus an
            # optional assert block with contains and excludes lists.
            assert_block = entry.get("assert")
            command = entry.get("command")
        else:
            command = entry
        if command is not None and not isinstance(command, str):
            print("agent-os: verification command '%s' is not a string; "
                  "quote the command or set it to null" % name, file=err)
            return 2
        if assert_block is not None:
            assert_error = _validate_assert(name, assert_block)
            if assert_error:
                print("agent-os: %s" % assert_error, file=err)
                return 2
            if command is None or (isinstance(command, str)
                                   and command.strip() == ""):
                print("agent-os: warning: verifier '%s' has an assert "
                      "block but no command; the assert is ignored"
                      % name, file=err)
        if command is None or command.strip() == "":
            status, evidence_ref, artifact, summary = (
                _VERDICT_NA, "no command configured", "", "n/a  (no command)")
        else:
            status, evidence_ref, artifact, summary = _run_one(
                name, command, configured_timeout, err, assert_block)
        derived[name] = status
        records.append(_ledger_record(name, status, evidence_ref, command or "", artifact))
        summaries.append("  %s: %s" % (name, summary))
        if status == _VERDICT_FAIL:
            any_fail = True

    for record in records:
        _append_ledger(ledger_file, record, err)
    _writeback_status(state_file, derived, err)
    print("agent-os: ran verifiers from %s" % config_path)
    for line in summaries:
        print(line)
    if any_fail:
        return 1
    return 0