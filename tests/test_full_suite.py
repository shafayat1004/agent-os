import unittest
import os


class TestDocsPresent(unittest.TestCase):
    def test_spec_and_roadmap_exist(self):
        self.assertTrue(os.path.exists("SPEC.md"))
        self.assertTrue(os.path.exists("ROADMAP.md"))

    def test_spec_has_no_em_dash(self):
        for name in ("SPEC.md", "ROADMAP.md"):
            with open(name, encoding="utf-8") as fh:
                self.assertNotIn("—", fh.read(), "%s has an em-dash" % name)


if __name__ == "__main__":
    unittest.main()
