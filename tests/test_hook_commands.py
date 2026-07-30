import json
import os
import subprocess
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTOS = os.path.join(_ROOT, "bin", "agentos")

_POLICY = (
    "may_edit: [src]\n"
    "ask_first: [deploy]\n"
    'never: ["*.render", .git]\n'
)

_VALID_STATE = (
    "task_id: t1\n"
    "goal: g\n"
    "risk_class: reversible\n"
    "acceptance_criteria: []\n"
    "verification_status:\n"
    "  format: pending\n"
    "  compile: pending\n"
    "  tests: pending\n"
    "  policy: pending\n"
    "  security: pending\n"
    "next_action: n\n"
)


def _write(root, relative, content):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as output_file:
        output_file.write(content)


def _run(arguments, cwd, stdin_text=""):
    return subprocess.run([_AGENTOS] + arguments, cwd=cwd, input=stdin_text,
                          capture_output=True, text=True)


def _tool_payload(path_key, path_value):
    return json.dumps({"tool_input": {path_key: path_value}})


class TestHookPreTool(unittest.TestCase):
    def _repo(self, temp_dir):
        _write(temp_dir, os.path.join("policies", "path-policy.yaml"), _POLICY)

    def test_never_path_blocks_with_exit_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("file_path", "gen/out.render"))
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("never", completed.stderr)

    def test_ask_first_warns_with_exit_1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("file_path", "deploy/release.sh"))
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("ask_first", completed.stderr)

    def test_may_edit_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("file_path", "src/main.py"))
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_undeclared_path_warns_with_exit_1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("file_path", "other/thing.py"))
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("outside declared scope", completed.stderr)

    def test_absolute_path_inside_repo_is_checked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            target = os.path.join(temp_dir, "gen", "out.render")
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("file_path", target))
            self.assertEqual(completed.returncode, 2, completed.stderr)

    def test_absolute_path_outside_repo_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("file_path", "/etc/passwd"))
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_notebook_path_is_checked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("notebook_path", "gen/out.render"))
            self.assertEqual(completed.returncode, 2, completed.stderr)

    def test_missing_file_path_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir, "{}")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_malformed_json_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir, "not json at all")
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_missing_policy_allows(self):
        # A guardrail that cannot load must fail open, never wedge the editor.
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["hook-pre-tool"], temp_dir,
                             _tool_payload("file_path", "gen/out.render"))
            self.assertEqual(completed.returncode, 0, completed.stderr)


class TestCheckPath(unittest.TestCase):
    def _repo(self, temp_dir):
        _write(temp_dir, os.path.join("policies", "path-policy.yaml"), _POLICY)

    def test_never_blocks_with_exit_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-path", "gen/out.render"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("never", completed.stderr)

    def test_ask_first_warns_with_exit_1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-path", "deploy/release.sh"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)

    def test_may_edit_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-path", "src/main.py"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_undeclared_warns_with_exit_1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-path", "other/thing.py"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)

    def test_worst_code_wins_across_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-path", "src/a.py", "gen/x.render"],
                             temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)

    def test_missing_policy_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["check-path", "gen/out.render"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)


class TestHookStop(unittest.TestCase):
    def test_valid_artifacts_allow_stop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, "STATE.yaml", _VALID_STATE)
            _write(temp_dir, os.path.join("evidence", "ledger.ndjson"), "")
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_invalid_state_blocks_stop_with_exit_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, "STATE.yaml", "task_id:\ngoal:\nnext_action:\n")
            _write(temp_dir, os.path.join("evidence", "ledger.ndjson"), "")
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("goal", completed.stderr)

    def test_missing_artifacts_allow_stop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)


def _state_with(readiness=None, verdicts=None, criteria="[done means green]"):
    lines = ["task_id: t1", "goal: g", "risk_class: reversible"]
    if readiness:
        lines.append("stop_readiness: %s" % readiness)
    lines.append("acceptance_criteria: %s" % criteria)
    lines.append("verification_status:")
    for name in ("format", "compile", "tests", "policy", "security"):
        value = (verdicts or {}).get(name, "pass")
        lines.append("  %s: %s" % (name, value))
    lines.append("next_action: n")
    return "\n".join(lines) + "\n"


_PASS_COMMAND = '"%s" -c "pass"' % sys.executable
_FAIL_COMMAND = '"%s" -c "import sys; sys.exit(3)"' % sys.executable


class TestHookStopVerdict(unittest.TestCase):
    def _repo(self, temp_dir, state_text):
        _write(temp_dir, "STATE.yaml", state_text)
        _write(temp_dir, os.path.join("evidence", "ledger.ndjson"), "")

    def test_ready_with_green_verdicts_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_ready_with_pending_verdict_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready",
                                             verdicts={"tests": "pending"}))
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("tests", completed.stderr)

    def test_ready_with_failed_verdict_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready",
                                             verdicts={"policy": "fail"}))
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("policy", completed.stderr)

    def test_ready_with_empty_criteria_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready", criteria="[]"))
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("acceptance_criteria", completed.stderr)

    def test_blocked_readiness_skips_verdict_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="blocked",
                                             verdicts={"tests": "pending"},
                                             criteria="[]"))
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_absent_readiness_skips_verdict_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(verdicts={"tests": "pending"}))
            completed = _run(["hook-stop"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_run_tests_passing_command_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            completed = _run(["hook-stop", "--run-tests", _PASS_COMMAND],
                             temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_run_tests_failing_command_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            completed = _run(["hook-stop", "--run-tests", _FAIL_COMMAND],
                             temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("test command", completed.stderr)

    def test_run_tests_not_run_without_ready_claim(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="blocked"))
            completed = _run(["hook-stop", "--run-tests", _FAIL_COMMAND],
                             temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)


def _config_text(commands):
    lines = ["commands:"]
    for name in ("format", "compile", "tests", "policy", "security"):
        value = commands.get(name)
        if value is None:
            lines.append("  %s: null" % name)
        else:
            lines.append('  %s: "%s"' % (name, value))
    lines.append("timeout: 60")
    return "\n".join(lines) + "\n"


class TestHookDone(unittest.TestCase):
    def _repo(self, temp_dir, state_text):
        _write(temp_dir, "STATE.yaml", state_text)
        _write(temp_dir, os.path.join("evidence", "ledger.ndjson"), "")

    def test_done_ready_with_green_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_done_missing_readiness_blocks_with_actionable_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(verdicts={"tests": "pass"}))
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("stop_readiness is not set", completed.stderr)
            self.assertIn("ready", completed.stderr)

    def test_done_blocked_readiness_blocks_with_actionable_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="blocked",
                                              verdicts={"tests": "pass"}))
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("blocked", completed.stderr)
            self.assertIn("ready", completed.stderr)

    def test_done_malformed_readiness_blocks(self):
        # The task-state schema enum is [ready, blocked], so a value that
        # is neither is caught by the always-on schema check (exit 2). This
        # covers "malformed is rejected" without weakening the schema.
        with tempfile.TemporaryDirectory() as temp_dir:
            state_text = _state_with(verdicts={"tests": "pass"})
            state_text = state_text.replace(
                "acceptance_criteria: [done means green]",
                "acceptance_criteria: [done means green]\n"
                "stop_readiness: maybe")
            self._repo(temp_dir, state_text)
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertTrue("stop_readiness" in completed.stderr
                            or "schema" in completed.stderr.lower(),
                            completed.stderr)

    def test_done_ready_with_pending_verdict_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready",
                                              verdicts={"tests": "pending"}))
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("tests", completed.stderr)

    def test_done_ready_with_empty_criteria_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready", criteria="[]"))
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("acceptance_criteria", completed.stderr)

    def test_done_run_tests_passing_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            completed = _run(["done", "--no-verify", "--run-tests",
                              _PASS_COMMAND], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_done_run_tests_failing_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            completed = _run(["done", "--no-verify", "--run-tests",
                              _FAIL_COMMAND], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("test command", completed.stderr)

    def test_done_invalid_state_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, "STATE.yaml", "task_id:\ngoal:\nnext_action:\n")
            _write(temp_dir, os.path.join("evidence", "ledger.ndjson"), "")
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)

    def test_done_missing_artifacts_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["done", "--no-verify"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_done_with_verify_derives_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            _write(temp_dir, os.path.join("policies", "verification.yaml"),
                   _config_text({"tests": _PASS_COMMAND,
                                 "policy": _FAIL_COMMAND}))
            completed = _run(["done", "--run-tests", _PASS_COMMAND], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("policy", completed.stderr)

    def test_done_no_verify_skips_verify(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _state_with(readiness="ready"))
            _write(temp_dir, os.path.join("policies", "verification.yaml"),
                   _config_text({"tests": _PASS_COMMAND,
                                 "policy": _FAIL_COMMAND}))
            completed = _run(["done", "--no-verify", "--run-tests",
                              _PASS_COMMAND], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)


class TestHookPostTool(unittest.TestCase):
    def _trace_lines(self, temp_dir, relative=os.path.join("evidence",
                                                           "trace.ndjson")):
        path = os.path.join(temp_dir, relative)
        if not os.path.exists(path):
            return []
        with open(path) as trace_file:
            return [json.loads(line) for line in trace_file if line.strip()]

    def test_flags_append_trace_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["hook-post-tool", "--tool", "edit",
                              "--target", "src/a.py"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = self._trace_lines(temp_dir)
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["tool"], "edit")
            self.assertEqual(lines[0]["target"], "src/a.py")
            self.assertIn("ts", lines[0])

    def test_stdin_payload_supplies_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = json.dumps({"tool_name": "Write",
                                  "tool_input": {"file_path": "docs/x.md"}})
            completed = _run(["hook-post-tool"], temp_dir, payload)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = self._trace_lines(temp_dir)
            self.assertEqual(lines[0]["tool"], "Write")
            self.assertEqual(lines[0]["target"], "docs/x.md")

    def test_bash_command_is_a_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = json.dumps({"tool_name": "Bash",
                                  "tool_input": {"command": "ls -la"}})
            completed = _run(["hook-post-tool"], temp_dir, payload)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = self._trace_lines(temp_dir)
            self.assertEqual(lines[0]["target"], "ls -la")

    def test_flags_override_stdin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = json.dumps({"tool_name": "Write",
                                  "tool_input": {"file_path": "docs/x.md"}})
            completed = _run(["hook-post-tool", "--target", "src/b.py"],
                             temp_dir, payload)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = self._trace_lines(temp_dir)
            self.assertEqual(lines[0]["target"], "src/b.py")

    def test_flags_mode_ignores_stdin_payload(self):
        # Flag mode is the adapter contract: once --tool or --target is
        # given, stdin is not consulted at all (see the hang regression
        # test below for why reading it is unsafe).
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = json.dumps({"tool_name": "Write",
                                  "tool_input": {"file_path": "docs/x.md"}})
            completed = _run(["hook-post-tool", "--tool", "edit",
                              "--target", "src/a.py"], temp_dir, payload)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = self._trace_lines(temp_dir)
            self.assertEqual(lines[0]["tool"], "edit")
            self.assertEqual(lines[0]["target"], "src/a.py")

    def test_flags_mode_does_not_block_on_held_open_stdin(self):
        # Regression for the opencode freeze: the CLI used to call
        # sys.stdin.read() unconditionally, so a harness that spawns hooks
        # with an inherited, never-EOF stdin (opencode's Bun shell) wedged
        # the session after the first tool call. Simulate that harness by
        # holding the child's stdin pipe open from the parent.
        with tempfile.TemporaryDirectory() as temp_dir:
            process = subprocess.Popen(
                [_AGENTOS, "hook-post-tool", "--tool", "edit",
                 "--target", "src/a.py"],
                cwd=temp_dir, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                self.fail("hook-post-tool blocked on a held-open stdin")
            finally:
                for stream in (process.stdin, process.stdout,
                               process.stderr):
                    if stream:
                        stream.close()
                if process.poll() is None:
                    process.kill()
            self.assertEqual(process.returncode, 0)
            lines = self._trace_lines(temp_dir)
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["tool"], "edit")

    def test_malformed_input_writes_nothing_and_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["hook-post-tool"], temp_dir, "not json at all")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(self._trace_lines(temp_dir), [])

    def test_unwritable_trace_still_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, "blocker", "a file, not a directory")
            completed = _run(["hook-post-tool", "--tool", "edit",
                              "--target", "src/a.py",
                              "--trace", os.path.join("blocker",
                                                      "trace.ndjson")],
                             temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_custom_trace_path_creates_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            relative = os.path.join("logs", "deep", "trace.ndjson")
            completed = _run(["hook-post-tool", "--tool", "read",
                              "--trace", relative], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(len(self._trace_lines(temp_dir, relative)), 1)


class TestHookPreCompact(unittest.TestCase):
    def test_valid_state_reminds_and_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, "STATE.yaml", _VALID_STATE)
            completed = _run(["hook-pre-compact"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Refresh STATE.yaml", completed.stdout)

    def test_invalid_state_reports_errors_and_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, "STATE.yaml", "task_id:\ngoal:\nnext_action:\n")
            completed = _run(["hook-pre-compact"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("invalid", completed.stdout)

    def test_missing_state_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["hook-pre-compact"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
