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
