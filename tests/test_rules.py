import os
import tempfile
import unittest
from agentos.checks.rules import check_rules


class TestRules(unittest.TestCase):
    def test_ok(self):
        result = check_rules("tests/fixtures/agents_ok.md")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])
        self.assertEqual(result.grade, "A-")

    def test_big_file_errors(self):
        result = check_rules("tests/fixtures/agents_big.md", soft=3, hard=5)
        self.assertFalse(result.ok)

    def test_missing_conventions_warns(self):
        body = "\n".join("## %s\n- x" % section for section in
                         ["Commands", "Invariants", "Forbidden",
                          "Approval gates", "Scope"])
        file_descriptor, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(file_descriptor, "w") as handle:
                handle.write(body)
            result = check_rules(path)
            self.assertTrue(any(finding.level == "warn" and "Conventions" in finding.message
                                for finding in result.findings))
        finally:
            os.remove(path)

    def test_section_name_in_body_not_counted(self):
        # Every required word appears in body text but there are no headings.
        body = "Commands Invariants Forbidden Approval gates Scope Conventions\n"
        file_descriptor, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(file_descriptor, "w") as handle:
                handle.write(body)
            result = check_rules(path)
            missing_findings = [finding for finding in result.findings
                                if "missing section" in finding.message]
            self.assertEqual(len(missing_findings), 6)
        finally:
            os.remove(path)

    def test_out_of_order_warns(self):
        section_order = ["Invariants", "Commands", "Forbidden", "Approval gates",
                         "Scope", "Conventions"]  # Commands and Invariants swapped
        body = "\n".join("## %s\n- x" % section for section in section_order)
        file_descriptor, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(file_descriptor, "w") as handle:
                handle.write(body)
            result = check_rules(path)
            self.assertTrue(any("out of required order" in finding.message
                                for finding in result.findings))
        finally:
            os.remove(path)

    def test_missing_section_warns(self):
        # agents_ok.md omits no required section, so use a file that does:
        big_file_result = check_rules("tests/fixtures/agents_big.md",
                                      soft=1000, hard=2000)
        self.assertTrue(any(finding.level == "warn"
                            for finding in big_file_result.findings))


if __name__ == "__main__":
    unittest.main()
