import argparse
import json
import sys

from agentos.checks import state as state_check
from agentos.checks import ledger as ledger_check
from agentos.checks import diff as diff_check
from agentos.checks import deps as deps_check
from agentos.checks import skills as skills_check
from agentos.checks import rules as rules_check
from agentos import gitutil


def _print(results, as_json):
    if as_json:
        payload = [{"name": r.name, "grade": r.grade, "ok": r.ok,
                    "findings": [{"level": f.level, "message": f.message}
                                 for f in r.findings]} for r in results]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for r in results:
            status = "PASS" if r.ok else "FAIL"
            print("[%s] %s (grade %s)" % (status, r.name, r.grade))
            for f in r.findings:
                print("  %s: %s" % (f.level.upper(), f.message))


def _run_all(a):
    results = []
    results.append(state_check.check_state(a.state_file))
    results.append(ledger_check.check_ledger(a.ledger_file))
    results.append(diff_check.check_diff(a.path_policy,
                                         gitutil.changed_files(staged=a.staged,
                                                               rev_range=a.range)))
    results.append(deps_check.check_deps(a.dep_policy, a.root))
    results.append(skills_check.check_skills(a.skill_index, a.skills_dir))
    results.append(rules_check.check_rules(a.rules_file))
    return results


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("state"); p.add_argument("state_file", nargs="?", default="STATE.yaml")
    p = sub.add_parser("ledger"); p.add_argument("ledger_file", nargs="?",
                                                 default="evidence/ledger.ndjson")
    p = sub.add_parser("diff")
    p.add_argument("--path-policy", default="policies/path-policy.yaml")
    p.add_argument("--staged", action="store_true")
    p.add_argument("--range", default=None)
    p = sub.add_parser("deps")
    p.add_argument("--dep-policy", default="policies/dependency-policy.yaml")
    p.add_argument("--root", default=".")
    p = sub.add_parser("skills")
    p.add_argument("--skill-index", default="skills/index.yaml")
    p.add_argument("--skills-dir", default=".claude/skills")
    p = sub.add_parser("rules"); p.add_argument("rules_file", nargs="?", default="AGENTS.md")
    p = sub.add_parser("all")
    p.add_argument("--state-file", default="STATE.yaml")
    p.add_argument("--ledger-file", default="evidence/ledger.ndjson")
    p.add_argument("--path-policy", default="policies/path-policy.yaml")
    p.add_argument("--dep-policy", default="policies/dependency-policy.yaml")
    p.add_argument("--root", default=".")
    p.add_argument("--skill-index", default="skills/index.yaml")
    p.add_argument("--skills-dir", default=".claude/skills")
    p.add_argument("--rules-file", default="AGENTS.md")
    p.add_argument("--staged", action="store_true")
    p.add_argument("--range", default=None)

    try:
        a = parser.parse_args(argv)
    except SystemExit:
        return 2
    if a.cmd is None:
        parser.print_help()
        return 2
    try:
        if a.cmd == "state":
            results = [state_check.check_state(a.state_file)]
        elif a.cmd == "ledger":
            results = [ledger_check.check_ledger(a.ledger_file)]
        elif a.cmd == "diff":
            files = gitutil.changed_files(staged=a.staged, rev_range=a.range)
            results = [diff_check.check_diff(a.path_policy, files)]
        elif a.cmd == "deps":
            results = [deps_check.check_deps(a.dep_policy, a.root)]
        elif a.cmd == "skills":
            results = [skills_check.check_skills(a.skill_index, a.skills_dir)]
        elif a.cmd == "rules":
            results = [rules_check.check_rules(a.rules_file)]
        elif a.cmd == "all":
            results = _run_all(a)
        else:
            return 2
    except FileNotFoundError as e:
        print("config error: %s" % e, file=sys.stderr)
        return 2
    _print(results, a.json)
    return 0 if all(r.ok for r in results) else 1
