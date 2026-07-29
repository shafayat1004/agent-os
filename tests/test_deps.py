import unittest
import os
import tempfile
from agentos.checks.deps import check_deps

POLICY = "tests/fixtures/dep_policy.yaml"


class TestDeps(unittest.TestCase):
    def test_flags_moq(self):
        r = check_deps(POLICY, "tests/fixtures/depscan_dirty")
        self.assertFalse(r.ok)
        self.assertTrue(any("Moq" in f.message for f in r.findings))

    def test_clean_tree_passes(self):
        r = check_deps(POLICY, "tests/fixtures/depscan_clean")
        self.assertTrue(r.ok, [f.message for f in r.findings])

    def test_default_ignore_skips_vendored_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A banned dep inside node_modules must not be reported.
            nm = os.path.join(tmp, "node_modules", "pkg")
            os.makedirs(nm)
            with open(os.path.join(nm, "package.json"), "w") as fh:
                fh.write('{"dependencies": {"Moq": "1.0"}}')
            # A banned dep in owned source must still be reported.
            with open(os.path.join(tmp, "app.fsproj"), "w") as fh:
                fh.write('<PackageReference Include="AutoMapper" />')
            r = check_deps(POLICY, tmp)
            messages = [f.message for f in r.findings]
            self.assertTrue(any("AutoMapper" in m for m in messages))
            self.assertFalse(any("Moq" in m for m in messages))
            self.assertFalse(any("node_modules" in m for m in messages))

    def test_policy_ignore_extends_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            skipdir = os.path.join(tmp, "thirdparty")
            os.makedirs(skipdir)
            with open(os.path.join(skipdir, "package.json"), "w") as fh:
                fh.write('{"dependencies": {"Moq": "1.0"}}')
            policy = os.path.join(tmp, "dep-policy.yaml")
            with open(policy, "w") as fh:
                fh.write("banned:\n  - name: Moq\n    reason: x\n"
                         "ignore: [thirdparty]\n")
            r = check_deps(policy, tmp)
            self.assertTrue(r.ok, [f.message for f in r.findings])

    def test_deterministic_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            for sub in ("zdir", "adir"):
                subdir = os.path.join(tmp, sub)
                os.makedirs(subdir)
                with open(os.path.join(subdir, "package.json"), "w") as fh:
                    fh.write('{"dependencies": {"Moq": "1.0"}}')
            r1 = check_deps(POLICY, tmp)
            r2 = check_deps(POLICY, tmp)
            messages1 = [f.message for f in r1.findings]
            messages2 = [f.message for f in r2.findings]
            self.assertEqual(messages1, messages2)
            self.assertEqual(messages1, sorted(messages1))


if __name__ == "__main__":
    unittest.main()
