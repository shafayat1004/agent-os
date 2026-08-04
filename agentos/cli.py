import argparse
import json
import os
import subprocess
import sys

from agentos.checks import state as state_check
from agentos.checks import ledger as ledger_check
from agentos.checks import diff as diff_check
from agentos.checks import deps as deps_check
from agentos.checks import skills as skills_check
from agentos.checks import rules as rules_check
from agentos import gitutil
from agentos import hooks as hook_commands
from agentos.initcmd import run_init
from agentos.yaml_min import YamlError

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _print(results, as_json):
    if as_json:
        payload = [{"name": result.name, "grade": result.grade, "ok": result.ok,
                    "findings": [{"level": finding.level, "message": finding.message}
                                 for finding in result.findings]} for result in results]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            print("[%s] %s (grade %s)" % (status, result.name, result.grade))
            for finding in result.findings:
                print("  %s: %s" % (finding.level.upper(), finding.message))


def _run_all(args):
    results = []
    results.append(state_check.check_state(args.state_file))
    results.append(ledger_check.check_ledger(args.ledger_file,
                                             state_file=args.state_file,
                                             root=args.root))
    results.append(diff_check.check_diff(args.path_policy,
                                         gitutil.changed_files(staged=args.staged,
                                                               rev_range=args.range)))
    results.append(deps_check.check_deps(args.dep_policy, args.root))
    results.append(skills_check.check_skills(args.skill_index, args.skills_dir))
    results.append(rules_check.check_rules(args.rules_file))
    return results


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="cmd")

    command_parser = subparsers.add_parser("state")
    command_parser.add_argument("state_file", nargs="?", default="STATE.yaml")
    command_parser = subparsers.add_parser("ledger")
    command_parser.add_argument("ledger_file", nargs="?",
                                default="evidence/ledger.ndjson")
    command_parser = subparsers.add_parser("diff")
    command_parser.add_argument("--path-policy", default="policies/path-policy.yaml")
    command_parser.add_argument("--staged", action="store_true")
    command_parser.add_argument("--range", default=None)
    command_parser = subparsers.add_parser("deps")
    command_parser.add_argument("--dep-policy", default="policies/dependency-policy.yaml")
    command_parser.add_argument("--root", default=".")
    command_parser = subparsers.add_parser("skills")
    command_parser.add_argument("--skill-index", default="skills/index.yaml")
    command_parser.add_argument("--skills-dir", default=".claude/skills")
    command_parser = subparsers.add_parser("rules")
    command_parser.add_argument("rules_file", nargs="?", default="AGENTS.md")
    command_parser = subparsers.add_parser("init")
    command_parser.add_argument("dest", nargs="?", default=".")
    command_parser = subparsers.add_parser("hook-pre-tool")
    command_parser.add_argument("--path-policy", default="policies/path-policy.yaml")
    command_parser = subparsers.add_parser("hook-stop")
    command_parser.add_argument("--state-file", default="STATE.yaml")
    command_parser.add_argument("--ledger-file", default="evidence/ledger.ndjson")
    command_parser.add_argument("--run-tests", default=None,
                                help="test command the verdict gate runs when "
                                     "STATE sets stop_readiness to ready")
    command_parser = subparsers.add_parser("hook-post-tool")
    command_parser.add_argument("--tool", default=None,
                                help="adapter mode: when --tool or --target is "
                                     "given, the stdin payload is not read")
    command_parser.add_argument("--target", default=None,
                                help="adapter mode: see --tool")
    command_parser.add_argument("--trace", default="evidence/trace.ndjson")
    command_parser = subparsers.add_parser("hook-pre-compact")
    command_parser.add_argument("--state-file", default="STATE.yaml")
    command_parser = subparsers.add_parser("done", help="explicit completion "
                                           "gate; always runs the verdict, "
                                           "rejects a missing or blocked "
                                           "stop_readiness with an actionable "
                                           "reason")
    command_parser.add_argument("--state-file", default="STATE.yaml")
    command_parser.add_argument("--ledger-file", default="evidence/ledger.ndjson")
    command_parser.add_argument("--run-tests", default=None,
                                help="test command the verdict gate runs")
    command_parser.add_argument("--verify-config",
                                default="policies/verification.yaml",
                                help="verification config; run the configured "
                                     "verifiers and derive status before the "
                                     "verdict gate")
    command_parser.add_argument("--no-verify", action="store_true",
                                help="skip the verifiers; trust self-reported "
                                     "verification_status")
    command_parser = subparsers.add_parser("verify", help="run the configured "
                                           "project verifiers and write the "
                                           "derived status into STATE.yaml")
    command_parser.add_argument("--config", default="policies/verification.yaml")
    command_parser.add_argument("--state-file", default="STATE.yaml")
    command_parser.add_argument("--ledger-file", default="evidence/ledger.ndjson")
    command_parser.add_argument("--timeout", type=int, default=None)
    command_parser = subparsers.add_parser("check-path")
    command_parser.add_argument("paths", nargs="+")
    command_parser.add_argument("--path-policy", default="policies/path-policy.yaml")
    command_parser = subparsers.add_parser("all")
    command_parser.add_argument("--state-file", default="STATE.yaml")
    command_parser.add_argument("--ledger-file", default="evidence/ledger.ndjson")
    command_parser.add_argument("--path-policy", default="policies/path-policy.yaml")
    command_parser.add_argument("--dep-policy", default="policies/dependency-policy.yaml")
    command_parser.add_argument("--root", default=".")
    command_parser.add_argument("--skill-index", default="skills/index.yaml")
    command_parser.add_argument("--skills-dir", default=".claude/skills")
    command_parser.add_argument("--rules-file", default="AGENTS.md")
    command_parser.add_argument("--staged", action="store_true")
    command_parser.add_argument("--range", default=None)

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.cmd is None:
        parser.print_help()
        return 2
    if args.cmd == "hook-pre-tool":
        return hook_commands.run_pre_tool(sys.stdin.read(), args.path_policy,
                                          os.getcwd())
    if args.cmd == "hook-stop":
        return hook_commands.run_stop(args.state_file, args.ledger_file,
                                      run_tests=args.run_tests)
    if args.cmd == "hook-post-tool":
        # Flags mean adapter mode (the opencode plugin): never touch stdin.
        # A harness that spawns hooks with an inherited, never-EOF stdin
        # (opencode's Bun shell) blocks here forever otherwise, wedging the
        # session after the first tool call. Stdin is read only on the
        # flagless Claude Code path, which pipes the payload and closes
        # stdin.
        stdin_text = ("" if args.tool is not None or args.target is not None
                      else sys.stdin.read())
        return hook_commands.run_post_tool(stdin_text, args.trace,
                                           tool=args.tool, target=args.target)
    if args.cmd == "hook-pre-compact":
        return hook_commands.run_pre_compact(args.state_file)
    if args.cmd == "done":
        verify_config = None if args.no_verify else args.verify_config
        return hook_commands.run_done(args.state_file, args.ledger_file,
                                      run_tests=args.run_tests,
                                      verify_config=verify_config)
    if args.cmd == "verify":
        from agentos.verify import run_verify
        return run_verify(args.config, args.state_file, args.ledger_file,
                          timeout=args.timeout)
    if args.cmd == "check-path":
        return hook_commands.run_check_path(args.paths, args.path_policy,
                                            os.getcwd())
    if args.cmd == "init":
        try:
            summary = run_init(args.dest, _ROOT,
                               report=lambda action, path: print("%s: %s" % (action, path)))
        except OSError as error:
            print("config error: %s" % error, file=sys.stderr)
            return 2
        if summary["settings_written"]:
            print("\nWrote .claude/settings.json with the PreToolUse,"
                  " PostToolUse, PreCompact, and Stop hooks.")
        else:
            print("\n.claude/settings.json exists; merge these hooks into it:\n")
            print(summary["settings_snippet"])
        print("Also active: the git pre-commit hook and the opencode plugin"
              " (.opencode/plugins/agentos.js).")
        return 0
    try:
        if args.cmd == "state":
            results = [state_check.check_state(args.state_file)]
        elif args.cmd == "ledger":
            results = [ledger_check.check_ledger(args.ledger_file)]
        elif args.cmd == "diff":
            changed = gitutil.changed_files(staged=args.staged, rev_range=args.range)
            results = [diff_check.check_diff(args.path_policy, changed)]
        elif args.cmd == "deps":
            results = [deps_check.check_deps(args.dep_policy, args.root)]
        elif args.cmd == "skills":
            results = [skills_check.check_skills(args.skill_index, args.skills_dir)]
        elif args.cmd == "rules":
            results = [rules_check.check_rules(args.rules_file)]
        elif args.cmd == "all":
            results = _run_all(args)
        else:
            return 2
    except (FileNotFoundError, OSError, subprocess.CalledProcessError,
            YamlError) as error:
        print("config error: %s" % error, file=sys.stderr)
        return 2
    _print(results, args.json)
    return 0 if all(result.ok for result in results) else 1
