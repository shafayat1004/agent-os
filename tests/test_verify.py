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


if __name__ == "__main__":
    unittest.main()