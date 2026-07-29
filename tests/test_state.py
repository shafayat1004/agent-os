import unittest
from agentos.checks.state import check_state


class TestStateCheck(unittest.TestCase):
    def test_ok_fixture_passes(self):
        result = check_state("tests/fixtures/state_ok.yaml")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])
        self.assertEqual(result.grade, "A-")

    def test_bad_fixture_fails(self):
        result = check_state("tests/fixtures/state_bad.yaml")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
