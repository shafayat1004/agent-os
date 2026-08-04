import io
import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from agentos.initcmd import run_init
from agentos.cli import main

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestInit(unittest.TestCase):
    def test_writes_artifacts_pointer_and_wrappers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "AGENTS.md")))
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "STATE.yaml")))
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "CLAUDE.md")))
            pre_tool_hook = os.path.join(temp_dir, ".claude", "hooks", "agentos-pre-tool")
            self.assertTrue(os.path.exists(pre_tool_hook))
            self.assertTrue(os.access(pre_tool_hook, os.X_OK))

    def test_wrappers_call_hook_subcommands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            with open(os.path.join(temp_dir, ".claude", "hooks",
                                   "agentos-pre-tool")) as hook_file:
                self.assertIn("hook-pre-tool", hook_file.read())
            with open(os.path.join(temp_dir, ".claude", "hooks",
                                   "agentos-stop-check")) as hook_file:
                self.assertIn("hook-stop", hook_file.read())
            with open(os.path.join(temp_dir, ".claude", "hooks",
                                   "agentos-post-tool")) as hook_file:
                self.assertIn("hook-post-tool", hook_file.read())
            with open(os.path.join(temp_dir, ".claude", "hooks",
                                   "agentos-pre-compact")) as hook_file:
                self.assertIn("hook-pre-compact", hook_file.read())

    def test_trace_and_compact_wrappers_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            for wrapper_name in ("agentos-post-tool", "agentos-pre-compact"):
                path = os.path.join(temp_dir, ".claude", "hooks", wrapper_name)
                self.assertTrue(os.path.exists(path), wrapper_name)
                self.assertTrue(os.access(path, os.X_OK), wrapper_name)

    def test_pointer_names_agents_md(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            with open(os.path.join(temp_dir, "CLAUDE.md")) as pointer_file:
                self.assertIn("AGENTS.md", pointer_file.read())

    def test_writes_pointer_files_for_each_harness(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            for relative in ("CLAUDE.md", "GEMINI.md",
                             os.path.join(".github", "copilot-instructions.md")):
                path = os.path.join(temp_dir, relative)
                self.assertTrue(os.path.exists(path), relative)
                with open(path) as pointer_file:
                    self.assertIn("AGENTS.md", pointer_file.read())

    def test_writes_opencode_plugin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_init(temp_dir, _ROOT)
            plugin_path = os.path.join(temp_dir, ".opencode", "plugins",
                                       "agentos.js")
            self.assertTrue(os.path.exists(plugin_path))
            with open(plugin_path) as plugin_file:
                body = plugin_file.read()
            self.assertIn("tool.execute.before", body)
            self.assertIn("tool.execute.after", body)
            self.assertIn("check-path", body)
            self.assertIn("session.idle", body)
            # Vendored model: SHARED is null, plugin finds .agent-os/bin/agentos
            self.assertIn(".agent-os/bin/agentos", body)
            self.assertIn("null", body)
            # The idle nudge must never start a new AI turn. session.prompt
            # awaits a full turn, which deadlocks the TUI when called from
            # the handler of the event that marks the prior turn done. The
            # refusal is surfaced as a toast and a log line instead; the git
            # pre-commit hook remains the hard gate.
            self.assertNotIn("session.prompt", body)
            self.assertNotIn("await client.session", body)
            self.assertIn("tui.showToast", body)
            self.assertIn("app.log", body)
            # The idle handler must skip the validator spawn when the
            # session is not claiming done, so a non-done turn never pays
            # for a subprocess (or a test-suite run). A cheap regex
            # pre-filter on STATE.yaml gates the spawn; the validator
            # remains the authoritative readiness check.
            self.assertIn("isClaimingDone", body)
            self.assertIn("stop_readiness", body)
            self.assertIn("done", body)

    def test_opencode_plugin_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_path = os.path.join(temp_dir, ".opencode", "plugins",
                                       "agentos.js")
            os.makedirs(os.path.dirname(plugin_path))
            with open(plugin_path, "w") as plugin_file:
                plugin_file.write("// my custom plugin")
            run_init(temp_dir, _ROOT)
            with open(plugin_path) as plugin_file:
                self.assertEqual(plugin_file.read(), "// my custom plugin")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_opencode_plugin_parses_as_es_module(self):
        # node --check treats .js as CommonJS, so parse a .mjs copy to
        # check the ES module syntax.
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            plugin_path = os.path.join(temp_dir, ".opencode", "plugins",
                                       "agentos.js")
            module_copy = os.path.join(temp_dir, "plugin-check.mjs")
            shutil.copyfile(plugin_path, module_copy)
            completed = subprocess.run(["node", "--check", module_copy],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_installs_pre_commit_when_git_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, ".git", "hooks"))
            run_init(temp_dir, _ROOT)
            # Vendored model: .githooks/pre-commit is the primary location
            githooks_path = os.path.join(temp_dir, ".githooks", "pre-commit")
            self.assertTrue(os.path.exists(githooks_path))
            self.assertTrue(os.access(githooks_path, os.X_OK))
            with open(githooks_path) as hook_file:
                hook_body = hook_file.read()
            self.assertIn("diff --staged", hook_body)
            self.assertIn(".agent-os/bin/agentos", hook_body)
            # Also written to .git/hooks/ as a fallback
            git_hook_path = os.path.join(temp_dir, ".git", "hooks", "pre-commit")
            self.assertTrue(os.path.exists(git_hook_path))

    def test_skips_pre_commit_without_git(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            self.assertFalse(
                os.path.exists(os.path.join(temp_dir, ".git", "hooks", "pre-commit")))

    def test_non_destructive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "CLAUDE.md"), "w") as pointer_file:
                pointer_file.write("keep me")
            run_init(temp_dir, _ROOT)
            with open(os.path.join(temp_dir, "CLAUDE.md")) as pointer_file:
                self.assertEqual(pointer_file.read(), "keep me")

    def test_writes_verification_config(self):
        from agentos import yaml_min
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, "tests"))
            run_init(temp_dir, _ROOT)
            config_path = os.path.join(temp_dir, "policies",
                                        "verification.yaml")
            self.assertTrue(os.path.exists(config_path), config_path)
            with open(config_path) as config_file:
                config = yaml_min.load(config_file.read())
            self.assertIn("commands", config)
            self.assertEqual(config["commands"]["tests"],
                             "python3 -m unittest discover -s tests")
            self.assertIn("all", config["commands"]["policy"])

    def test_verification_config_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, "policies"))
            config_path = os.path.join(temp_dir, "policies",
                                        "verification.yaml")
            with open(config_path, "w") as config_file:
                config_file.write("# my custom config\n")
            run_init(temp_dir, _ROOT)
            with open(config_path) as config_file:
                self.assertEqual(config_file.read(), "# my custom config\n")

    def test_settings_snippet_is_valid_json_with_hooks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_init(temp_dir, _ROOT)
            parsed_settings = json.loads(summary["settings_snippet"])
            self.assertIn("PreToolUse", parsed_settings["hooks"])
            self.assertIn("PostToolUse", parsed_settings["hooks"])
            self.assertIn("PreCompact", parsed_settings["hooks"])
            self.assertIn("Stop", parsed_settings["hooks"])

    def test_settings_json_written_when_absent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_init(temp_dir, _ROOT)
            self.assertTrue(summary["settings_written"])
            settings_path = os.path.join(temp_dir, ".claude", "settings.json")
            with open(settings_path) as settings_file:
                written = json.load(settings_file)
            self.assertIn("PreToolUse", written["hooks"])
            pre_tool_command = written["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            self.assertIn("$CLAUDE_PROJECT_DIR", pre_tool_command)

    def test_settings_json_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, ".claude"))
            settings_path = os.path.join(temp_dir, ".claude", "settings.json")
            with open(settings_path, "w") as settings_file:
                settings_file.write('{"model": "opus"}')
            summary = run_init(temp_dir, _ROOT)
            self.assertFalse(summary["settings_written"])
            with open(settings_path) as settings_file:
                self.assertEqual(settings_file.read(), '{"model": "opus"}')

    def test_dest_is_file_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "afile")
            with open(file_path, "w") as output_file:
                output_file.write("x")
            with self.assertRaises(OSError):
                run_init(file_path, _ROOT)

    def test_vendors_runtime_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_init(temp_dir, _ROOT)
            self.assertTrue(summary["vendored"])
            # The vendored runtime exists
            self.assertTrue(os.path.exists(
                os.path.join(temp_dir, ".agent-os", "bin", "agentos")))
            self.assertTrue(os.path.exists(
                os.path.join(temp_dir, ".agent-os", "agentos", "cli.py")))
            self.assertTrue(os.path.exists(
                os.path.join(temp_dir, ".agent-os", "schemas")))
            self.assertTrue(os.path.exists(
                os.path.join(temp_dir, ".agent-os", "VERSION")))
            # No __pycache__ vendored
            self.assertFalse(os.path.exists(
                os.path.join(temp_dir, ".agent-os", "agentos", "__pycache__")))
            # .gitignore inside .agent-os
            self.assertTrue(os.path.exists(
                os.path.join(temp_dir, ".agent-os", ".gitignore")))

    def test_creates_extension_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            for ext in ("pre-tool.d", "post-tool.d", "stop.d"):
                ext_path = os.path.join(temp_dir, ".agent-os", "hooks", ext)
                self.assertTrue(os.path.isdir(ext_path), ext)
                self.assertTrue(os.path.exists(
                    os.path.join(ext_path, ".gitkeep")))

    def test_hook_wrappers_reference_vendored_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            for wrapper in ("agentos-pre-tool", "agentos-stop-check",
                            "agentos-post-tool", "agentos-pre-compact"):
                path = os.path.join(temp_dir, ".claude", "hooks", wrapper)
                with open(path) as f:
                    body = f.read()
                self.assertIn(".agent-os/bin/agentos", body,
                              "%s does not reference vendored path" % wrapper)

    def test_hook_wrappers_have_extension_loop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            # pre-tool and stop-check have the extension loop
            for wrapper, ext_dir in [("agentos-pre-tool", "pre-tool.d"),
                                     ("agentos-stop-check", "stop.d"),
                                     ("agentos-post-tool", "post-tool.d")]:
                path = os.path.join(temp_dir, ".claude", "hooks", wrapper)
                with open(path) as f:
                    body = f.read()
                self.assertIn(ext_dir, body,
                              "%s does not reference %s" % (wrapper, ext_dir))

    def test_shared_mode_uses_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_init(temp_dir, _ROOT, shared=True)
            self.assertFalse(summary["vendored"])
            self.assertTrue(os.path.isabs(summary["agentos_bin"]))
            # No .agent-os/ directory in shared mode
            self.assertFalse(os.path.exists(
                os.path.join(temp_dir, ".agent-os")))
            # Hook wrappers reference the absolute path
            pre_tool = os.path.join(temp_dir, ".claude", "hooks",
                                    "agentos-pre-tool")
            with open(pre_tool) as f:
                self.assertIn(summary["agentos_bin"], f.read())

    def test_vendored_agentos_version_works(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_init(temp_dir, _ROOT)
            vendored_bin = os.path.join(temp_dir, ".agent-os", "bin", "agentos")
            completed = subprocess.run([vendored_bin, "--version"],
                                       cwd=temp_dir, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with open(os.path.join(_ROOT, "VERSION")) as version_file:
                expected = version_file.read().strip()
            self.assertIn(expected, completed.stdout)

    def test_cli_init_exit_zero_and_bootstraps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            captured_output = io.StringIO()
            with contextlib.redirect_stdout(captured_output):
                code = main(["init", temp_dir])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "AGENTS.md")))
            self.assertIn("PreToolUse", captured_output.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_installed_pre_commit_runs(self):
        # The generated hook must actually invoke real validator subcommands.
        # With nothing staged and no banned deps, it exits 0.
        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(["git", "init", "-q", temp_dir], check=True)
            run_init(temp_dir, _ROOT)
            # Use the .githooks/pre-commit (the primary location)
            hook_path = os.path.join(temp_dir, ".githooks", "pre-commit")
            completed = subprocess.run([hook_path], cwd=temp_dir,
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
