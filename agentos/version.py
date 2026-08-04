"""Version reporting for agent-os.

Three version dimensions exist (see SPEC.md section 7):

- Release version: one semver string, the git tag. Source of truth is the
  VERSION file at the package root.
- Schema version: a per-file integer (schema_version) at the top of each
  schema file. Additive and independent per file.
- Adapter protocol version: one integer for the hook/adapter contract.
  Bumped when the hook stdin/stdout contract or exit-code mapping changes.

This module reads the VERSION file and the schema_version fields from each
schema file so `agentos --version` can report all three dimensions.
"""
import json
import os

_ADAPTER_PROTOCOL = 1

_cached_release = None
_cached_schemas = None


def _package_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def release_version(root=None):
    """Read the release semver from the VERSION file."""
    global _cached_release
    if _cached_release is not None:
        return _cached_release
    base = root if root is not None else _package_root()
    path = os.path.join(base, "VERSION")
    with open(path) as handle:
        _cached_release = handle.read().strip()
    return _cached_release


def schema_versions(root=None):
    """Read schema_version from each schema file in schemas/."""
    global _cached_schemas
    if _cached_schemas is not None:
        return dict(_cached_schemas)
    base = root if root is not None else _package_root()
    schemas_dir = os.path.join(base, "schemas")
    versions = {}
    for name in sorted(os.listdir(schemas_dir)):
        if not name.endswith(".schema.json"):
            continue
        path = os.path.join(schemas_dir, name)
        with open(path) as handle:
            schema = json.load(handle)
        key = name.replace(".schema.json", "")
        versions[key] = schema.get("schema_version", "unversioned")
    _cached_schemas = dict(versions)
    return versions


def adapter_protocol():
    """Return the adapter protocol version integer."""
    return _ADAPTER_PROTOCOL


def version_string(root=None):
    """Format the full version string for --version output."""
    rv = release_version(root)
    sv = schema_versions(root)
    ap = adapter_protocol()
    sv_str = ", ".join("%s=%s" % (k, v) for k, v in sorted(sv.items()))
    return "agentos %s (schema %s; adapter protocol %d)" % (rv, sv_str, ap)
