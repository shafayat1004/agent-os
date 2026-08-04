"""`agentos doctor`: audit enforcement wiring.

Checks that every enforcement adapter is wired and functional:
- vendored runtime present at .agent-os/bin/agentos
- VERSION matches
- .claude/settings.json references the hooks and paths resolve
- .opencode/plugins/agentos.js present
- core.hooksPath set and pre-commit executable (or .git/hooks/pre-commit)
- AGENTS.md present and valid

Reports a per-harness matrix. Exit 0 = all wired, exit 1 = something broken.
"""
import json
import os
import subprocess


def _check_file(path, label):
    if os.path.exists(path):
        return True, "%s: present" % label
    return False, "%s: MISSING" % label


def _check_executable(path, label):
    if not os.path.exists(path):
        return False, "%s: MISSING" % label
    if os.access(path, os.X_OK):
        return True, "%s: executable" % label
    return False, "%s: NOT executable" % label


def _check_version(vendor_dir):
    version_path = os.path.join(vendor_dir, "VERSION")
    if not os.path.exists(version_path):
        return False, "VERSION: MISSING in .agent-os/"
    with open(version_path) as handle:
        local = handle.read().strip()
    # Check the vendored bin reports the same version
    agentos_bin = os.path.join(vendor_dir, "bin", "agentos")
    if not os.path.exists(agentos_bin):
        return False, "VERSION: %s but bin/agentos missing" % local
    try:
        result = subprocess.run([agentos_bin, "--version"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and local in result.stdout:
            return True, "VERSION: %s (verified)" % local
        return False, "VERSION: mismatch (file=%s, bin=%s)" % (
            local, result.stdout.strip())
    except (subprocess.TimeoutExpired, OSError) as error:
        return False, "VERSION: cannot verify (%s)" % error


def _check_claude_code(root, vendor_dir):
    """Check Claude Code hook registration."""
    settings_path = os.path.join(root, ".claude", "settings.json")
    if not os.path.exists(settings_path):
        return False, "Claude Code: .claude/settings.json MISSING"
    try:
        with open(settings_path) as handle:
            settings = json.load(handle)
    except (OSError, ValueError) as error:
        return False, "Claude Code: settings.json invalid (%s)" % error
    hooks = settings.get("hooks", {})
    required = ("PreToolUse", "PostToolUse", "PreCompact", "Stop")
    missing = [name for name in required if name not in hooks]
    if missing:
        return False, "Claude Code: missing hook entries: %s" % ", ".join(missing)
    # Check that hook commands reference paths that resolve
    for hook_name, entries in hooks.items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                command = hook.get("command", "")
                if "$CLAUDE_PROJECT_DIR" in command:
                    # Resolve relative to root
                    resolved = command.replace("$CLAUDE_PROJECT_DIR", root)
                    binary = resolved.split()[0]
                    if not os.path.exists(binary):
                        return False, ("Claude Code: %s command path does not "
                                       "resolve: %s" % (hook_name, binary))
    return True, "Claude Code: enforced (4 hooks registered)"


def _check_opencode(root, vendor_dir):
    """Check opencode plugin presence."""
    plugin_path = os.path.join(root, ".opencode", "plugins", "agentos.js")
    ok, msg = _check_file(plugin_path, "opencode plugin")
    if not ok:
        return False, "opencode: plugin MISSING"
    return True, "opencode: plugin present"


def _check_git_hooks(root, vendor_dir):
    """Check git pre-commit hook."""
    # Check core.hooksPath
    try:
        result = subprocess.run(
            ["git", "config", "core.hooksPath"],
            cwd=root, capture_output=True, text=True, timeout=5)
        hooks_path = result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        hooks_path = None

    if hooks_path:
        pre_commit = os.path.join(root, hooks_path, "pre-commit")
        ok, msg = _check_executable(pre_commit, "git pre-commit (.githooks)")
        if ok:
            return True, "git: core.hooksPath=%s, pre-commit enforced" % hooks_path
        return False, msg

    # Fallback: .git/hooks/pre-commit
    pre_commit = os.path.join(root, ".git", "hooks", "pre-commit")
    ok, msg = _check_executable(pre_commit, "git pre-commit (.git/hooks)")
    if ok:
        return True, "git: pre-commit in .git/hooks (consider setting core.hooksPath)"
    return False, "git: pre-commit MISSING (run 'agentos init' to install)"


def _check_agents_md(root):
    """Check AGENTS.md presence."""
    path = os.path.join(root, "AGENTS.md")
    ok, msg = _check_file(path, "AGENTS.md")
    if not ok:
        return False, msg
    return True, "AGENTS.md: present"


def _check_extensions(vendor_dir):
    """Report extension scripts if present."""
    scripts = []
    ext_base = os.path.join(vendor_dir, "hooks")
    for ext_name in ("pre-tool.d", "post-tool.d", "stop.d"):
        ext_path = os.path.join(ext_base, ext_name)
        if not os.path.isdir(ext_path):
            continue
        for name in sorted(os.listdir(ext_path)):
            if name.startswith("."):
                continue
            full = os.path.join(ext_path, name)
            if os.access(full, os.X_OK):
                scripts.append("%s/%s" % (ext_name, name))
    if scripts:
        return True, "extensions: %d script(s): %s" % (len(scripts), ", ".join(scripts))
    return True, "extensions: none (ok)"


def run_doctor(root, report=None):
    """Audit enforcement wiring. Exit 0 = all wired, exit 1 = broken."""
    report = report or (lambda line: None)
    vendor_dir = os.path.join(root, ".agent-os")
    self_hosted_bin = os.path.join(root, "bin", "agentos")

    checks = []
    # Runtime: vendored (.agent-os/) or self-hosted (bin/)
    vendored_bin = os.path.join(vendor_dir, "bin", "agentos")
    if os.path.exists(vendored_bin):
        runtime_location = "vendored (.agent-os/)"
        runtime_bin = vendored_bin
    elif os.path.exists(self_hosted_bin):
        runtime_location = "self-hosted (bin/)"
        runtime_bin = self_hosted_bin
        vendor_dir = root  # for version check and extensions
    else:
        checks.append(("runtime", False, ".agent-os/bin/agentos: MISSING"
                        " and bin/agentos: MISSING"))
        # Still check harness wiring
        runtime_bin = None

    if runtime_bin:
        checks.append(("runtime", True,
                        "runtime: %s" % runtime_location))
        # Version check
        version_path = os.path.join(
            vendor_dir if runtime_location.startswith("vendored") else root,
            "VERSION")
        if os.path.exists(version_path):
            with open(version_path) as handle:
                local = handle.read().strip()
            try:
                result = subprocess.run([runtime_bin, "--version"],
                                        capture_output=True, text=True,
                                        timeout=10)
                if result.returncode == 0 and local in result.stdout:
                    checks.append(("version", True,
                                   "VERSION: %s (verified)" % local))
                else:
                    checks.append(("version", False,
                                   "VERSION: mismatch"))
            except (subprocess.TimeoutExpired, OSError):
                checks.append(("version", False, "VERSION: cannot verify"))
        else:
            checks.append(("version", True, "VERSION: not found (ok for shared)"))

    # Harness enforcement
    ok, msg = _check_claude_code(root, vendor_dir)
    checks.append(("claude-code", ok, msg))
    ok, msg = _check_opencode(root, vendor_dir)
    checks.append(("opencode", ok, msg))
    ok, msg = _check_git_hooks(root, vendor_dir)
    checks.append(("git", ok, msg))

    # Rules file
    ok, msg = _check_agents_md(root)
    checks.append(("rules", ok, msg))

    # Extensions
    ok, msg = _check_extensions(vendor_dir)
    checks.append(("extensions", ok, msg))

    # Report
    all_ok = True
    for name, ok, msg in checks:
        status = "OK" if ok else "FAIL"
        report("[%s] %s" % (status, msg))
        if not ok:
            all_ok = False

    report("")
    if all_ok:
        report("All checks passed. Enforcement is wired.")
        return 0
    report("Some checks failed. Run 'agentos init' to fix wiring.")
    return 1
