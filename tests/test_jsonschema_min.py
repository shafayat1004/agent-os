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
        errors = validate({"claim": "x"}, self.schema)
        self.assertTrue(any("status" in error for error in errors))

    def test_wrong_type(self):
        errors = validate({"claim": 5, "status": "confirmed"}, self.schema)
        self.assertTrue(any("claim" in error and "string" in error for error in errors))

    def test_bad_enum(self):
        errors = validate({"claim": "x", "status": "maybe"}, self.schema)
        self.assertTrue(any("status" in error for error in errors))

    def test_additional_property(self):
        errors = validate({"claim": "x", "status": "confirmed", "extra": 1}, self.schema)
        self.assertTrue(any("extra" in error for error in errors))

    def test_bad_pattern(self):
        errors = validate({"claim": "x", "status": "confirmed", "ver": "1.0"}, self.schema)
        self.assertTrue(any("ver" in error for error in errors))

    def test_min_items(self):
        errors = validate({"claim": "x", "status": "confirmed", "tags": []}, self.schema)
        self.assertTrue(any("tags" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
