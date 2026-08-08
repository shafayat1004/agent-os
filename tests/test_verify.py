import json
import os
import subprocess
import sys
import tempfile
import unittest

from agentos import yaml_min

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTOS = os.path.join(_ROOT, "bin", "agentos")

_PASS_COMMAND = '"%s" -c "pass"' % sys.executable
_FAIL_COMMAND = '"%s" -c "import sys; sys.exit(3)"' % sys.executable
_SLEEP_COMMAND = '"%s" -c "import time; time.sleep(5)"' % sys.executable
# Commands that print known output so content asserts can match it.
_PRINT_FABLE = ('"%s" -c "print(\'Started Fable compilation\')"'
                % sys.executable)
_PRINT_SKIP = ('"%s" -c "print(\'Skipped compilation because all '
               'generated files are up-to-date\')"' % sys.executable)
_PRINT_ERROR = ('"%s" -c "print(\'error FS0001: bad code\')"'
                 % sys.executable)

_STATE = (
    "task_id: t1\n"
    "goal: g\n"
    "risk_class: reversible\n"
    "acceptance_criteria: [done means green]\n"
    "verification_status:\n"
    "  format: pending\n"
    "  compile: pending\n"
    "  tests: pending\n"
    "  policy: pending\n"
    "  security: pending\n"
    "next_action: n\n"
)


def _config(commands, timeout=60):
    lines = ["commands:"]
    for name in ("format", "compile", "tests", "policy", "security"):
        value = commands.get(name)
        if value is None:
            lines.append("  %s: null" % name)
        else:
            lines.append('  %s: "%s"' % (name, value))
    lines.append("timeout: %d" % timeout)
    return "\n".join(lines) + "\n"


def _run(args, cwd):
    return subprocess.run([_AGENTOS] + args, cwd=cwd,
                          capture_output=True, text=True)


def _state_value(temp_dir, field):
    with open(os.path.join(temp_dir, "STATE.yaml")) as state_file:
        state = yaml_min.load(state_file.read())
    return state.get("verification_status", {}).get(field)


def _ledger_lines(temp_dir):
    path = os.path.join(temp_dir, "evidence", "ledger.ndjson")
    with open(path) as ledger_file:
        return [json.loads(line) for line in ledger_file if line.strip()]


class TestVerify(unittest.TestCase):
    def _repo(self, temp_dir, commands):
        with open(os.path.join(temp_dir, "STATE.yaml"), "w") as out:
            out.write(_STATE)
        os.makedirs(os.path.join(temp_dir, "evidence"), exist_ok=True)
        with open(os.path.join(temp_dir, "evidence", "ledger.ndjson"), "w") as out:
            out.write("")
        config_dir = os.path.join(temp_dir, "policies")
        os.makedirs(config_dir, exist_ok=True)
        with open(os.path.join(config_dir, "verification.yaml"), "w") as out:
            out.write(_config(commands))

    def test_passing_command_sets_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, {"tests": _PASS_COMMAND})
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "tests"), "pass")
            tests_lines = [record for record in _ledger_lines(temp_dir)
                           if "tests" in record["claim"]]
            self.assertTrue(any("pass" in record["claim"]
                                for record in tests_lines))

    def test_failing_command_sets_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, {"tests": _FAIL_COMMAND})
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "tests"), "fail")
            tests_lines = [record for record in _ledger_lines(temp_dir)
                           if "tests" in record["claim"]]
            self.assertTrue(any("fail" in record["claim"]
                                for record in tests_lines))

    def test_timeout_sets_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, {"tests": _SLEEP_COMMAND})
            completed = _run(["verify", "--timeout", "1"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "tests"), "fail")
            tests_line = [record for record in _ledger_lines(temp_dir)
                          if "tests" in record["claim"]][0]
            self.assertIn("timeout", tests_line["evidence_ref"])

    def test_unavailable_command_sets_na(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, {})
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "tests"), "n/a")
            self.assertEqual(_state_value(temp_dir, "format"), "n/a")

    def test_missing_config_skips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "STATE.yaml"), "w") as out:
                out.write(_STATE)
            os.makedirs(os.path.join(temp_dir, "evidence"), exist_ok=True)
            with open(os.path.join(temp_dir, "evidence", "ledger.ndjson"),
                      "w") as out:
                out.write("")
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("skipped", completed.stderr + completed.stdout)

    def test_not_runnable_command_sets_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, {"tests": "nonexistent-binary-xyz-123"})
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "tests"), "fail")
            tests_line = [record for record in _ledger_lines(temp_dir)
                          if "tests" in record["claim"]][0]
            self.assertIn("not runnable", tests_line["evidence_ref"])

    def test_records_command_exit_hash_in_ledger(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, {"tests": _PASS_COMMAND})
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            record = [record for record in _ledger_lines(temp_dir)
                      if "tests" in record["claim"]
                      and "pass" in record["claim"]][0]
            self.assertEqual(record["verifier"], _PASS_COMMAND)
            self.assertEqual(len(record["hash"]), 64)
            self.assertNotEqual(record["hash"], "")
            self.assertEqual(record["source_type"], "test")
            self.assertEqual(record["status"], "confirmed")
            self.assertTrue(record["ts"])

    def test_non_string_command_is_config_error(self):
        # A command value that is not a string (here an integer, a likely
        # config typo) is a config error, not a silent n/a.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, {"tests": _PASS_COMMAND})
            config_path = os.path.join(temp_dir, "policies",
                                       "verification.yaml")
            with open(config_path, "w") as out:
                out.write("commands:\n  tests: 123\ntimeout: 60\n")
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("not a string", completed.stderr)

    def test_full_rewrite_fallback_preserves_fields(self):
        # A verification_status block that misses a field cannot be patched
        # in place, so the whole file is rewritten from the parsed mapping.
        # Every other field must survive.
        with tempfile.TemporaryDirectory() as temp_dir:
            state = (
                "task_id: t1\n"
                "goal: keep me\n"
                "risk_class: reversible\n"
                "acceptance_criteria: [done]\n"
                "confirmed_facts:\n"
                "  - fact: a fact stays\n"
                "    evidence_ref: ref\n"
                "verification_status:\n"
                "  format: pending\n"
                "  compile: pending\n"
                "  tests: pending\n"
                "  policy: pending\n"
                "next_action: n\n"
                "stop_readiness: blocked\n"
            )
            with open(os.path.join(temp_dir, "STATE.yaml"), "w") as out:
                out.write(state)
            os.makedirs(os.path.join(temp_dir, "evidence"), exist_ok=True)
            with open(os.path.join(temp_dir, "evidence", "ledger.ndjson"),
                      "w") as out:
                out.write("")
            os.makedirs(os.path.join(temp_dir, "policies"), exist_ok=True)
            with open(os.path.join(temp_dir, "policies",
                                   "verification.yaml"), "w") as out:
                out.write(_config({"tests": _PASS_COMMAND}))
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with open(os.path.join(temp_dir, "STATE.yaml")) as state_file:
                after = yaml_min.load(state_file.read())
            self.assertEqual(after["goal"], "keep me")
            self.assertEqual(after["stop_readiness"], "blocked")
            self.assertEqual(after["confirmed_facts"][0]["fact"],
                             "a fact stays")
            self.assertEqual(after["verification_status"]["tests"], "pass")
            # The missing field was added back with its derived value.
            self.assertEqual(after["verification_status"]["security"], "n/a")

    def test_preserves_other_state_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = (
                "task_id: t1\n"
                "goal: keep me\n"
                "risk_class: reversible\n"
                "acceptance_criteria: [done]\n"
                "confirmed_facts:\n"
                "  - fact: a fact stays\n"
                "    evidence_ref: ref\n"
                "decisions:\n"
                "  - decision: a decision stays\n"
                "    rationale: why\n"
                "verification_status:\n"
                "  format: pending\n"
                "  compile: pending\n"
                "  tests: pending\n"
                "  policy: pending\n"
                "  security: pending\n"
                "next_action: n\n"
                "stop_readiness: blocked\n"
            )
            with open(os.path.join(temp_dir, "STATE.yaml"), "w") as out:
                out.write(state)
            os.makedirs(os.path.join(temp_dir, "evidence"), exist_ok=True)
            with open(os.path.join(temp_dir, "evidence", "ledger.ndjson"),
                      "w") as out:
                out.write("")
            os.makedirs(os.path.join(temp_dir, "policies"), exist_ok=True)
            with open(os.path.join(temp_dir, "policies",
                                   "verification.yaml"), "w") as out:
                out.write(_config({"tests": _PASS_COMMAND}))
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with open(os.path.join(temp_dir, "STATE.yaml")) as state_file:
                after = yaml_min.load(state_file.read())
            self.assertEqual(after["goal"], "keep me")
            self.assertEqual(after["stop_readiness"], "blocked")
            self.assertEqual(after["confirmed_facts"][0]["fact"],
                             "a fact stays")
            self.assertEqual(after["decisions"][0]["decision"],
                             "a decision stays")
            self.assertEqual(after["verification_status"]["tests"], "pass")


class TestVerifyAsserts(unittest.TestCase):
    """Content assertions on verifier output (issue #35).

    Each verifier value in commands can be a string (the #9 shape) or a
    mapping with a command plus an assert block. A zero exit with a
    failed assert marks the verifier fail with the pattern in
    evidence_ref, so the ledger records why.
    """

    def _assert_config(self, name, command, contains=None, excludes=None,
                       timeout=60):
        lines = ["commands:"]
        for field in ("format", "compile", "tests", "policy", "security"):
            if field == name:
                lines.append("  %s:" % field)
                lines.append('    command: "%s"' % command)
                if contains or excludes:
                    lines.append("    assert:")
                    if contains:
                        lines.append("      contains:")
                        for pattern in contains:
                            lines.append('        - "%s"' % pattern)
                    if excludes:
                        lines.append("      excludes:")
                        for pattern in excludes:
                            lines.append('        - "%s"' % pattern)
            else:
                lines.append("  %s: null" % field)
        lines.append("timeout: %d" % timeout)
        return "\n".join(lines) + "\n"

    def _repo(self, temp_dir, config_text):
        state = (
            "task_id: t1\n"
            "goal: g\n"
            "risk_class: reversible\n"
            "acceptance_criteria: [done means green]\n"
            "verification_status:\n"
            "  format: pending\n"
            "  compile: pending\n"
            "  tests: pending\n"
            "  policy: pending\n"
            "  security: pending\n"
            "next_action: n\n"
            "stop_readiness: ready\n"
        )
        with open(os.path.join(temp_dir, "STATE.yaml"), "w") as out:
            out.write(state)
        os.makedirs(os.path.join(temp_dir, "evidence"), exist_ok=True)
        with open(os.path.join(temp_dir, "evidence", "ledger.ndjson"),
                  "w") as out:
            out.write("")
        os.makedirs(os.path.join(temp_dir, "policies"), exist_ok=True)
        with open(os.path.join(temp_dir, "policies",
                               "verification.yaml"), "w") as out:
            out.write(config_text)

    def test_pass_exit_plus_pass_assert(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._assert_config(
                "compile", _PRINT_FABLE,
                contains=["Started Fable compilation"],
                excludes=["error FS", "Skipped compilation"])
            self._repo(temp_dir, config)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "compile"), "pass")

    def test_pass_exit_plus_failed_contains(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._assert_config(
                "compile", _PASS_COMMAND,
                contains=["Started Fable compilation"])
            self._repo(temp_dir, config)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "compile"), "fail")
            record = [r for r in _ledger_lines(temp_dir)
                      if "compile" in r["claim"]][0]
            self.assertIn("assert missing", record["evidence_ref"])
            self.assertIn("Started Fable compilation",
                          record["evidence_ref"])

    def test_pass_exit_plus_matched_excludes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._assert_config(
                "compile", _PRINT_SKIP,
                excludes=["Skipped compilation"])
            self._repo(temp_dir, config)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "compile"), "fail")
            record = [r for r in _ledger_lines(temp_dir)
                      if "compile" in r["claim"]][0]
            self.assertIn("assert forbidden", record["evidence_ref"])
            self.assertIn("Skipped compilation", record["evidence_ref"])

    def test_timeout_with_assert_present(self):
        # A timeout is a fail regardless of asserts; the assert is not
        # checked when the command already timed out.
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._assert_config(
                "compile", _SLEEP_COMMAND,
                contains=["Started Fable compilation"])
            self._repo(temp_dir, config)
            completed = _run(["verify", "--timeout", "1"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "compile"), "fail")
            record = [r for r in _ledger_lines(temp_dir)
                      if "compile" in r["claim"]][0]
            self.assertIn("timeout", record["evidence_ref"])

    def test_nonzero_exit_skips_assert(self):
        # A nonzero exit is a fail; the assert is not checked because
        # the command already failed the exit-code gate.
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._assert_config(
                "compile", _FAIL_COMMAND,
                contains=["Started Fable compilation"])
            self._repo(temp_dir, config)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "compile"), "fail")
            record = [r for r in _ledger_lines(temp_dir)
                      if "compile" in r["claim"]][0]
            self.assertIn("exit=3", record["evidence_ref"])
            self.assertNotIn("assert", record["evidence_ref"])

    def test_assert_fail_writeback_full_rewrite(self):
        # A verification_status block missing the compile field forces
        # the full-rewrite fallback; the derived fail must still write
        # back and the other fields must survive.
        with tempfile.TemporaryDirectory() as temp_dir:
            state = (
                "task_id: t1\n"
                "goal: keep me\n"
                "risk_class: reversible\n"
                "acceptance_criteria: [done]\n"
                "confirmed_facts:\n"
                "  - fact: a fact stays\n"
                "    evidence_ref: ref\n"
                "verification_status:\n"
                "  format: pending\n"
                "  tests: pending\n"
                "  policy: pending\n"
                "next_action: n\n"
                "stop_readiness: blocked\n"
            )
            with open(os.path.join(temp_dir, "STATE.yaml"), "w") as out:
                out.write(state)
            os.makedirs(os.path.join(temp_dir, "evidence"), exist_ok=True)
            with open(os.path.join(temp_dir, "evidence", "ledger.ndjson"),
                      "w") as out:
                out.write("")
            os.makedirs(os.path.join(temp_dir, "policies"), exist_ok=True)
            config = self._assert_config(
                "compile", _PASS_COMMAND,
                contains=["Started Fable compilation"])
            with open(os.path.join(temp_dir, "policies",
                                   "verification.yaml"), "w") as out:
                out.write(config)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            with open(os.path.join(temp_dir, "STATE.yaml")) as f:
                after = yaml_min.load(f.read())
            self.assertEqual(after["goal"], "keep me")
            self.assertEqual(after["stop_readiness"], "blocked")
            self.assertEqual(after["confirmed_facts"][0]["fact"],
                             "a fact stays")
            self.assertEqual(after["verification_status"]["compile"],
                             "fail")
            self.assertEqual(after["verification_status"]["security"],
                             "n/a")

    def test_done_refuses_on_failed_assert(self):
        # The done gate runs verify first; a failed assert makes verify
        # return nonzero, so done refuses the claim.
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._assert_config(
                "tests", _PASS_COMMAND,
                contains=["Started Fable compilation"])
            self._repo(temp_dir, config)
            completed = _run(["done"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "tests"), "fail")

    def test_done_passes_with_passing_assert(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._assert_config(
                "tests", _PRINT_FABLE,
                contains=["Started Fable compilation"])
            self._repo(temp_dir, config)
            completed = _run(["done"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_assert_not_mapping_is_config_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_text = (
                "commands:\n"
                "  compile:\n"
                "    command: \"%s\"\n"
                '    assert: "not a mapping"\n'
                "  tests: null\n"
                "  format: null\n"
                "  policy: null\n"
                "  security: null\n"
                "timeout: 60\n" % _PASS_COMMAND
            )
            self._repo(temp_dir, config_text)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("not a mapping", completed.stderr)

    def test_assert_contains_not_list_is_config_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_text = (
                "commands:\n"
                "  compile:\n"
                "    command: \"%s\"\n"
                "    assert:\n"
                "      contains: \"not a list\"\n"
                "  tests: null\n"
                "  format: null\n"
                "  policy: null\n"
                "  security: null\n"
                "timeout: 60\n" % _PASS_COMMAND
            )
            self._repo(temp_dir, config_text)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("not a list", completed.stderr)

    def test_string_command_still_works_no_regression(self):
        # A plain string command (the #9 shape, no assert) must behave
        # identically to before.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _config({"tests": _PASS_COMMAND}))
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(_state_value(temp_dir, "tests"), "pass")

    def test_assert_on_null_command_warns(self):
        # An assert block on a null command is a silent no-op; warn so
        # the misconfiguration is visible.
        with tempfile.TemporaryDirectory() as temp_dir:
            config_text = (
                "commands:\n"
                "  compile:\n"
                "    command: null\n"
                "    assert:\n"
                '      contains:\n'
                '        - "Started Fable compilation"\n'
                "  tests: null\n"
                "  format: null\n"
                "  policy: null\n"
                "  security: null\n"
                "timeout: 60\n"
            )
            self._repo(temp_dir, config_text)
            completed = _run(["verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("assert is ignored", completed.stderr)


if __name__ == "__main__":
    unittest.main()
