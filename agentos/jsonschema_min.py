"""Minimal JSON Schema (Draft-07 subset) validator, standard library only."""
import re

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(instance, schema, path="$"):
    errs = []
    _check(instance, schema, path, errs)
    return errs


def _check(instance, schema, path, errs):
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPE_CHECKS[x](instance) for x in types):
            errs.append("%s: expected type %s" % (path, "/".join(types)))
            return
    if "enum" in schema and instance not in schema["enum"]:
        errs.append("%s: %r not in enum %s" % (path, instance, schema["enum"]))
    if "pattern" in schema and isinstance(instance, str):
        if re.search(schema["pattern"], instance) is None:
            errs.append("%s: %r does not match pattern" % (path, instance))
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errs.append("%s: missing required property '%s'" % (path, req))
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for k in instance:
                if k not in props:
                    errs.append("%s: additional property '%s' not allowed" % (path, k))
        for k, sub in props.items():
            if k in instance:
                _check(instance[k], sub, "%s.%s" % (path, k), errs)
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errs.append("%s: fewer than %d items" % (path, schema["minItems"]))
        item_schema = schema.get("items")
        if item_schema is not None:
            for i, item in enumerate(instance):
                _check(item, item_schema, "%s[%d]" % (path, i), errs)
