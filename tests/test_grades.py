import unittest
from agentos.grades import grade_for
from agentos.result import Finding, CheckResult


class TestGrades(unittest.TestCase):
    def test_known_grades(self):
        self.assertEqual(grade_for("ledger"), "A")
        self.assertEqual(grade_for("state"), "A-")
        self.assertEqual(grade_for("deps"), "B+")

    def test_unknown_grade_raises(self):
        with self.assertRaises(KeyError):
            grade_for("nope")


class TestResult(unittest.TestCase):
    def test_ok_true_with_only_warnings(self):
        r = CheckResult("state", "A-", [Finding("warn", "soft cap")])
        self.assertTrue(r.ok)

    def test_ok_false_with_error(self):
        r = CheckResult("state", "A-", [Finding("error", "missing field")])
        self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()
