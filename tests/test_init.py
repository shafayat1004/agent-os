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
        with tempfile.TemporaryDirectory() as d:
            run_init(d, _ROOT)
            self.assertTrue(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertTrue(os.path.exists(os.path.join(d, "STATE.yaml")))
            self.assertTrue(os.path.exists(os.path.join(d, "CLAUDE.md")))
            pre_tool = os.path.join(d, ".claude", "hooks", "agentos-pre-tool")
            self.assertTrue(os.path.exists(pre_tool))
            self.assertTrue(os.access(pre_tool, os.X_OK))

    def test_pointer_names_agents_md(self):
        with tempfile.TemporaryDirectory() as d:
            run_init(d, _ROOT)
            with open(os.path.join(d, "CLAUDE.md")) as fh:
                self.assertIn("AGENTS.md", fh.read())

    def test_installs_pre_commit_when_git_present(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".git", "hooks"))
            run_init(d, _ROOT)
            hook = os.path.join(d, ".git", "hooks", "pre-commit")
            self.assertTrue(os.path.exists(hook))
            self.assertTrue(os.access(hook, os.X_OK))
            with open(hook) as fh:
                body = fh.read()
            self.assertIn("diff --staged", body)
            self.assertIn(os.path.join(_ROOT, "bin", "agentos"), body)

    def test_skips_pre_commit_without_git(self):
        with tempfile.TemporaryDirectory() as d:
            run_init(d, _ROOT)
            self.assertFalse(
                os.path.exists(os.path.join(d, ".git", "hooks", "pre-commit")))

    def test_non_destructive(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "CLAUDE.md"), "w") as fh:
                fh.write("keep me")
            run_init(d, _ROOT)
            with open(os.path.join(d, "CLAUDE.md")) as fh:
                self.assertEqual(fh.read(), "keep me")

    def test_settings_snippet_is_valid_json_with_hooks(self):
        with tempfile.TemporaryDirectory() as d:
            summary = run_init(d, _ROOT)
            parsed = json.loads(summary["settings_snippet"])
            self.assertIn("PreToolUse", parsed["hooks"])
            self.assertIn("Stop", parsed["hooks"])

    def test_dest_is_file_errors(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "afile")
            with open(f, "w") as fh:
                fh.write("x")
            with self.assertRaises(OSError):
                run_init(f, _ROOT)

    def test_cli_init_exit_zero_and_bootstraps(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["init", d])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertIn("PreToolUse", buf.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_installed_pre_commit_runs(self):
        # The generated hook must actually invoke real validator subcommands.
        # With nothing staged and no banned deps, it exits 0.
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            run_init(d, _ROOT)
            hook = os.path.join(d, ".git", "hooks", "pre-commit")
            r = subprocess.run([hook], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
