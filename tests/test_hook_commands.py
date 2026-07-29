import json
import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
