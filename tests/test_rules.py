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

    def test_missing_conventions_warns(self):
        import tempfile, os
        body = "\n".join("## %s\n- x" % s for s in
                         ["Commands", "Invariants", "Forbidden",
                          "Approval gates", "Scope"])
        fd, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(body)
            r = check_rules(path)
            self.assertTrue(any(f.level == "warn" and "Conventions" in f.message
                                for f in r.findings))
        finally:
            os.remove(path)

    def test_section_name_in_body_not_counted(self):
        import tempfile, os
        # Every required word appears in body text but there are no headings.
        body = "Commands Invariants Forbidden Approval gates Scope Conventions\n"
        fd, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(body)
            r = check_rules(path)
            missing = [f for f in r.findings if "missing section" in f.message]
            self.assertEqual(len(missing), 6)
        finally:
            os.remove(path)

    def test_out_of_order_warns(self):
        import tempfile, os
        order = ["Invariants", "Commands", "Forbidden", "Approval gates",
                 "Scope", "Conventions"]  # Commands and Invariants swapped
        body = "\n".join("## %s\n- x" % s for s in order)
        fd, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(body)
            r = check_rules(path)
            self.assertTrue(any("out of required order" in f.message
                                for f in r.findings))
        finally:
            os.remove(path)

    def test_missing_section_warns(self):
        r = check_rules("tests/fixtures/agents_ok.md", soft=1000, hard=2000)
        # agents_ok.md omits no required section, so force a missing one:
        r2 = check_rules("tests/fixtures/agents_big.md", soft=1000, hard=2000)
        self.assertTrue(any(f.level == "warn" for f in r2.findings))


if __name__ == "__main__":
    unittest.main()
