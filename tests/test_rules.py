import unittest
from agentos.checks.rules import check_rules


class TestRules(unittest.TestCase):
    def test_ok(self):
        r = check_rules("tests/fixtures/agents_ok.md")
        self.assertTrue(r.ok, [f.message for f in r.findings])
        self.assertEqual(r.grade, "A-")

    def test_big_file_errors(self):
        r = check_rules("tests/fixtures/agents_big.md", soft=3, hard=5)
        self.assertFalse(r.ok)

    def test_missing_section_warns(self):
        r = check_rules("tests/fixtures/agents_ok.md", soft=1000, hard=2000)
        # agents_ok.md omits no required section, so force a missing one:
        r2 = check_rules("tests/fixtures/agents_big.md", soft=1000, hard=2000)
        self.assertTrue(any(f.level == "warn" for f in r2.findings))


if __name__ == "__main__":
    unittest.main()
