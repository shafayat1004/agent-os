import unittest
from agentos.jsonschema_min import validate


class TestJsonSchemaMin(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "type": "object",
            "required": ["claim", "status"],
            "additionalProperties": False,
            "properties": {
                "claim": {"type": "string"},
                "status": {"enum": ["confirmed", "inferred", "unverified"]},
                "count": {"type": "integer"},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "ver": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            },
        }

    def test_valid(self):
        self.assertEqual(validate(
            {"claim": "x", "status": "confirmed", "tags": ["a"], "ver": "1.0.0"},
            self.schema), [])

    def test_missing_required(self):
        errs = validate({"claim": "x"}, self.schema)
        self.assertTrue(any("status" in e for e in errs))

    def test_wrong_type(self):
        errs = validate({"claim": 5, "status": "confirmed"}, self.schema)
        self.assertTrue(any("claim" in e and "string" in e for e in errs))

    def test_bad_enum(self):
        errs = validate({"claim": "x", "status": "maybe"}, self.schema)
        self.assertTrue(any("status" in e for e in errs))

    def test_additional_property(self):
        errs = validate({"claim": "x", "status": "confirmed", "extra": 1}, self.schema)
        self.assertTrue(any("extra" in e for e in errs))

    def test_bad_pattern(self):
        errs = validate({"claim": "x", "status": "confirmed", "ver": "1.0"}, self.schema)
        self.assertTrue(any("ver" in e for e in errs))

    def test_min_items(self):
        errs = validate({"claim": "x", "status": "confirmed", "tags": []}, self.schema)
        self.assertTrue(any("tags" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
