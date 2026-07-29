import os
import tempfile
import unittest
from agentos.checks.skills import check_skills


class TestSkills(unittest.TestCase):
    def test_ok(self):
        result = check_skills("tests/fixtures/skills_index_ok.yaml",
                              "tests/fixtures/skills_dir")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])
        self.assertEqual(result.grade, "B")

    def test_missing_entry_warns(self):
        result = check_skills("tests/fixtures/skills_index_empty.yaml",
                              "tests/fixtures/skills_dir")
        self.assertTrue(result.ok)  # warn only
        self.assertTrue(any("demo" in finding.message and finding.level == "warn"
                            for finding in result.findings))

    def test_bad_version_errors(self):
        result = check_skills("tests/fixtures/skills_index_badver.yaml",
                              "tests/fixtures/skills_dir")
        self.assertFalse(result.ok)

    def test_malformed_index_errors(self):
        # The index is the artifact under lint, so unparseable content is a
        # violation (error finding), not a crash.
        file_descriptor, path = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(file_descriptor, "w") as handle:
                handle.write("skills: |\n  block literal not in subset\n")
            result = check_skills(path, "tests/fixtures/skills_dir")
            self.assertFalse(result.ok)
            self.assertTrue(any("cannot load" in finding.message
                                for finding in result.findings))
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
