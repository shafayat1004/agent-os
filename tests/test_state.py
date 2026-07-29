import unittest
from agentos.checks.state import check_state


class TestStateCheck(unittest.TestCase):
    def test_ok_fixture_passes(self):
        r = check_state("tests/fixtures/state_ok.yaml")
        self.assertTrue(r.ok, [f.message for f in r.findings])
        self.assertEqual(r.grade, "A-")

    def test_bad_fixture_fails(self):
        r = check_state("tests/fixtures/state_bad.yaml")
        self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()
