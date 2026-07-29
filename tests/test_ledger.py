import unittest
from agentos.checks.ledger import check_ledger


class TestLedgerCheck(unittest.TestCase):
    def test_ok(self):
        r = check_ledger("tests/fixtures/ledger_ok.ndjson")
        self.assertTrue(r.ok, [f.message for f in r.findings])
        self.assertEqual(r.grade, "A")

    def test_bad_status_and_malformed_line(self):
        r = check_ledger("tests/fixtures/ledger_bad.ndjson")
        self.assertFalse(r.ok)
        self.assertTrue(any("line 2" in f.message for f in r.findings))


if __name__ == "__main__":
    unittest.main()
