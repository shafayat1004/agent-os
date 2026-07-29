import unittest
from agentos.checks.state import check_state
from agentos.checks.rules import check_rules
from agentos.checks.diff import check_diff


class TestExampleSubject(unittest.TestCase):
    def test_state_valid(self):
        r = check_state("examples/subject/STATE.yaml")
        self.assertTrue(r.ok, [f.message for f in r.findings])

    def test_rules_valid(self):
        r = check_rules("examples/subject/AGENTS.md")
        self.assertTrue(r.ok, [f.message for f in r.findings])

    def test_policy_blocks_app_and_autogen(self):
        r = check_diff("examples/subject/policies/path-policy.yaml",
                       ["AppEggShellGallery/x.fs", "LibClient/x.render",
                        "LibClient/src/ok.fs"])
        # LibClient/x.render -> error (never); App* -> warn; LibClient ok -> none
        self.assertFalse(r.ok)
        self.assertTrue(any(f.level == "warn" for f in r.findings))


if __name__ == "__main__":
    unittest.main()
