import unittest
from agentos.checks.state import check_state
from agentos.checks.rules import check_rules
from agentos.checks.diff import check_diff


class TestExampleSubject(unittest.TestCase):
    def test_state_valid(self):
        result = check_state("examples/subject/STATE.yaml")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_rules_valid(self):
        result = check_rules("examples/subject/AGENTS.md")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_policy_blocks_app_and_autogen(self):
        result = check_diff("examples/subject/policies/path-policy.yaml",
                            ["AppEggShellGallery/x.fs", "LibClient/x.render",
                             "LibClient/src/ok.fs"])
        # LibClient/x.render -> error (never); App* -> warn; LibClient ok -> none
        self.assertFalse(result.ok)
        self.assertTrue(any(finding.level == "warn" for finding in result.findings))


if __name__ == "__main__":
    unittest.main()
