import unittest
import os


class TestDocsPresent(unittest.TestCase):
    def test_spec_and_roadmap_exist(self):
        self.assertTrue(os.path.exists("SPEC.md"))
        self.assertTrue(os.path.exists("ROADMAP.md"))

    def test_spec_has_no_em_dash(self):
        for doc_name in ("SPEC.md", "ROADMAP.md"):
            with open(doc_name, encoding="utf-8") as doc_file:
                self.assertNotIn("—", doc_file.read(), "%s has an em-dash" % doc_name)


if __name__ == "__main__":
    unittest.main()
