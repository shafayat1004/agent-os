"""Tests for the ste-writing glossary sync and necessity check.

These tests exercise the comparison, structure validation, and drift
classification logic offline with fixture glossaries. They also verify
that the real vendored glossary passes its own integrity check and that
its provenance file is pinned to the current content hash.

The script imports the standard library only, so the tests run under a
bare python3 with no third-party packages.
"""
import importlib.util
import json
import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SCRIPT = os.path.join(_ROOT, ".claude", "skills", "ste-writing",
                       "scripts", "glossary-sync.py")
_GLOSSARY = os.path.join(_ROOT, ".claude", "skills", "ste-writing",
                         "glossary.json")
_PROVENANCE = os.path.join(_ROOT, ".claude", "skills", "ste-writing",
                           "glossary.provenance.json")


def _load_module():
    spec = importlib.util.spec_from_file_location("glossary_sync", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_glossary(domains=None, generated="2026-07-29", note="x"):
    """Build a minimal valid glossary for fixtures."""
    if domains is None:
        domains = {
            "git": {
                "label": "Git",
                "sources": ["https://git-scm.com/docs"],
                "technical_nouns": ["commit"],
                "technical_verbs": ["rebase"],
                "canonical": {
                    "commit": {"aliases": ["changeset"],
                               "note": "A snapshot of the tree."}
                },
                "avoid": {
                    "master": {"prefer": "main", "reason": "Non-inclusive.",
                               "source": "https://git-scm.com"}
                },
            }
        }
    return {
        "version": "1.0.0",
        "generated": generated,
        "standard": "ASD-STE100 adaptation",
        "note": note,
        "domains": domains,
    }


class TestStructureValidation(unittest.TestCase):
    def setUp(self):
        self.gs = _load_module()

    def test_valid_glossary_passes(self):
        self.assertEqual([], self.gs.validate_structure(_make_glossary()))

    def test_missing_version_is_error(self):
        g = _make_glossary()
        del g["version"]
        self.assertTrue(any("version" in e for e in self.gs.validate_structure(g)))

    def test_missing_domains_is_error(self):
        g = _make_glossary()
        del g["domains"]
        self.assertTrue(self.gs.validate_structure(g))

    def test_empty_domains_is_error(self):
        g = _make_glossary(domains={})
        self.assertTrue(self.gs.validate_structure(g))

    def test_domain_missing_required_key(self):
        g = _make_glossary()
        del g["domains"]["git"]["sources"]
        errs = self.gs.validate_structure(g)
        self.assertTrue(any("sources" in e for e in errs))

    def test_empty_sources_list_is_error(self):
        g = _make_glossary()
        g["domains"]["git"]["sources"] = []
        errs = self.gs.validate_structure(g)
        self.assertTrue(any("sources" in e for e in errs))

    def test_canonical_without_aliases_is_error(self):
        g = _make_glossary()
        g["domains"]["git"]["canonical"]["commit"] = {"note": "no aliases"}
        errs = self.gs.validate_structure(g)
        self.assertTrue(any("aliases" in e for e in errs))

    def test_avoid_without_replacement_field_is_error(self):
        g = _make_glossary()
        g["domains"]["git"]["avoid"]["master"] = {"reason": "no fix"}
        errs = self.gs.validate_structure(g)
        self.assertTrue(any("prefer" in e for e in errs))

    def test_avoid_with_replacement_field_is_valid(self):
        g = _make_glossary()
        g["domains"]["git"]["avoid"]["master"] = {
            "replacement": "main", "reason": "Non-inclusive.",
            "source": "https://git-scm.com"}
        self.assertEqual([], self.gs.validate_structure(g))


class TestContentHash(unittest.TestCase):
    def setUp(self):
        self.gs = _load_module()

    def test_volatile_fields_excluded_from_hash(self):
        a = _make_glossary(generated="2026-07-29", note="one")
        b = _make_glossary(generated="2099-01-01", note="two")
        self.assertEqual(self.gs.content_hash(a), self.gs.content_hash(b))

    def test_normative_change_changes_hash(self):
        a = _make_glossary()
        b = _make_glossary()
        b["domains"]["git"]["technical_nouns"].append("branch")
        self.assertNotEqual(self.gs.content_hash(a), self.gs.content_hash(b))


class TestClassifyDrift(unittest.TestCase):
    def setUp(self):
        self.gs = _load_module()
        self.local = _make_glossary()

    def test_identical_is_in_sync(self):
        report = self.gs.classify_drift(self.local, _make_glossary())
        self.assertEqual("in_sync", report["classification"])

    def test_volatile_only_change_is_in_sync(self):
        # A difference confined to volatile metadata (generated date or
        # note) is in_sync: the update is not necessary.
        upstream = _make_glossary(generated="2099-01-01", note="changed")
        report = self.gs.classify_drift(self.local, upstream)
        self.assertEqual("in_sync", report["classification"])

    def test_added_term_is_necessary(self):
        upstream = _make_glossary()
        upstream["domains"]["git"]["technical_nouns"].append("branch")
        report = self.gs.classify_drift(self.local, upstream)
        self.assertEqual("necessary", report["classification"])
        self.assertGreater(report["detail"]["added_terms_count"], 0)

    def test_removed_term_is_necessary(self):
        upstream = _make_glossary()
        upstream["domains"]["git"]["technical_nouns"].remove("commit")
        report = self.gs.classify_drift(self.local, upstream)
        self.assertEqual("necessary", report["classification"])
        self.assertGreater(report["detail"]["removed_terms_count"], 0)

    def test_added_domain_is_necessary(self):
        upstream = _make_glossary()
        upstream["domains"]["docker"] = {
            "label": "Docker", "sources": ["https://docs.docker.com"],
            "technical_nouns": ["container"], "technical_verbs": ["build"],
            "canonical": {}, "avoid": {}}
        report = self.gs.classify_drift(self.local, upstream)
        self.assertEqual("necessary", report["classification"])
        self.assertIn("docker", report["detail"]["added_domains"])

    def test_changed_avoid_replacement_is_necessary(self):
        upstream = _make_glossary()
        upstream["domains"]["git"]["avoid"]["master"]["prefer"] = "trunk"
        report = self.gs.classify_drift(self.local, upstream)
        self.assertEqual("necessary", report["classification"])


class TestIntegrityCheck(unittest.TestCase):
    def setUp(self):
        self.gs = _load_module()

    def test_in_sync_when_hash_matches(self):
        local = _make_glossary()
        with tempfile.TemporaryDirectory() as tmp:
            lpath = os.path.join(tmp, "glossary.json")
            ppath = os.path.join(tmp, "glossary.provenance.json")
            with open(lpath, "w") as handle:
                json.dump(local, handle)
            self.gs.write_provenance(ppath, self.gs.content_hash(local),
                                     upstream_sha="abc", skill_version="1.1.0")
            ok, messages = self.gs.check_integrity(lpath, ppath)
            self.assertTrue(ok, messages)

    def test_local_drift_when_hash_differs(self):
        local = _make_glossary()
        with tempfile.TemporaryDirectory() as tmp:
            lpath = os.path.join(tmp, "glossary.json")
            ppath = os.path.join(tmp, "glossary.provenance.json")
            with open(lpath, "w") as handle:
                json.dump(local, handle)
            # Pin a wrong hash.
            self.gs.write_provenance(ppath, "sha256:deadbeef",
                                     upstream_sha="abc", skill_version="1.1.0")
            ok, messages = self.gs.check_integrity(lpath, ppath)
            self.assertFalse(ok)
            self.assertTrue(any("DRIFT" in m for m in messages))

    def test_missing_provenance_is_ok_with_warning(self):
        local = _make_glossary()
        with tempfile.TemporaryDirectory() as tmp:
            lpath = os.path.join(tmp, "glossary.json")
            with open(lpath, "w") as handle:
                json.dump(local, handle)
            ok, messages = self.gs.check_integrity(
                lpath, os.path.join(tmp, "missing.json"))
            self.assertTrue(ok)
            self.assertTrue(any("provenance" in m for m in messages))

    def test_invalid_structure_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            lpath = os.path.join(tmp, "glossary.json")
            with open(lpath, "w") as handle:
                json.dump({"version": "1.0.0", "domains": {}}, handle)
            ok, messages = self.gs.check_integrity(
                lpath, os.path.join(tmp, "missing.json"))
            self.assertFalse(ok)


class TestRealGlossary(unittest.TestCase):
    """The vendored glossary and its provenance must be consistent."""

    def setUp(self):
        self.gs = _load_module()

    def test_real_glossary_is_valid(self):
        with open(_GLOSSARY) as handle:
            glossary = json.load(handle)
        self.assertEqual([], self.gs.validate_structure(glossary),
                         "vendored glossary.json failed structure validation")

    def test_real_glossary_provenance_matches(self):
        ok, messages = self.gs.check_integrity(_GLOSSARY, _PROVENANCE)
        self.assertTrue(ok, messages)

    def test_real_provenance_records_upstream(self):
        with open(_PROVENANCE) as handle:
            provenance = json.load(handle)
        self.assertEqual("https://github.com/shafayat1004/agent-skills",
                         provenance["upstream_repo"])
        self.assertTrue(provenance["upstream_sha_at_sync"])
        self.assertTrue(provenance["content_hash"].startswith("sha256:"))

    def test_real_glossary_has_sixteen_domains(self):
        with open(_GLOSSARY) as handle:
            glossary = json.load(handle)
        domains = glossary["domains"]
        self.assertEqual(16, len(domains))
        expected = {"azure", "gcp", "aws", "datadog", "kubernetes", "docker",
                    "git", "jira", "opsgenie", "csharp", "fsharp", "dotnet",
                    "go", "javascript", "oop", "fp"}
        self.assertEqual(expected, set(domains))


class TestCLIRun(unittest.TestCase):
    """Exercise the script as a subprocess to confirm exit codes."""

    def test_check_exits_zero_on_real_glossary(self):
        import subprocess
        result = subprocess.run(
            ["python3", _SCRIPT, "--check", "--json"],
            capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_help_exits_nonzero_without_args(self):
        import subprocess
        result = subprocess.run(
            ["python3", _SCRIPT], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
