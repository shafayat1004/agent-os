import unittest
from agentos.yaml_min import load, YamlError


class TestYamlMin(unittest.TestCase):
    def test_flat_mapping(self):
        self.assertEqual(load("goal: fix bug\nrisk_class: reversible\n"),
                         {"goal": "fix bug", "risk_class": "reversible"})

    def test_scalars_typed(self):
        self.assertEqual(load("a: 3\nb: true\nc: null\n"),
                         {"a": 3, "b": True, "c": None})

    def test_quoted_string_keeps_hash(self):
        self.assertEqual(load('a: "x # y"\n'), {"a": "x # y"})

    def test_comment_stripped(self):
        self.assertEqual(load("a: 1  # note\n# whole line\nb: 2\n"),
                         {"a": 1, "b": 2})

    def test_flow_list(self):
        self.assertEqual(load("may_edit: [Lib*, ThirdParty]\n"),
                         {"may_edit": ["Lib*", "ThirdParty"]})

    def test_block_sequence_of_scalars(self):
        self.assertEqual(load("acceptance_criteria:\n  - one\n  - two\n"),
                         {"acceptance_criteria": ["one", "two"]})

    def test_block_sequence_of_mappings(self):
        text = ("confirmed_facts:\n"
                "  - fact: uses jwt\n"
                "    evidence_ref: auth.fs:212\n")
        self.assertEqual(load(text),
                         {"confirmed_facts": [
                             {"fact": "uses jwt", "evidence_ref": "auth.fs:212"}]})

    def test_nested_mapping(self):
        text = "verification_status:\n  compile: pass\n  tests: pending\n"
        self.assertEqual(load(text),
                         {"verification_status": {"compile": "pass", "tests": "pending"}})

    def test_flow_map(self):
        self.assertEqual(load("x: {name: Moq, reason: org rule}\n"),
                         {"x": {"name": "Moq", "reason": "org rule"}})

    def test_tab_indent_raises(self):
        with self.assertRaises(YamlError):
            load("a:\n\t- x\n")

    def test_block_literal_raises(self):
        with self.assertRaises(YamlError):
            load("a: |\n  line\n")

    def test_anchor_raises(self):
        with self.assertRaises(YamlError):
            load("a: &x value\n")

    def test_alias_raises(self):
        with self.assertRaises(YamlError):
            load("a: *x\n")

    def test_quoted_ampersand_ok(self):
        self.assertEqual(load('a: "&x"\n'), {"a": "&x"})

    def test_block_literal_variant_raises(self):
        with self.assertRaises(YamlError):
            load("a: >-\n")

    def test_nested_under_sequence_item_raises(self):
        text = ("items:\n"
                "  - fact: a\n"
                "    detail:\n"
                "      x: 1\n"
                "      y: 2\n")
        with self.assertRaises(YamlError):
            load(text)

    def test_flat_sequence_item_still_works(self):
        text = ("confirmed_facts:\n"
                "  - fact: a\n"
                "    evidence_ref: b\n")
        self.assertEqual(load(text),
                          {"confirmed_facts": [{"fact": "a", "evidence_ref": "b"}]})


if __name__ == "__main__":
    unittest.main()
