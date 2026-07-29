import unittest
from agentos.checks.ledger import check_ledger


class TestLedgerCheck(unittest.TestCase):
    def test_ok(self):
        result = check_ledger("tests/fixtures/ledger_ok.ndjson")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])
        self.assertEqual(result.grade, "A")

    def test_bad_status_and_malformed_line(self):
        result = check_ledger("tests/fixtures/ledger_bad.ndjson")
        self.assertFalse(result.ok)
        self.assertTrue(any("line 2" in finding.message for finding in result.findings))


if __name__ == "__main__":
    unittest.main()
