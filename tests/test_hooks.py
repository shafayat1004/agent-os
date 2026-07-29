import unittest
import os
import stat


class TestHooks(unittest.TestCase):
    def test_hooks_exist_and_executable(self):
        for hook_name in ("pre-tool", "post-tool", "pre-compact",
                          "pre-commit", "stop-check"):
            path = os.path.join("hooks", hook_name)
            self.assertTrue(os.path.exists(path), path)
            mode = os.stat(path).st_mode
            self.assertTrue(mode & stat.S_IXUSR, "%s not executable" % path)

    def test_hooks_reference_agentos(self):
        for hook_name in ("pre-tool", "post-tool", "pre-compact",
                          "pre-commit", "stop-check"):
            with open(os.path.join("hooks", hook_name)) as hook_file:
                self.assertIn("agentos", hook_file.read())


if __name__ == "__main__":
    unittest.main()
