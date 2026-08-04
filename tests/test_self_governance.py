import json
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
        for relative in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "STATE.yaml",
                         os.path.join("evidence", "ledger.ndjson"),
                         os.path.join("policies", "path-policy.yaml"),
                         os.path.join("policies", "dependency-policy.yaml"),
                         os.path.join("skills", "index.yaml"),
                         os.path.join(".claude", "settings.json"),
                         os.path.join(".opencode", "plugins", "agentos.js"),
                         os.path.join(".github", "copilot-instructions.md"),
                         "VERSION"):
            self.assertTrue(os.path.exists(os.path.join(_ROOT, relative)),
                            relative)

    def _ref_is_main(self):
        """True when the checked-out ref is main.

        CI sets AGENTOS_REF_IS_MAIN explicitly because a CI checkout is a
        detached HEAD, where the branch name is unavailable. Local runs
        fall back to the current branch name.
        """
        env = os.environ.get("AGENTOS_REF_IS_MAIN")
        if env is not None:
            return env == "1"
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                cwd=_ROOT, capture_output=True, text=True)
        return result.stdout.strip() == "main"

    def test_repo_passes_its_own_validator(self):
        completed = subprocess.run([_AGENTOS, "all"], cwd=_ROOT,
                                   capture_output=True, text=True)
        if completed.returncode == 0:
            return
        # On main the gate must be fully green: a merged/released state has
        # no excuse for a red self-check. The mid-task exemption below is
        # for feature branches only.
        if self._ref_is_main():
            self.fail("agentos all must pass fully on main:\n"
                      + completed.stdout + completed.stderr)
        # Feature branch: non-zero exit is acceptable only when
        # stop_readiness is blocked (mid-task). In that state, uncovered
        # criteria correctly make the ledger check fail. Every other check
        # must still pass.
        state_path = os.path.join(_ROOT, "STATE.yaml")
        with open(state_path) as handle:
            state_content = handle.read()
        if "stop_readiness: blocked" not in state_content:
            self.fail(completed.stdout + completed.stderr)
        json_run = subprocess.run([_AGENTOS, "--json", "all"], cwd=_ROOT,
                                  capture_output=True, text=True)
        results = json.loads(json_run.stdout)
        for result in results:
            if result["name"] != "ledger" and not result["ok"]:
                self.fail("non-ledger check failed while blocked: %s\n%s"
                          % (result["name"], completed.stdout))

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
