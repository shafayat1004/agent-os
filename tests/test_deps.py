import unittest
import os
import tempfile
from agentos.checks.deps import check_deps

POLICY = "tests/fixtures/dep_policy.yaml"


class TestDeps(unittest.TestCase):
    def test_flags_moq(self):
        result = check_deps(POLICY, "tests/fixtures/depscan_dirty")
        self.assertFalse(result.ok)
        self.assertTrue(any("Moq" in finding.message for finding in result.findings))

    def test_clean_tree_passes(self):
        result = check_deps(POLICY, "tests/fixtures/depscan_clean")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_default_ignore_skips_vendored_manifests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # A banned dep inside node_modules must not be reported.
            vendored_pkg_dir = os.path.join(temp_dir, "node_modules", "pkg")
            os.makedirs(vendored_pkg_dir)
            with open(os.path.join(vendored_pkg_dir, "package.json"), "w") as manifest:
                manifest.write('{"dependencies": {"Moq": "1.0"}}')
            # A banned dep in owned source must still be reported.
            with open(os.path.join(temp_dir, "app.fsproj"), "w") as manifest:
                manifest.write('<PackageReference Include="AutoMapper" />')
            result = check_deps(POLICY, temp_dir)
            messages = [finding.message for finding in result.findings]
            self.assertTrue(any("AutoMapper" in message for message in messages))
            self.assertFalse(any("Moq" in message for message in messages))
            self.assertFalse(any("node_modules" in message for message in messages))

    def test_policy_ignore_extends_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skipped_dir = os.path.join(temp_dir, "thirdparty")
            os.makedirs(skipped_dir)
            with open(os.path.join(skipped_dir, "package.json"), "w") as manifest:
                manifest.write('{"dependencies": {"Moq": "1.0"}}')
            policy_path = os.path.join(temp_dir, "dep-policy.yaml")
            with open(policy_path, "w") as policy_file:
                policy_file.write("banned:\n  - name: Moq\n    reason: x\n"
                                  "ignore: [thirdparty]\n")
            result = check_deps(policy_path, temp_dir)
            self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_deterministic_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for subdir_name in ("zdir", "adir"):
                subdir = os.path.join(temp_dir, subdir_name)
                os.makedirs(subdir)
                with open(os.path.join(subdir, "package.json"), "w") as manifest:
                    manifest.write('{"dependencies": {"Moq": "1.0"}}')
            first_result = check_deps(POLICY, temp_dir)
            second_result = check_deps(POLICY, temp_dir)
            first_messages = [finding.message for finding in first_result.findings]
            second_messages = [finding.message for finding in second_result.findings]
            self.assertEqual(first_messages, second_messages)
            self.assertEqual(first_messages, sorted(first_messages))


if __name__ == "__main__":
    unittest.main()
