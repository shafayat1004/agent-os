"""Tests for agentos upgrade, doctor, custom checks, and version."""
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from agentos.cli import main
from agentos.version import release_version, schema_versions, adapter_protocol
from agentos.checks.custom import check_custom
from agentos.upgrade import run_upgrade, _extract_runtime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTOS = os.path.join(_ROOT, "bin", "agentos")


def _init_repo(target_dir):
    """git init + agentos init a fresh repo. Return the vendored bin path."""
    subprocess.run(["git", "init", "-q", target_dir], check=True)
    subprocess.run([_AGENTOS, "init", target_dir],
                   capture_output=True, text=True)
    return os.path.join(target_dir, ".agent-os", "bin", "agentos")


def _make_runtime_tarball(dest_tarball, version):
    """Build a minimal release tarball (bin/, agentos/, schemas/, VERSION)."""
    with tempfile.TemporaryDirectory() as src:
        os.makedirs(os.path.join(src, "bin"))
        with open(os.path.join(src, "bin", "agentos"), "w") as handle:
            handle.write("#!/bin/sh\n# new runtime\n")
        os.makedirs(os.path.join(src, "agentos"))
        with open(os.path.join(src, "agentos", "__init__.py"), "w") as handle:
            handle.write("# new package\n")
        os.makedirs(os.path.join(src, "schemas"))
        with open(os.path.join(src, "schemas", "s.json"), "w") as handle:
            handle.write("{}\n")
        with open(os.path.join(src, "VERSION"), "w") as handle:
            handle.write(version + "\n")
        with tarfile.open(dest_tarball, "w:gz") as tar:
            tar.add(src, arcname=".")


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
        # Assert against the VERSION file, not a hardcoded string, so a
        # release bump does not silently break this test.
        expected = release_version(_ROOT)
        completed = subprocess.run(
            [_AGENTOS, "--version"], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0)
        self.assertIn(expected, completed.stdout)
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
        self.assertIn("All checks passed", completed.stdout)

    def test_doctor_on_fresh_init(self):
        with tempfile.TemporaryDirectory() as td:
            vendored = _init_repo(td)
            completed = subprocess.run(
                [vendored, "doctor"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stdout + completed.stderr)
            self.assertIn("vendored", completed.stdout)
            self.assertIn("core.hooksPath", completed.stdout)
            self.assertIn("All checks passed", completed.stdout)

    def test_doctor_fails_when_settings_missing(self):
        # Doctor's reason to exist is catching broken wiring. Remove the
        # Claude Code hook registration and it must report exit 1, not 0.
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            os.remove(os.path.join(td, ".claude", "settings.json"))
            completed = subprocess.run(
                [_AGENTOS, "doctor"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 1,
                             completed.stdout + completed.stderr)
            self.assertIn("MISSING", completed.stdout)
            self.assertIn("Some checks failed", completed.stdout)

    def test_doctor_fails_when_runtime_missing(self):
        # No vendored .agent-os/ and no self-hosted bin/ means the runtime
        # is unwired; doctor must fail.
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            shutil.rmtree(os.path.join(td, ".agent-os"))
            completed = subprocess.run(
                [_AGENTOS, "doctor"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 1,
                             completed.stdout + completed.stderr)
            self.assertIn("bin/agentos: MISSING", completed.stdout)
            self.assertIn("Some checks failed", completed.stdout)


class TestUpgrade(unittest.TestCase):
    def test_upgrade_check_no_vendor(self):
        with tempfile.TemporaryDirectory() as td:
            completed = subprocess.run(
                [_AGENTOS, "upgrade", "--check", td],
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertIn("no vendored runtime", completed.stdout)

    def test_check_reports_error_when_api_unreachable(self):
        # Network failure during --check is reported, not crashed. Stubbed
        # so the test is hermetic and does not depend on whether a release
        # exists (the old 404 test broke the moment 0.4.0 was tagged).
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            with mock.patch("agentos.upgrade._latest_release",
                            side_effect=OSError("no network")):
                result = run_upgrade(td, check_only=True)
            self.assertEqual(result["action"], "error")
            self.assertIn("cannot fetch", result["message"])

    def test_check_reports_up_to_date(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            local = release_version(_ROOT)
            with mock.patch("agentos.upgrade._latest_release",
                            return_value=("v" + local, "url")):
                result = run_upgrade(td, check_only=True)
            self.assertEqual(result["action"], "check")
            self.assertIn("up to date", result["message"])

    def test_check_reports_update_available(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            with mock.patch("agentos.upgrade._latest_release",
                            return_value=("v999.0.0", "url")):
                result = run_upgrade(td, check_only=True)
            self.assertEqual(result["action"], "check")
            self.assertIn("update available", result["message"])

    def test_extract_replaces_runtime_and_preserves_extensions(self):
        # The core of upgrade: runtime files are replaced, user-owned
        # extension scripts under hooks/*.d are preserved.
        with tempfile.TemporaryDirectory() as td:
            vendor = os.path.join(td, ".agent-os")
            os.makedirs(os.path.join(vendor, "bin"))
            with open(os.path.join(vendor, "bin", "agentos"), "w") as handle:
                handle.write("old runtime\n")
            with open(os.path.join(vendor, "VERSION"), "w") as handle:
                handle.write("0.0.1\n")
            # A user extension script that must survive the upgrade.
            ext_dir = os.path.join(vendor, "hooks", "stop.d")
            os.makedirs(ext_dir)
            ext_script = os.path.join(ext_dir, "my-check.sh")
            with open(ext_script, "w") as handle:
                handle.write("#!/bin/sh\necho mine\n")

            tarball = os.path.join(td, "release.tar.gz")
            _make_runtime_tarball(tarball, "9.9.9")
            _extract_runtime(tarball, vendor, lambda action, path: None)

            # Runtime replaced.
            with open(os.path.join(vendor, "VERSION")) as handle:
                self.assertEqual(handle.read().strip(), "9.9.9")
            with open(os.path.join(vendor, "bin", "agentos")) as handle:
                self.assertIn("new runtime", handle.read())
            # Extension preserved untouched.
            self.assertTrue(os.path.exists(ext_script))
            with open(ext_script) as handle:
                self.assertIn("echo mine", handle.read())

    def test_upgrade_happy_path_replaces_runtime(self):
        # End-to-end run_upgrade with the network stubbed: it downloads
        # (fed a local tarball), extracts, and reports the new version.
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            tarball = os.path.join(td, "release.tar.gz")
            _make_runtime_tarball(tarball, "9.9.9")

            def fake_download(tag, dest_path):
                shutil.copy(tarball, dest_path)

            with mock.patch("agentos.upgrade._latest_release",
                            return_value=("v9.9.9", "url")), \
                    mock.patch("agentos.upgrade._download_tarball",
                               side_effect=fake_download):
                result = run_upgrade(td)

            self.assertEqual(result["action"], "upgraded", result["message"])
            self.assertEqual(result["upgraded_to"], "9.9.9")
            with open(os.path.join(td, ".agent-os", "VERSION")) as handle:
                self.assertEqual(handle.read().strip(), "9.9.9")

    def test_upgrade_preserves_user_files(self):
        # User-owned files outside the vendored runtime are never touched.
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            state_path = os.path.join(td, "STATE.yaml")
            with open(state_path, "w") as handle:
                handle.write("task_id: keep-me\n")
            tarball = os.path.join(td, "release.tar.gz")
            _make_runtime_tarball(tarball, "9.9.9")

            def fake_download(tag, dest_path):
                shutil.copy(tarball, dest_path)

            with mock.patch("agentos.upgrade._latest_release",
                            return_value=("v9.9.9", "url")), \
                    mock.patch("agentos.upgrade._download_tarball",
                               side_effect=fake_download):
                run_upgrade(td)

            with open(state_path) as handle:
                self.assertIn("keep-me", handle.read())


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

    def _write_custom_policy(self, td, body):
        policy_path = os.path.join(td, "policies", "custom-checks.yaml")
        with open(policy_path, "w") as f:
            f.write(body)

    def test_custom_checks_in_agentos_all(self):
        """agentos all runs the named custom check and reports its result."""
        with tempfile.TemporaryDirectory() as td:
            vendored = _init_repo(td)
            self._write_custom_policy(
                td,
                "checks:\n"
                "  - name: always-pass\n"
                "    command: 'true'\n"
                "    on_fail: error\n")
            completed = subprocess.run(
                [vendored, "all"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stdout + completed.stderr)
            # Assert the named check actually ran, not merely that the
            # "custom" section header (a constant) was printed.
            self.assertIn("always-pass", completed.stdout)

    def test_failing_error_custom_check_blocks_all(self):
        # The headline #38 behavior: an on_fail: error custom check flips
        # `agentos all` to a blocking exit code, end to end through the CLI.
        with tempfile.TemporaryDirectory() as td:
            vendored = _init_repo(td)
            self._write_custom_policy(
                td,
                "checks:\n"
                "  - name: must-fail\n"
                "    command: 'false'\n"
                "    on_fail: error\n")
            completed = subprocess.run(
                [vendored, "all"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 1,
                             completed.stdout + completed.stderr)
            self.assertIn("must-fail", completed.stdout)

    def test_warn_custom_check_does_not_block_all(self):
        # A warn-level failure reports but keeps the gate green (exit 0).
        with tempfile.TemporaryDirectory() as td:
            vendored = _init_repo(td)
            self._write_custom_policy(
                td,
                "checks:\n"
                "  - name: soft-fail\n"
                "    command: 'false'\n"
                "    on_fail: warn\n")
            completed = subprocess.run(
                [vendored, "all"], cwd=td,
                capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stdout + completed.stderr)
            self.assertIn("soft-fail", completed.stdout)


class TestExtensionDirs(unittest.TestCase):
    def test_extension_script_runs(self):
        """A script in stop.d/ runs after the built-in stop check."""
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
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
