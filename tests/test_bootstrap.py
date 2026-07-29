import unittest
import os
import tempfile
import importlib.util
from importlib.machinery import SourceFileLoader

_SPEC = importlib.util.spec_from_loader("bootstrap_mod", SourceFileLoader("bootstrap_mod", "bin/bootstrap"))
bootstrap_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bootstrap_mod)


class TestBootstrap(unittest.TestCase):
    def test_copies_templates(self):
        with tempfile.TemporaryDirectory() as d:
            created = bootstrap_mod.bootstrap("templates", d)
            self.assertTrue(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertTrue(os.path.exists(
                os.path.join(d, "policies", "path-policy.yaml")))
            self.assertIn(os.path.join(d, "STATE.yaml"), created)

    def test_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "AGENTS.md"), "w") as fh:
                fh.write("keep me")
            bootstrap_mod.bootstrap("templates", d)
            with open(os.path.join(d, "AGENTS.md")) as fh:
                self.assertEqual(fh.read(), "keep me")


if __name__ == "__main__":
    unittest.main()
