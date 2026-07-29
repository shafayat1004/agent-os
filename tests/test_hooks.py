import unittest
import os
import stat


class TestHooks(unittest.TestCase):
    def test_hooks_exist_and_executable(self):
        for name in ("pre-tool", "pre-commit", "stop-check"):
            path = os.path.join("hooks", name)
            self.assertTrue(os.path.exists(path), path)
            mode = os.stat(path).st_mode
            self.assertTrue(mode & stat.S_IXUSR, "%s not executable" % path)

    def test_hooks_reference_agentos(self):
        for name in ("pre-commit", "stop-check"):
            with open(os.path.join("hooks", name)) as fh:
                self.assertIn("agentos", fh.read())


if __name__ == "__main__":
    unittest.main()
