import unittest
import os
import tempfile
import importlib.util
from importlib.machinery import SourceFileLoader

_SPEC = importlib.util.spec_from_loader(
    "bootstrap_mod", SourceFileLoader("bootstrap_mod", "bin/bootstrap"))
bootstrap_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bootstrap_mod)


class TestBootstrap(unittest.TestCase):
    def test_copies_templates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = bootstrap_mod.bootstrap("templates", temp_dir)
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "AGENTS.md")))
            self.assertTrue(os.path.exists(
                os.path.join(temp_dir, "policies", "path-policy.yaml")))
            self.assertIn(os.path.join(temp_dir, "STATE.yaml"), created)

    def test_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(temp_dir, exist_ok=True)
            with open(os.path.join(temp_dir, "AGENTS.md"), "w") as handle:
                handle.write("keep me")
            bootstrap_mod.bootstrap("templates", temp_dir)
            with open(os.path.join(temp_dir, "AGENTS.md")) as handle:
                self.assertEqual(handle.read(), "keep me")


if __name__ == "__main__":
    unittest.main()
