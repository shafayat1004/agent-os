import os
import shutil
import subprocess
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTOS = os.path.join(_ROOT, "bin", "agentos")


class TestSelfGovernance(unittest.TestCase):
    """The self-compile gate. agent-os must pass its own validator on its
    own repo, and a fresh init destination must pass it too. A framework
    that cannot govern its own codebase governs nothing."""

    def test_repo_artifacts_exist(self):
        for relative in ("AGENTS.md", "CLAUDE.md", "STATE.yaml",
                         os.path.join("evidence", "ledger.ndjson"),
                         os.path.join("policies", "path-policy.yaml"),
                         os.path.join("policies", "dependency-policy.yaml"),
                         os.path.join("skills", "index.yaml"),
                         os.path.join(".claude", "settings.json")):
            self.assertTrue(os.path.exists(os.path.join(_ROOT, relative)),
                            relative)

    def test_repo_passes_its_own_validator(self):
        completed = subprocess.run([_AGENTOS, "all"], cwd=_ROOT,
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_fresh_init_destination_passes_validator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(["git", "init", "-q", temp_dir], check=True)
            init_run = subprocess.run([_AGENTOS, "init", temp_dir],
                                      capture_output=True, text=True)
            self.assertEqual(init_run.returncode, 0, init_run.stderr)
            all_run = subprocess.run([_AGENTOS, "all"], cwd=temp_dir,
                                     capture_output=True, text=True)
            self.assertEqual(all_run.returncode, 0,
                             all_run.stdout + all_run.stderr)


if __name__ == "__main__":
    unittest.main()
