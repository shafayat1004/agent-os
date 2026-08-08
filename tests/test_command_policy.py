import json
import os
import subprocess
import tempfile
import unittest

from agentos.checks.command import classify

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTOS = os.path.join(_ROOT, "bin", "agentos")

_POLICY = (
    "tools:\n"
    "  bash:\n"
    "    deny:\n"
    "      - pattern: 'dotnet\\s+fable'\n"
    "        reason: emits stray .fs.js files\n"
    "    warn:\n"
    "      - pattern: 'rm\\s+-rf'\n"
    "        reason: destructive\n"
    "    allow:\n"
    "      - 'git\\s+'\n"
    "      - 'python3\\s+'\n"
)

_POLICY_STRING_ENTRIES = (
    "tools:\n"
    "  bash:\n"
    "    deny: ['rm\\s+-rf\\s+/']\n"
    "    warn: []\n"
    "    allow: []\n"
)

_POLICY_EMPTY = (
    "tools:\n"
    "  bash:\n"
    "    deny: []\n"
    "    warn: []\n"
    "    allow: []\n"
)

_MALFORMED_YAML = (
    "tools:\n"
    "  bash:\n"
    "    deny: [broken\n"
    "     bad indent here\n"
)


def _write(root, relative, content):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as output_file:
        output_file.write(content)


def _run(arguments, cwd, stdin_text=""):
    return subprocess.run([_AGENTOS] + arguments, cwd=cwd, input=stdin_text,
                          capture_output=True, text=True)


class TestClassify(unittest.TestCase):
    def test_deny_match_is_error(self):
        policy = {"tools": {"bash": {"deny": [r"dotnet\s+fable"]}}}
        result = classify(policy, "Bash", "dotnet fable src")
        self.assertFalse(result.ok)
        self.assertEqual(result.findings[0].level, "error")

    def test_deny_with_reason_in_message(self):
        policy = {"tools": {"bash": {"deny": [
            {"pattern": r"dotnet\s+fable", "reason": "stray files"}]}}}
        result = classify(policy, "bash", "dotnet fable")
        self.assertIn("stray files", result.findings[0].message)

    def test_warn_match_is_warn(self):
        policy = {"tools": {"bash": {"warn": [r"rm\s+-rf"]}}}
        result = classify(policy, "bash", "rm -rf /tmp/x")
        self.assertTrue(result.ok)
        self.assertEqual(result.findings[0].level, "warn")

    def test_deny_beats_warn(self):
        policy = {"tools": {"bash": {
            "deny": [r"rm"], "warn": [r"rm\s+-rf"]}}}
        result = classify(policy, "bash", "rm -rf /")
        self.assertFalse(result.ok)
        self.assertEqual(len(result.findings), 1)

    def test_allow_list_unmatched_is_warn(self):
        policy = {"tools": {"bash": {
            "allow": [r"git\s+"]}}}
        result = classify(policy, "bash", "dotnet fable")
        self.assertTrue(result.ok)
        self.assertTrue(any("outside declared scope" in f.message
                            for f in result.findings))

    def test_allow_list_matched_allows(self):
        policy = {"tools": {"bash": {
            "allow": [r"git\s+"]}}}
        result = classify(policy, "bash", "git status")
        self.assertEqual(result.findings, [])

    def test_empty_allow_allows_anything(self):
        policy = {"tools": {"bash": {
            "deny": [], "warn": [], "allow": []}}}
        result = classify(policy, "bash", "anything goes")
        self.assertEqual(result.findings, [])

    def test_no_tool_entry_allows(self):
        result = classify({}, "bash", "rm -rf /")
        self.assertEqual(result.findings, [])

    def test_tool_name_lowercased(self):
        policy = {"tools": {"bash": {"deny": [r"forbidden"]}}}
        result = classify(policy, "Bash", "forbidden command")
        self.assertFalse(result.ok)

    def test_string_entry_treated_as_pattern(self):
        policy = {"tools": {"bash": {"deny": ["forbidden"]}}}
        result = classify(policy, "bash", "run forbidden now")
        self.assertFalse(result.ok)

    def test_none_policy_does_not_crash(self):
        # An empty YAML file loads as None; the classifier must treat it
        # as an empty policy, not crash with AttributeError.
        result = classify(None, "bash", "rm -rf /")
        self.assertEqual(result.findings, [])

    def test_list_policy_does_not_crash(self):
        # A YAML file whose top level is a list must not crash.
        result = classify([], "bash", "rm -rf /")
        self.assertEqual(result.findings, [])

    def test_malformed_deny_entry_emits_warning(self):
        # A deny entry with a typo'd key (patern instead of pattern) must
        # not silently pass. The classifier emits a warning so the operator
        # sees the rule that does not load.
        policy = {"tools": {"bash": {"deny": [
            {"patern": "forbidden", "reason": "typo"}]}}}
        result = classify(policy, "bash", "forbidden command")
        self.assertTrue(any("unrecognized" in f.message for f in result.findings))
        # The malformed entry did not block, but the warning is visible
        self.assertTrue(any(f.level == "warn" for f in result.findings))

    def test_non_string_deny_entry_emits_warning(self):
        policy = {"tools": {"bash": {"deny": [42]}}}
        result = classify(policy, "bash", "anything")
        self.assertTrue(any("unrecognized" in f.message for f in result.findings))

    def test_valid_and_invalid_entries_coexist(self):
        # A valid deny entry alongside an invalid one: the valid one
        # still blocks, and the invalid one emits a warning.
        policy = {"tools": {"bash": {"deny": [
            "forbidden", {"patern": "typo"}]}}}
        result = classify(policy, "bash", "run forbidden now")
        self.assertFalse(result.ok)  # the valid entry blocked
        self.assertTrue(any("unrecognized" in f.message for f in result.findings))

    def test_string_deny_section_warns_and_ignores(self):
        # A deny section whose value is a string (not a list) must not
        # degenerate-match against single characters. The classifier
        # emits a warning and treats the section as empty.
        policy = {"tools": {"bash": {"deny": "rm -rf"}}}
        result = classify(policy, "bash", "rm -rf /")
        # The command is permitted (no valid deny list), but a warning
        # about the malformed section is present.
        self.assertTrue(result.ok)
        self.assertTrue(any("expected a list" in f.message for f in result.findings))

    def test_int_deny_section_warns_and_ignores(self):
        policy = {"tools": {"bash": {"deny": 42}}}
        result = classify(policy, "bash", "anything")
        self.assertTrue(result.ok)
        self.assertTrue(any("expected a list" in f.message for f in result.findings))

    def test_absent_section_is_silent(self):
        # A missing section (None) is the normal absent case: no warning.
        policy = {"tools": {"bash": {}}}
        result = classify(policy, "bash", "anything")
        self.assertEqual(result.findings, [])


class TestCheckCommandCli(unittest.TestCase):
    def _repo(self, temp_dir, policy_text=_POLICY):
        _write(temp_dir, os.path.join("policies", "command-policy.yaml"),
               policy_text)

    def test_deny_returns_exit_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "dotnet fable src"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("deny", completed.stderr)

    def test_warn_returns_exit_1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "rm -rf /tmp/x"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("warn", completed.stderr)

    def test_allowed_command_returns_exit_0(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "git status"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_string_entries_deny(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _POLICY_STRING_ENTRIES)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "rm -rf /"], temp_dir)
            self.assertEqual(completed.returncode, 2, completed.stderr)

    def test_empty_policy_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _POLICY_EMPTY)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "anything"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_missing_policy_fails_open(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "rm -rf /"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("cannot enforce", completed.stderr)

    def test_malformed_yaml_fails_open(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, _MALFORMED_YAML)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "rm -rf /"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("cannot enforce", completed.stderr)

    def test_bad_regex_fails_open(self):
        bad_regex = "tools:\n  bash:\n    deny: ['[unclosed']\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, bad_regex)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "anything"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("cannot enforce", completed.stderr)

    def test_empty_file_fails_open(self):
        # An empty command-policy.yaml loads as None; the classifier must
        # treat it as an empty policy, not crash with a traceback.
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, os.path.join("policies",
                                          "command-policy.yaml"), "")
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "rm -rf /"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_malformed_deny_entry_warns(self):
        # A deny entry with a typo'd key must emit a warning, not pass
        # silently. The command is permitted (exit 1, warn) but the
        # operator sees the unrecognized entry.
        typo_policy = (
            "tools:\n"
            "  bash:\n"
            "    deny:\n"
            "      - patern: 'dotnet\\s+fable'\n"
            "        reason: typo\n"
            "    warn: []\n"
            "    allow: []\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, typo_policy)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "dotnet fable"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("unrecognized", completed.stderr)

    def test_string_deny_section_warns(self):
        # A deny section whose value is a string (not a list) must emit
        # a warning and not degenerate-match against single characters.
        string_section_policy = (
            "tools:\n"
            "  bash:\n"
            "    deny: 'rm -rf'\n"
            "    warn: []\n"
            "    allow: []\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir, string_section_policy)
            completed = _run(["check-command", "--tool", "bash",
                              "--command", "rm -rf /"], temp_dir)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("expected a list", completed.stderr)

    def test_unknown_tool_allows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["check-command", "--tool", "node",
                              "--command", "rm -rf /"], temp_dir)
            self.assertEqual(completed.returncode, 0, completed.stderr)


class TestHookPreToolCommand(unittest.TestCase):
    _PATH_POLICY = (
        "may_edit: [src]\n"
        "ask_first: [deploy]\n"
        'never: ["*.render", .git]\n'
    )
    _COMMAND_POLICY = (
        "tools:\n"
        "  bash:\n"
        "    deny: ['dotnet\\s+fable']\n"
        "    warn: ['rm\\s+-rf']\n"
        "    allow: []\n"
    )

    def _repo(self, temp_dir):
        _write(temp_dir, os.path.join("policies", "path-policy.yaml"),
               self._PATH_POLICY)
        _write(temp_dir, os.path.join("policies", "command-policy.yaml"),
               self._COMMAND_POLICY)

    def _bash_payload(self, command):
        return json.dumps({"tool_name": "Bash",
                           "tool_input": {"command": command}})

    def test_denied_command_blocks_with_exit_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             self._bash_payload("dotnet fable"))
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("deny", completed.stderr)

    def test_warned_command_permits_with_trace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             self._bash_payload("rm -rf /tmp/x"))
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("warn", completed.stderr)

    def test_allowed_command_permits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            completed = _run(["hook-pre-tool"], temp_dir,
                             self._bash_payload("ls -la"))
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_path_check_still_works_for_edit_tools(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            payload = json.dumps({"tool_name": "Edit",
                                  "tool_input": {"file_path": "gen/x.render"}})
            completed = _run(["hook-pre-tool"], temp_dir, payload)
            self.assertEqual(completed.returncode, 2, completed.stderr)

    def test_missing_command_policy_fails_open(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write(temp_dir, os.path.join("policies", "path-policy.yaml"),
                   self._PATH_POLICY)
            completed = _run(["hook-pre-tool"], temp_dir,
                             self._bash_payload("rm -rf /"))
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_worst_code_wins_across_both_checks(self):
        # Both checks fire and return nonzero: a warned path (ask_first,
        # exit 1) plus a denied command (exit 2). max(1, 2) must pick the
        # block (exit 2). This is the genuinely new integration path that
        # proves the worst-code-wins logic.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            payload = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"file_path": "deploy/release.sh",
                               "command": "dotnet fable"}})
            completed = _run(["hook-pre-tool"], temp_dir, payload)
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("deny", completed.stderr)

    def test_warn_path_plus_warn_command_returns_exit_1(self):
        # Both checks warn: path ask_first (exit 1) plus a warn command
        # (exit 1). max(1, 1) = 1.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._repo(temp_dir)
            payload = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"file_path": "deploy/release.sh",
                               "command": "rm -rf /tmp/x"}})
            completed = _run(["hook-pre-tool"], temp_dir, payload)
            self.assertEqual(completed.returncode, 1, completed.stderr)


if __name__ == "__main__":
    unittest.main()
