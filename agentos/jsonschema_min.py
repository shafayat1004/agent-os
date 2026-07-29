"""Minimal JSON Schema (Draft-07 subset) validator, standard library only."""
import re

_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def validate(instance, schema, path="$"):
    errors = []
    _check(instance, schema, path, errors)
    return errors


def _check(instance, schema, path, errors):
    declared_type = schema.get("type")
    if declared_type is not None:
        allowed_types = declared_type if isinstance(declared_type, list) else [declared_type]
        if not any(_TYPE_CHECKS[type_name](instance) for type_name in allowed_types):
            errors.append("%s: expected type %s" % (path, "/".join(allowed_types)))
            return
    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r not in enum %s" % (path, instance, schema["enum"]))
    if "pattern" in schema and isinstance(instance, str):
        if re.search(schema["pattern"], instance) is None:
            errors.append("%s: %r does not match pattern" % (path, instance))
    if isinstance(instance, dict):
        for required_property in schema.get("required", []):
            if required_property not in instance:
                errors.append("%s: missing required property '%s'"
                              % (path, required_property))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for property_name in instance:
                if property_name not in properties:
                    errors.append("%s: additional property '%s' not allowed"
                                  % (path, property_name))
        for property_name, property_schema in properties.items():
            if property_name in instance:
                _check(instance[property_name], property_schema,
                       "%s.%s" % (path, property_name), errors)
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: fewer than %d items" % (path, schema["minItems"]))
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(instance):
                _check(item, item_schema, "%s[%d]" % (path, index), errors)
