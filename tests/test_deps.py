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


if __name__ == "__main__":
    unittest.main()
