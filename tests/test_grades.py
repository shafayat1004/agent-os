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
        result = CheckResult("state", "A-", [Finding("warn", "soft cap")])
        self.assertTrue(result.ok)

    def test_ok_false_with_error(self):
        result = CheckResult("state", "A-", [Finding("error", "missing field")])
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
