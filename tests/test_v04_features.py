"""Tests for agentos upgrade, doctor, custom checks, and version."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from agentos.cli import main
from agentos.version import release_version, schema_versions, adapter_protocol
from agentos.checks.custom import check_custom

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTOS = os.path.join(_ROOT, "bin", "agentos")


class TestVersion(unittest.TestCase):
    def test_release_version_reads_file(self):
        v = release_version(_ROOT)
        self.assertTrue(v)  # non-empty
        self.assertIn(".", v)  # looks like semver

    def test_schema_versions_all_present(self):
        sv = schema_versions(_ROOT)
        self.assertIn("evidence", sv)
        self.assertIn("skill", sv)
        self.assertIn("task-state", sv)
        for key, val in sv.items():
            self.assertIsInstance(val, int, "%s version is not int" % key)

    def test_adapter_protocol_is_integer(self):
        ap = adapter_protocol()
        self.assertIsInstance(ap, int)

    def test_cli_version_flag(self):
        completed = subprocess.run(
            [_AGENTOS, "--version"], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0)
        self.assertIn("0.4.0", completed.stdout)
        self.assertIn("adapter protocol", completed.stdout)


class TestDoctor(unittest.TestCase):
    def test_doctor_on_self_host_repo(self):
        completed = subprocess.run(
            [_AGENTOS, "doctor"], cwd=_ROOT,
            capture_output=True, text=True)
        # The agent-os repo self-hosts; doctor should pass
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)
        self.assertIn("runtime", completed.stdout)
        self.assertIn("Claude Code", completed.stdout)

    def test_doctor_on_fresh_init(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            subprocess.run([_AGENTOS, "init", td], capture_output=True,
                           text=True)
            vendored = os.path.join(td, ".agent-os", "bin", "agentos")
            completed = subprocess.run(
                [vendored, "doctor"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stdout + completed.stderr)
            self.assertIn("vendored", completed.stdout)
            self.assertIn("core.hooksPath", completed.stdout)


class TestUpgrade(unittest.TestCase):
    def test_upgrade_check_no_vendor(self):
        with tempfile.TemporaryDirectory() as td:
            completed = subprocess.run(
                [_AGENTOS, "upgrade", "--check", td],
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertIn("no vendored runtime", completed.stdout)

    def test_upgrade_check_with_vendor_no_releases(self):
        # No releases exist yet, so the API returns 404.
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([_AGENTOS, "init", td], capture_output=True,
                           text=True)
            vendored = os.path.join(td, ".agent-os", "bin", "agentos")
            completed = subprocess.run(
                [vendored, "upgrade", "--check"], cwd=td,
                capture_output=True, text=True)
            # 404 is expected when no releases exist
            self.assertEqual(completed.returncode, 2)
            self.assertIn("cannot fetch", completed.stdout)


class TestCustomChecks(unittest.TestCase):
    def test_no_policy_file_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            result = check_custom(os.path.join(td, "custom-checks.yaml"),
                                  root=td)
            self.assertTrue(result.ok)

    def test_empty_checks_list_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "custom-checks.yaml")
            with open(path, "w") as f:
                f.write("checks: []\n")
            result = check_custom(path, root=td)
            self.assertTrue(result.ok)

    def test_passing_check(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "custom-checks.yaml")
            with open(path, "w") as f:
                f.write("checks:\n"
                        "  - name: true-check\n"
                        "    command: 'true'\n"
                        "    on_fail: error\n")
            result = check_custom(path, root=td)
            self.assertTrue(result.ok)

    def test_failing_check_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "custom-checks.yaml")
            with open(path, "w") as f:
                f.write("checks:\n"
                        "  - name: false-check\n"
                        "    command: 'false'\n"
                        "    on_fail: error\n")
            result = check_custom(path, root=td)
            self.assertFalse(result.ok)

    def test_warn_check_does_not_block(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "custom-checks.yaml")
            with open(path, "w") as f:
                f.write("checks:\n"
                        "  - name: false-check\n"
                        "    command: 'false'\n"
                        "    on_fail: warn\n")
            result = check_custom(path, root=td)
            self.assertTrue(result.ok)

    def test_custom_checks_in_agentos_all(self):
        """agentos all includes the custom check in its output."""
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            subprocess.run([_AGENTOS, "init", td], capture_output=True,
                           text=True)
            # Add a custom check
            policy_path = os.path.join(td, "policies", "custom-checks.yaml")
            with open(policy_path, "w") as f:
                f.write("checks:\n"
                        "  - name: always-pass\n"
                        "    command: 'true'\n"
                        "    on_fail: error\n")
            vendored = os.path.join(td, ".agent-os", "bin", "agentos")
            completed = subprocess.run(
                [vendored, "all"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stdout + completed.stderr)
            self.assertIn("custom", completed.stdout)


class TestExtensionDirs(unittest.TestCase):
    def test_extension_script_runs(self):
        """A script in stop.d/ runs after the built-in stop check."""
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            subprocess.run([_AGENTOS, "init", td], capture_output=True,
                           text=True)
            # Add a stop.d script that writes a marker file
            ext_dir = os.path.join(td, ".agent-os", "hooks", "stop.d")
            marker_script = os.path.join(ext_dir, "marker.sh")
            with open(marker_script, "w") as f:
                f.write("#!/bin/sh\necho 'extension ran' > %s/marker.txt\n" % td)
            os.chmod(marker_script, 0o755)
            # Run the stop wrapper
            stop_wrapper = os.path.join(td, ".claude", "hooks",
                                        "agentos-stop-check")
            subprocess.run([stop_wrapper], cwd=td,
                           capture_output=True, text=True)
            # The marker file should exist
            self.assertTrue(os.path.exists(os.path.join(td, "marker.txt")))


if __name__ == "__main__":
    unittest.main()
