import hashlib
import json
import os
import tempfile
import unittest

from agentos.checks.ledger import check_ledger

_STATE = "tests/fixtures/state_criteria.yaml"
_OK = "tests/fixtures/ledger_v1_ok.ndjson"
_BAD = "tests/fixtures/ledger_v1_bad.ndjson"


def _write(path, lines):
    with open(path, "w") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")


class TestLedgerLegacyV0(unittest.TestCase):
    def test_v0_ok_still_passes(self):
        result = check_ledger("tests/fixtures/ledger_ok.ndjson")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_v0_bad_still_fails(self):
        result = check_ledger("tests/fixtures/ledger_bad.ndjson")
        self.assertFalse(result.ok)


class TestLedgerV1Structural(unittest.TestCase):
    def test_v1_ok_passes_with_state(self):
        result = check_ledger(_OK, state_file=_STATE, root=".")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_v1_ok_passes_without_state(self):
        # No state file: no cross-reference, no coverage; structural only.
        result = check_ledger(_OK, state_file=None, root=".")
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_v1_bad_structural_errors(self):
        result = check_ledger(_BAD, state_file=None, root=".")
        messages = "\n".join(finding.message for finding in result.findings)
        self.assertFalse(result.ok)
        self.assertIn("empty claim", messages)
        self.assertIn("empty evidence_ref", messages)
        self.assertIn("ts is not ISO 8601", messages)
        self.assertIn("empty verifier", messages)
        self.assertIn("empty hash", messages)


class TestLedgerCoverage(unittest.TestCase):
    def test_uncovered_active_criterion_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "note", "status": "inferred",
                "evidence_ref": "n", "source_type": "human", "verifier": "",
                "hash": "", "ts": "2026-08-05T00:00:00Z"}])
            result = check_ledger(ledger, state_file=_STATE, root=temp)
            messages = "\n".join(finding.message for finding in result.findings)
        self.assertFalse(result.ok)
        self.assertIn("criterion 'build-green': no confirmed live proof", messages)

    def test_obsolete_criterion_needs_no_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            state = os.path.join(temp, "STATE.yaml")
            with open(state, "w") as handle:
                handle.write(
                    "task_id: t\ngoal: g\nrisk_class: reversible\n"
                    "acceptance_criteria: []\n"
                    "verification_status:\n  format: n/a\n  compile: n/a\n"
                    "  tests: pass\n  policy: pass\n  security: n/a\n"
                    "next_action: x\n"
                    "criteria:\n  - id: only-old\n    statement: retired\n"
                    "    status: obsolete\n")
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "note", "status": "inferred",
                "evidence_ref": "n", "source_type": "human", "verifier": "",
                "hash": "", "ts": "2026-08-05T00:00:00Z"}])
            result = check_ledger(ledger, state_file=state, root=temp)
        self.assertTrue(result.ok, [finding.message for finding in result.findings])


class TestLedgerCriterionKnown(unittest.TestCase):
    def test_unknown_criterion_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "ok", "status": "confirmed",
                "evidence_ref": "x", "source_type": "test", "verifier": "v",
                "hash": "h", "ts": "2026-08-05T00:00:00Z",
                "criterion": "no-such-criterion"}])
            result = check_ledger(ledger, state_file=_STATE, root=temp)
            messages = "\n".join(finding.message for finding in result.findings)
        self.assertFalse(result.ok)
        self.assertIn("criterion 'no-such-criterion' is not in STATE criteria", messages)


class TestLedgerStaleness(unittest.TestCase):
    def test_stale_live_proof_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "old proof", "status": "confirmed",
                "evidence_ref": "x", "source_type": "test", "verifier": "v",
                "hash": "h", "ts": "2026-07-01T00:00:00Z",
                "criterion": "build-green"}])
            result = check_ledger(ledger, state_file=_STATE, root=temp)
            errors = [finding for finding in result.findings
                      if finding.level == "error"]
        self.assertTrue(any("stale" in finding.message for finding in errors))

    def test_stale_free_standing_is_warning(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [
                {"version": 1, "id": "live", "claim": "current proof",
                 "status": "confirmed", "evidence_ref": "x",
                 "source_type": "test", "verifier": "v", "hash": "h",
                 "ts": "2026-08-05T00:00:00Z", "criterion": "build-green"},
                {"version": 1, "id": "x1", "claim": "old note",
                 "status": "inferred", "evidence_ref": "x",
                 "source_type": "human", "verifier": "", "hash": "",
                 "ts": "2026-07-01T00:00:00Z"}])
            result = check_ledger(ledger, state_file=_STATE, root=temp)
        self.assertTrue(result.ok, [finding.message for finding in result.findings])
        warnings = [finding for finding in result.findings
                    if finding.level == "warning"]
        self.assertTrue(any("stale" in finding.message for finding in warnings))


class TestLedgerFileDrift(unittest.TestCase):
    def _state_with_active_criterion(self, temp, criterion_id="build-green"):
        state = os.path.join(temp, "STATE.yaml")
        with open(state, "w") as handle:
            handle.write(
                "task_id: t\ngoal: g\nrisk_class: reversible\n"
                "acceptance_criteria: []\n"
                "verification_status:\n  format: n/a\n  compile: n/a\n"
                "  tests: pass\n  policy: pass\n  security: n/a\n"
                "next_action: x\n"
                "criteria:\n  - id: %s\n    statement: s\n" % criterion_id)
        return state

    def test_file_resolves_and_hash_matches_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            target = os.path.join(temp, "ref.txt")
            with open(target, "w") as handle:
                handle.write("stable content\n")
            with open(target, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            state = self._state_with_active_criterion(temp)
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "file proof", "status": "confirmed",
                "evidence_ref": "ref.txt", "source_type": "file", "verifier": "read",
                "hash": digest, "ts": "2026-08-05T00:00:00Z",
                "criterion": "build-green"}])
            result = check_ledger(ledger, state_file=state, root=temp)
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_hash_mismatch_live_proof_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            target = os.path.join(temp, "ref.txt")
            with open(target, "w") as handle:
                handle.write("changed content\n")
            state = self._state_with_active_criterion(temp)
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "file proof", "status": "confirmed",
                "evidence_ref": "ref.txt", "source_type": "file", "verifier": "read",
                "hash": "0" * 64, "ts": "2026-08-05T00:00:00Z",
                "criterion": "build-green"}])
            result = check_ledger(ledger, state_file=state, root=temp)
            errors = [finding for finding in result.findings
                      if finding.level == "error"]
        self.assertTrue(any("hash mismatch" in finding.message for finding in errors))

    def test_unresolvable_live_proof_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            state = self._state_with_active_criterion(temp)
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "file proof", "status": "confirmed",
                "evidence_ref": "missing.txt", "source_type": "file", "verifier": "read",
                "hash": "", "ts": "2026-08-05T00:00:00Z",
                "criterion": "build-green"}])
            result = check_ledger(ledger, state_file=state, root=temp)
            errors = [finding for finding in result.findings
                      if finding.level == "error"]
        self.assertTrue(any("does not resolve" in finding.message for finding in errors))

    def test_unresolvable_free_standing_is_warning(self):
        with tempfile.TemporaryDirectory() as temp:
            state = self._state_with_active_criterion(temp)
            ledger = os.path.join(temp, "ledger.ndjson")
            _write(ledger, [
                {"version": 1, "id": "live", "claim": "current proof",
                 "status": "confirmed", "evidence_ref": "x",
                 "source_type": "test", "verifier": "v", "hash": "h",
                 "ts": "2026-08-05T00:00:00Z", "criterion": "build-green"},
                {"version": 1, "id": "x1", "claim": "file note",
                 "status": "inferred", "evidence_ref": "missing.txt",
                 "source_type": "file", "verifier": "", "hash": "",
                 "ts": "2026-08-05T00:00:00Z"}])
            result = check_ledger(ledger, state_file=state, root=temp)
        self.assertTrue(result.ok, [finding.message for finding in result.findings])
        warnings = [finding for finding in result.findings
                   if finding.level == "warning"]
        self.assertTrue(any("does not resolve" in finding.message for finding in warnings))


class TestLedgerSuperseded(unittest.TestCase):
    def test_superseded_entry_is_silent(self):
        with tempfile.TemporaryDirectory() as temp:
            state = os.path.join(temp, "STATE.yaml")
            with open(state, "w") as handle:
                handle.write(
                    "task_id: t\ngoal: g\nrisk_class: reversible\n"
                    "acceptance_criteria: []\n"
                    "verification_status:\n  format: n/a\n  compile: n/a\n"
                    "  tests: pass\n  policy: pass\n  security: n/a\n"
                    "next_action: x\n")
            ledger = os.path.join(temp, "ledger.ndjson")
            # Line 1: a v1 entry that would fail structural (empty claim) and
            # drift (unresolvable file) if graded, but it is superseded.
            _write(ledger, [
                {"version": 1, "id": "old", "claim": "", "status": "confirmed",
                 "evidence_ref": "missing.txt", "source_type": "file",
                 "verifier": "v", "hash": "h", "ts": "2026-08-05T00:00:00Z"},
                {"version": 1, "id": "new", "claim": "replacement",
                 "status": "confirmed", "evidence_ref": "ok",
                 "source_type": "human", "verifier": "v", "hash": "",
                 "ts": "2026-08-05T00:00:00Z", "supersedes": "old"}])
            result = check_ledger(ledger, state_file=state, root=temp)
        self.assertTrue(result.ok, [finding.message for finding in result.findings])

    def test_supersede_by_line_number_silences_v0(self):
        with tempfile.TemporaryDirectory() as temp:
            state = os.path.join(temp, "STATE.yaml")
            with open(state, "w") as handle:
                handle.write(
                    "task_id: t\ngoal: g\nrisk_class: reversible\n"
                    "acceptance_criteria: []\n"
                    "verification_status:\n  format: n/a\n  compile: n/a\n"
                    "  tests: pass\n  policy: pass\n  security: n/a\n"
                    "next_action: x\n")
            ledger = os.path.join(temp, "ledger.ndjson")
            # Line 1 is a valid v0 entry. Line 2 supersedes line 1 by number.
            _write(ledger, [
                {"claim": "legacy", "status": "inferred", "evidence_ref": "n",
                 "source_type": "human", "verifier": "", "hash": "",
                 "ts": "2026-08-05T00:00:00Z"},
                {"version": 1, "id": "n2", "claim": "fresh",
                 "status": "confirmed", "evidence_ref": "ok",
                 "source_type": "human", "verifier": "v", "hash": "",
                 "ts": "2026-08-05T00:00:00Z", "supersedes": "1"}])
            result = check_ledger(ledger, state_file=state, root=temp)
        self.assertTrue(result.ok, [finding.message for finding in result.findings])


class TestLedgerObsoleteCriterion(unittest.TestCase):
    def test_obsolete_criterion_drift_is_silent(self):
        with tempfile.TemporaryDirectory() as temp:
            state = os.path.join(temp, "STATE.yaml")
            with open(state, "w") as handle:
                handle.write(
                    "task_id: t\ngoal: g\nrisk_class: reversible\n"
                    "acceptance_criteria: []\n"
                    "verification_status:\n  format: n/a\n  compile: n/a\n"
                    "  tests: pass\n  policy: pass\n  security: n/a\n"
                    "next_action: x\n"
                    "criteria:\n  - id: retired\n    statement: s\n"
                    "    status: obsolete\n"
                    "task_started: \"2026-08-01T00:00:00Z\"\n")
            ledger = os.path.join(temp, "ledger.ndjson")
            # Obsolete-criterion file entry, unresolvable + stale: drift must
            # stay silent, but structural v1 checks still apply.
            _write(ledger, [{
                "version": 1, "id": "x1", "claim": "old", "status": "confirmed",
                "evidence_ref": "missing.txt", "source_type": "file", "verifier": "v",
                "hash": "", "ts": "2026-07-01T00:00:00Z", "criterion": "retired"}])
            result = check_ledger(ledger, state_file=state, root=temp)
        self.assertTrue(result.ok, [finding.message for finding in result.findings])


if __name__ == "__main__":
    unittest.main()
