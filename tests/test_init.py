import io
import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from agentos.initcmd import run_init
from agentos.cli import main

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestInit(unittest.TestCase):
    def test_writes_artifacts_pointer_and_wrappers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "AGENTS.md")))
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "STATE.yaml")))
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "CLAUDE.md")))
            pre_tool_hook = os.path.join(temp_dir, ".claude", "hooks", "agentos-pre-tool")
            self.assertTrue(os.path.exists(pre_tool_hook))
            self.assertTrue(os.access(pre_tool_hook, os.X_OK))

    def test_pointer_names_agents_md(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            with open(os.path.join(temp_dir, "CLAUDE.md")) as pointer_file:
                self.assertIn("AGENTS.md", pointer_file.read())

    def test_installs_pre_commit_when_git_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, ".git", "hooks"))
            run_init(temp_dir, _ROOT)
            hook_path = os.path.join(temp_dir, ".git", "hooks", "pre-commit")
            self.assertTrue(os.path.exists(hook_path))
            self.assertTrue(os.access(hook_path, os.X_OK))
            with open(hook_path) as hook_file:
                hook_body = hook_file.read()
            self.assertIn("diff --staged", hook_body)
            self.assertIn(os.path.join(_ROOT, "bin", "agentos"), hook_body)

    def test_skips_pre_commit_without_git(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            self.assertFalse(
                os.path.exists(os.path.join(temp_dir, ".git", "hooks", "pre-commit")))

    def test_non_destructive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "CLAUDE.md"), "w") as pointer_file:
                pointer_file.write("keep me")
            run_init(temp_dir, _ROOT)
            with open(os.path.join(temp_dir, "CLAUDE.md")) as pointer_file:
                self.assertEqual(pointer_file.read(), "keep me")

    def test_settings_snippet_is_valid_json_with_hooks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_init(temp_dir, _ROOT)
            parsed_settings = json.loads(summary["settings_snippet"])
            self.assertIn("PreToolUse", parsed_settings["hooks"])
            self.assertIn("Stop", parsed_settings["hooks"])

    def test_dest_is_file_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "afile")
            with open(file_path, "w") as output_file:
                output_file.write("x")
            with self.assertRaises(OSError):
                run_init(file_path, _ROOT)

    def test_cli_init_exit_zero_and_bootstraps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            captured_output = io.StringIO()
            with contextlib.redirect_stdout(captured_output):
                code = main(["init", temp_dir])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "AGENTS.md")))
            self.assertIn("PreToolUse", captured_output.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_installed_pre_commit_runs(self):
        # The generated hook must actually invoke real validator subcommands.
        # With nothing staged and no banned deps, it exits 0.
        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(["git", "init", "-q", temp_dir], check=True)
            run_init(temp_dir, _ROOT)
            hook_path = os.path.join(temp_dir, ".git", "hooks", "pre-commit")
            completed = subprocess.run([hook_path], cwd=temp_dir,
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
