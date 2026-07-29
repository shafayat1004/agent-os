import unittest
import io
import contextlib
import shutil
from agentos.cli import main


class TestCli(unittest.TestCase):
    def test_state_ok_exit_zero(self):
        code = main(["state", "tests/fixtures/state_ok.yaml"])
        self.assertEqual(code, 0)

    def test_state_bad_exit_one(self):
        code = main(["state", "tests/fixtures/state_bad.yaml"])
        self.assertEqual(code, 1)

    def test_json_output(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["--json", "ledger", "tests/fixtures/ledger_ok.ndjson"])
        self.assertIn('"name": "ledger"', buf.getvalue())
        self.assertIn('"grade": "A"', buf.getvalue())

    def test_unknown_command_exit_two(self):
        code = main(["nope"])
        self.assertEqual(code, 2)

    def test_missing_state_file_exit_two(self):
        code = main(["state", "tests/fixtures/does_not_exist.yaml"])
        self.assertEqual(code, 2)

    def test_missing_ledger_file_exit_two(self):
        code = main(["ledger", "tests/fixtures/does_not_exist.ndjson"])
        self.assertEqual(code, 2)

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_bad_git_range_exit_two(self):
        code = main(["diff", "--range", "no-such-ref-zzz..also-no-such-zzz"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
