import unittest
from agentos.checks.skills import check_skills


class TestSkills(unittest.TestCase):
    def test_ok(self):
        r = check_skills("tests/fixtures/skills_index_ok.yaml",
                         "tests/fixtures/skills_dir")
        self.assertTrue(r.ok, [f.message for f in r.findings])
        self.assertEqual(r.grade, "B")

    def test_missing_entry_warns(self):
        r = check_skills("tests/fixtures/skills_index_empty.yaml",
                         "tests/fixtures/skills_dir")
        self.assertTrue(r.ok)  # warn only
        self.assertTrue(any("demo" in f.message and f.level == "warn"
                            for f in r.findings))

    def test_bad_version_errors(self):
        r = check_skills("tests/fixtures/skills_index_badver.yaml",
                         "tests/fixtures/skills_dir")
        self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()
