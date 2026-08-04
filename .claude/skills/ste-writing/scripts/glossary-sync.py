#!/usr/bin/env python3
"""Glossary sync and necessity check for the ste-writing skill.

The ste-writing skill ships a vendored domain glossary
(`glossary.json`) copied from the upstream `agent-skills` repo. This
script answers two questions:

  1. REGULAR CHECK (no network): is the local glossary still in its
     last deliberate state? It validates the structure and compares a
     content hash against the pinned provenance file. A mismatch means
     the local file drifted from the last sync, so a re-sync or a
     re-pin is necessary. This is the deterministic check wired into
     `agentos all` via `policies/custom-checks.yaml`.

  2. NECESSITY CHECK (`--check-upstream`, network): has the upstream
     glossary changed in a way that makes pulling an update necessary?
     It fetches the upstream file, compares the normative term content
     (volatile metadata such as the generated date is excluded), and
     reports whether the drift is necessary. An update is absolutely
     necessary only when term content was added, removed, or changed.

The script imports the Python standard library only, so it matches the
zero-dependency guarantee of the validator.

Exit codes:
  0  in sync, or cosmetic-only drift, or successful pin
  1  local drift, invalid structure, or necessary upstream drift
  2  usage error or network failure
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_ROOT = os.path.dirname(_HERE)
_DEFAULT_LOCAL = os.path.join(_SKILL_ROOT, "glossary.json")
_DEFAULT_PROVENANCE = os.path.join(_SKILL_ROOT, "glossary.provenance.json")

_UPSTREAM_REPO = "https://github.com/shafayat1004/agent-skills"
_UPSTREAM_RAW = ("https://raw.githubusercontent.com/shafayat1004/"
                 "agent-skills/main/skills/ste-writing/glossary.json")

# Fields excluded from the content hash because they are volatile
# metadata, not normative terminology. A change to only these fields is
# cosmetic drift, not a necessary update.
_VOLATILE_TOP = {"generated", "note"}
_VOLATILE_DOMAIN = set()


def _canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strip_volatile(glossary):
    """Return a copy with volatile top-level fields removed."""
    return {k: v for k, v in glossary.items() if k not in _VOLATILE_TOP}


def content_hash(glossary):
    """sha256 over the normative term content, volatile fields excluded."""
    normative = _strip_volatile(glossary)
    return "sha256:" + hashlib.sha256(_canonical_json(normative)).hexdigest()


def load_glossary(path):
    with open(path) as handle:
        return json.load(handle)


def validate_structure(glossary):
    """Return a list of human-readable structure errors. Empty means valid."""
    errors = []
    if not isinstance(glossary, dict):
        return ["glossary top level is not a JSON object"]
    if "version" not in glossary:
        errors.append("missing top-level 'version'")
    domains = glossary.get("domains")
    if not isinstance(domains, dict):
        errors.append("missing or non-object 'domains'")
        return errors
    if not domains:
        errors.append("'domains' is empty")
        return errors
    for name, block in domains.items():
        prefix = "domain '%s'" % name
        if not isinstance(block, dict):
            errors.append("%s: not an object" % prefix)
            continue
        for key in ("label", "sources", "technical_nouns",
                    "technical_verbs", "canonical", "avoid"):
            if key not in block:
                errors.append("%s: missing '%s'" % (prefix, key))
        sources = block.get("sources")
        if sources is not None and not (isinstance(sources, list) and sources):
            errors.append("%s: 'sources' must be a non-empty list" % prefix)
        canon = block.get("canonical")
        if isinstance(canon, dict):
            for term, spec in canon.items():
                if not isinstance(spec, dict) or "aliases" not in spec:
                    errors.append("%s: canonical '%s' lacks 'aliases'"
                                  % (prefix, term))
        avoid = block.get("avoid")
        if isinstance(avoid, dict):
            for term, spec in avoid.items():
                if not isinstance(spec, dict):
                    errors.append("%s: avoid '%s' is not an object" % (prefix, term))
                    continue
                if "reason" not in spec:
                    errors.append("%s: avoid '%s' lacks 'reason'"
                                  % (prefix, term))
                if "prefer" not in spec and "replacement" not in spec:
                    errors.append("%s: avoid '%s' lacks 'prefer' or 'replacement'"
                                  % (prefix, term))
    return errors


def load_provenance(path):
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return json.load(handle)


def check_integrity(local_path, provenance_path):
    """Regular check. Returns (ok, messages)."""
    messages = []
    try:
        glossary = load_glossary(local_path)
    except (OSError, ValueError) as error:
        return False, ["cannot load glossary: %s" % error]
    errors = validate_structure(glossary)
    if errors:
        return False, ["invalid structure:"] + errors
    actual = content_hash(glossary)
    provenance = load_provenance(provenance_path)
    if not provenance:
        messages.append("no provenance file; run with --pin to record the "
                        "current glossary state")
        messages.append("content_hash=%s" % actual)
        return True, messages
    pinned = provenance.get("content_hash")
    if pinned == actual:
        messages.append("in sync: local glossary matches pinned provenance")
        messages.append("content_hash=%s" % actual)
        return True, messages
    messages.append("LOCAL DRIFT: local glossary does not match pinned hash")
    messages.append("pinned=%s" % pinned)
    messages.append("actual=%s" % actual)
    messages.append("re-sync from upstream, or re-pin if the change was "
                    "deliberate: glossary-sync.py --pin")
    return False, messages


def _domain_terms(block):
    """Flatten a domain block into a frozenset of normative term items."""
    items = set()
    for noun in block.get("technical_nouns", []) or []:
        items.add(("noun", noun))
    for verb in block.get("technical_verbs", []) or []:
        items.add(("verb", verb))
    for term, spec in (block.get("canonical", {}) or {}).items():
        items.add(("canonical_term", term))
        if isinstance(spec, dict):
            for alias in spec.get("aliases", []) or []:
                items.add(("canonical_alias", alias))
    for term, spec in (block.get("avoid", {}) or {}).items():
        items.add(("avoid_term", term))
        if isinstance(spec, dict):
            repl = spec.get("prefer", spec.get("replacement", ""))
            items.add(("avoid_replacement", repl))
    return items


def classify_drift(local, upstream):
    """Compare two glossaries. Returns a dict with classification + detail.

    classification is 'in_sync' or 'necessary'. An update is necessary
    only when the normative term content differs. A difference confined
    to volatile metadata (the generated date or the note) is in_sync,
    because that content is excluded from the comparison.
    """
    local_norm = _strip_volatile(local)
    upstream_norm = _strip_volatile(upstream)
    if _canonical_json(local_norm) == _canonical_json(upstream_norm):
        return {"classification": "in_sync",
                "summary": "upstream and local match on normative content; "
                           "update not necessary"}

    local_domains = local.get("domains", {}) or {}
    upstream_domains = upstream.get("domains", {}) or {}
    added_domains = sorted(set(upstream_domains) - set(local_domains))
    removed_domains = sorted(set(local_domains) - set(upstream_domains))
    common = sorted(set(local_domains) & set(upstream_domains))

    added_terms = []
    removed_terms = []
    changed_terms = []
    for name in common:
        before = _domain_terms(local_domains[name])
        after = _domain_terms(upstream_domains[name])
        for item in sorted(after - before):
            added_terms.append("%s:%s" % (name, "/".join(item)))
        for item in sorted(before - after):
            removed_terms.append("%s:%s" % (name, "/".join(item)))
    detail = {
        "added_domains": added_domains,
        "removed_domains": removed_domains,
        "added_terms": added_terms,
        "removed_terms": removed_terms,
        "added_terms_count": len(added_terms),
        "removed_terms_count": len(removed_terms),
    }
    return {"classification": "necessary",
            "summary": "upstream term content changed; update is necessary",
            "detail": detail}


def fetch_upstream(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "agent-os-glossary-sync"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def write_provenance(provenance_path, local_hash, upstream_sha=None,
                     skill_version=None):
    import datetime
    record = {
        "upstream_repo": _UPSTREAM_REPO,
        "upstream_raw_url": _UPSTREAM_RAW,
        "upstream_ref": "main",
        "upstream_sha_at_sync": upstream_sha or "unknown",
        "synced_at": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%d"),
        "content_hash": local_hash,
        "hash_excludes": sorted(_VOLATILE_TOP),
        "skill_version": skill_version,
    }
    with open(provenance_path, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return record


def _emit(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
    elif isinstance(obj, dict) and "messages" in obj:
        for line in obj["messages"]:
            print(line)
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="glossary-sync.py",
        description="Glossary sync and necessity check for the ste-writing skill.")
    parser.add_argument("--check", action="store_true",
                        help="regular integrity check (no network)")
    parser.add_argument("--check-upstream", action="store_true",
                        help="fetch upstream and classify drift (network)")
    parser.add_argument("--pin", action="store_true",
                        help="write provenance with the current local hash")
    parser.add_argument("--upstream-sha", default=None,
                        help="upstream commit SHA to record with --pin")
    parser.add_argument("--local", default=_DEFAULT_LOCAL,
                        help="path to local glossary.json")
    parser.add_argument("--provenance", default=_DEFAULT_PROVENANCE,
                        help="path to glossary.provenance.json")
    parser.add_argument("--upstream", default=_UPSTREAM_RAW,
                        help="upstream raw URL for --check-upstream")
    parser.add_argument("--skill-version", default=None,
                        help="skill version to record in provenance")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    args = parser.parse_args(argv)

    if args.check:
        ok, messages = check_integrity(args.local, args.provenance)
        _emit({"ok": ok, "messages": messages}, args.json)
        return 0 if ok else 1

    if args.pin:
        try:
            glossary = load_glossary(args.local)
        except (OSError, ValueError) as error:
            print("cannot load glossary: %s" % error, file=sys.stderr)
            return 2
        errors = validate_structure(glossary)
        if errors:
            print("invalid structure; fix before pinning:", file=sys.stderr)
            for err in errors:
                print("  " + err, file=sys.stderr)
            return 2
        record = write_provenance(args.provenance, content_hash(glossary),
                                  upstream_sha=args.upstream_sha,
                                  skill_version=args.skill_version)
        _emit({"ok": True, "pinned": record}, args.json)
        return 0

    if args.check_upstream:
        try:
            local = load_glossary(args.local)
        except (OSError, ValueError) as error:
            print("cannot load local glossary: %s" % error, file=sys.stderr)
            return 2
        try:
            raw = fetch_upstream(args.upstream)
        except (urllib.error.URLError, OSError) as error:
            print("network error: %s" % error, file=sys.stderr)
            return 2
        try:
            upstream = json.loads(raw.decode("utf-8"))
        except ValueError as error:
            print("upstream is not valid JSON: %s" % error, file=sys.stderr)
            return 2
        report = classify_drift(local, upstream)
        report["upstream_url"] = args.upstream
        _emit(report, args.json)
        if report["classification"] == "necessary":
            return 1
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
