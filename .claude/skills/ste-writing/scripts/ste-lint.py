# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""STE-flavored writing linter for software, SRE, DevOps, and IT prose.

Two layers:
  1. Regex layer (default, zero dependency). Runs under `uv run` with no setup.
  2. spaCy layer (optional). If spaCy and an English model are installed, the
     linter uses the parser for passive voice, imperative form, noun clusters,
     and multi-instruction detection. Without spaCy it falls back to regex.

Install the optional parser layer:
    uv pip install spacy
    python -m spacy download en_core_web_sm

The linter reads a domain glossary (glossary.json next to the skill) so that
doc-verified technical nouns and verbs are not flagged, aliases map to one
canonical name, and deprecated or non-inclusive terms are caught with the
preferred replacement.

Usage:
    uv run ste-lint.py draft.md
    uv run ste-lint.py --strict --explain runbook.md
    uv run ste-lint.py --json draft.md
    uv run ste-lint.py --ci docs/*.md          # exit nonzero below threshold
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

try:
    import spacy  # type: ignore
except Exception:  # pragma: no cover - spaCy is optional
    spacy = None  # type: ignore


# --------------------------------------------------------------------------
# Rule catalog. IDs match .claude/skills/ste-writing/SKILL.md.
# severity drives CI gating. weight drives the compliance score.
# --------------------------------------------------------------------------
RULES = {
    "SRE-1.11": {"title": "Non-canonical term (alias)", "severity": "major", "weight": 5, "section": "terms"},
    "SRE-1.12": {"title": "Deprecated or discouraged term", "severity": "major", "weight": 5, "section": "terms"},
    "SRE-2.1": {"title": "Long noun cluster", "severity": "major", "weight": 5, "section": "terms"},
    "SRE-3.6": {"title": "Passive voice", "severity": "critical", "weight": 8, "section": "syntax"},
    "SRE-3.7": {"title": "Nominalization / weak verb", "severity": "major", "weight": 5, "section": "syntax"},
    "SRE-3.8": {"title": "-ing main verb", "severity": "major", "weight": 4, "section": "syntax"},
    "SRE-4.2": {"title": "Contraction", "severity": "major", "weight": 4, "section": "surface"},
    "SRE-4.5": {"title": "Likely missing article", "severity": "minor", "weight": 2, "section": "surface"},
    "SRE-5.1": {"title": "Sentence over 20 words (strict)", "severity": "major", "weight": 5, "section": "procedure"},
    "SRE-5.2": {"title": "Multiple instructions in one sentence", "severity": "critical", "weight": 8, "section": "procedure"},
    "SRE-5.3": {"title": "Instruction not imperative", "severity": "critical", "weight": 8, "section": "procedure"},
    "SRE-5.4": {"title": "Condition after command", "severity": "major", "weight": 5, "section": "procedure"},
    "SRE-6.3": {"title": "Sentence over 25 words (flavored)", "severity": "major", "weight": 4, "section": "description"},
    "SRE-6.6": {"title": "Paragraph over six sentences", "severity": "minor", "weight": 2, "section": "description"},
    "SRE-8.1": {"title": "Semicolon", "severity": "major", "weight": 4, "section": "surface"},
    "SRE-8.2": {"title": "Em dash (slop marker)", "severity": "minor", "weight": 2, "section": "surface"},
    "SRE-9.3": {"title": "Phrasal verb", "severity": "major", "weight": 4, "section": "surface"},
    "SRE-GR.7": {"title": "Non-inclusive language", "severity": "minor", "weight": 3, "section": "surface"},
    "SRE-X.1": {"title": "Hype / filler / AI padding", "severity": "major", "weight": 4, "section": "surface"},
}


# --------------------------------------------------------------------------
# Word lists (regex layer). These are English style controls, not domain terms.
# Domain terms live in glossary.json.
# --------------------------------------------------------------------------
MARKETING = [
    "seamless", "seamlessly", "robust", "powerful", "cutting-edge", "effortless", "effortlessly",
    "world-class", "next-generation", "revolutionary", "blazing", "lightning-fast", "elegant",
    "delightful", "turnkey", "best-in-class", "state-of-the-art", "game-changing", "first-class",
    "battle-tested", "enterprise-grade", "supercharge", "unlock", "unleash", "empower", "empowers",
    "holistic", "frictionless", "synergy", "innovative",
]
BANNED = {
    "begin": "start", "begins": "starts", "commence": "start", "commences": "starts",
    "initiate": "start", "initiates": "starts", "originate": "start",
    "utilize": "use", "utilizes": "uses", "utilizing": "using",
    "leverage": "use", "leverages": "uses", "leveraging": "using",
    "facilitate": "help", "facilitates": "helps",
    "ensure": "make sure", "ensures": "makes sure", "ensuring": "making sure",
    "prior to": "before", "subsequent to": "after",
    "obtain": "get", "obtains": "gets", "acquire": "get", "acquires": "gets",
    "demonstrate": "show", "demonstrates": "shows",
    "additionally": "also", "furthermore": "also", "moreover": "also",
    "comprehensive": "", "comprehensively": "", "utilization": "use",
    "aforementioned": "", "henceforth": "", "therein": "", "whilst": "while",
    "amongst": "among", "numerous": "many", "myriad": "many", "plethora": "many",
    "in order to": "to", "a variety of": "", "in the event that": "if",
    "due to the fact that": "because", "it is important to note": "",
}
PHRASAL = {
    "spin up": "start", "spin down": "stop", "spun up": "started", "reach out": "contact",
    "reaching out": "contacting", "dive into": "examine", "dives into": "examines",
    "diving into": "examining", "kick off": "start", "kicks off": "starts",
    "roll out": "release", "rolls out": "releases", "tear down": "remove",
    "ramp up": "increase", "circle back": "return to", "drill down": "inspect",
    "set up": "configure", "shut down": "stop",
}
MODAL_HEDGE = [
    "it is important to note", "it should be noted", "it is worth noting",
    "please note that", "as mentioned", "as noted above",
]
INCLUSIVE = {
    "man-hours": "person-hours", "manpower": "staff", "chairman": "chair",
    "he/she": "they", "he or she": "they", "sanity check": "consistency check",
    "grandfathered": "legacy", "dummy value": "placeholder value",
}
CONTRACTIONS = {
    "can't": "cannot", "won't": "will not", "don't": "do not", "doesn't": "does not",
    "didn't": "did not", "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "hasn't": "has not", "haven't": "have not", "it's": "it is",
    "that's": "that is", "there's": "there is", "they're": "they are", "we're": "we are",
    "you're": "you are", "you've": "you have", "we've": "we have", "they've": "they have",
    "shouldn't": "should not", "wouldn't": "would not", "couldn't": "could not",
    "mustn't": "must not", "needn't": "need not", "what's": "what is", "here's": "here is",
    "let's": "let us", "who's": "who is", "i'm": "I am", "i've": "I have", "i'll": "I will",
    "we'll": "we will", "they'll": "they will", "it'll": "it will", "you'll": "you will",
}

BE = r"(?:am|is|are|was|were|be|been|being)"
PP_IRREG = r"(?:done|made|sent|read|built|kept|held|set|put|run|written|shown|given|taken|found|got|gotten|seen|known|thrown|drawn|drained|deployed|rotated)"

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-/]*")
# "'t/'re/'ve/'ll/'d/'m" are always contractions. "'s" is a contraction only after
# a small set of pronouns/adverbs; after any other word it is a possessive, so it
# must not be flagged (e.g. "React's", "FSharpPlus's").
CONTRACTION_RE = re.compile(
    r"\b\w+['’](?:t|re|ve|ll|d|m)\b"
    r"|\b(?:it|that|there|here|what|who|let|he|she|where|when|how)['’]s\b",
    re.I,
)
NOMINALIZATION_RE = re.compile(
    r"\b(?:perform(?:s|ed)?|conduct(?:s|ed)?|provide(?:s|d)?|carry out|carries out|make use of|makes use of)\b"
    r"|\b\w{4,}(?:tion|ment|ance|ence)\s+of\b",
    re.I,
)
CODE_BLOCK_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
# Markdown table separator rows (e.g. |---|:--:|), so they are not treated as prose
TABLE_SEP_RE = re.compile(r"(?m)^(?=[^\n]*-)[ \t|:\-]+$")

# Mass/uncountable nouns that do not need an article. Extended from the glossary.
SINGULAR_COUNT_NOUN_EXCEPTIONS = {
    "traffic", "data", "code", "software", "hardware", "firmware", "storage", "logging",
    "monitoring", "linux", "kubernetes", "terraform", "prometheus", "grafana", "backup",
    "throughput", "latency", "telemetry", "observability", "infrastructure",
}


# --------------------------------------------------------------------------
# Glossary
# --------------------------------------------------------------------------
# Alias / avoid keys that are ordinary English words or too ambiguous to flag
# context-free. The full mappings stay in glossary.json for reference; the
# linter only auto-flags high-precision entries so it does not false-positive.
GENERIC_GLOSSARY_STOP = {
    "cache", "index", "instance", "agent", "bucket", "hash", "escalation",
    "rotation", "schedule", "refinement", "points", "ticket", "issue", "card",
    "native", "hang", "compose", "lambda", "defer", "var", "override", "object",
    "interface", "inheritance", "monad", "functor", "currying", "native",
    "recipient", "grooming", "value", "master", "union type",
}
# Uppercase acronyms that collide with common English words when lowercased.
ACRONYM_STOP = {"go", "os", "io", "id", "es", "it", "is", "as", "in", "on", "arm"}


class Glossary:
    def __init__(self):
        self.terms = set()            # approved nouns + verbs (lowercase)
        self.alias_map = {}           # alias_lower -> canonical (str)
        self.avoid_map = {}           # term_lower -> {prefer, reason}
        self.domains = []

    @staticmethod
    def _alias_is_lintable(alias):
        """Keep only high-precision aliases: acronyms with digits/symbols,
        safe uppercase acronyms, misspellings, or unambiguous multiword phrases.
        Drop bare common-English words and word-collision acronyms."""
        low = alias.lower()
        if low in GENERIC_GLOSSARY_STOP or len(low) < 2:
            return False
        if any(c in alias for c in "0123456789-./|?<>"):
            return True               # EC2, S3, go-lang, docker-compose, |>, T?
        if alias.isupper() and len(alias) >= 2:
            return low not in ACRONYM_STOP   # AKS, PVC, RBAC ok; GO/OS dropped
        if " " in alias:
            return low not in GENERIC_GLOSSARY_STOP
        # single lowercase/mixed token: keep only clear jargon variants
        return low not in GENERIC_GLOSSARY_STOP

    @classmethod
    def load(cls, path):
        g = cls()
        if not path or not os.path.exists(path):
            return g
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        domains = data.get("domains", data)
        if not isinstance(domains, dict):
            return g
        alias_targets = {}   # alias_lower -> set(canonical)
        for key, spec in domains.items():
            if not isinstance(spec, dict):
                continue
            g.domains.append(key)
            for term in spec.get("technical_nouns", []) or []:
                g.terms.add(str(term).lower())
            for term in spec.get("technical_verbs", []) or []:
                g.terms.add(str(term).lower())
            for canonical, cspec in (spec.get("canonical", {}) or {}).items():
                if not isinstance(cspec, dict):
                    continue
                g.terms.add(str(canonical).lower())
                for alias in cspec.get("aliases", []) or []:
                    if not cls._alias_is_lintable(str(alias)):
                        continue
                    # skip pure-casing aliases (e.g. javascript -> JavaScript):
                    # case-insensitive matching would flag the correct form.
                    if str(alias).lower() == str(canonical).lower():
                        continue
                    alias_targets.setdefault(str(alias).lower(), set()).add(str(canonical))
            for term, aspec in (spec.get("avoid", {}) or {}).items():
                if not isinstance(aspec, dict):
                    continue
                low = str(term).lower()
                prefer = aspec.get("prefer") or ""
                # skip guidance-only entries (no replacement, or parenthetical
                # judgement calls a regex cannot detect), generic words, and
                # pure-casing fixes (would flag the already-correct form)
                if (not prefer or "(" in term or low in GENERIC_GLOSSARY_STOP
                        or low == prefer.lower()):
                    continue
                existing = g.avoid_map.get(low)
                if existing:
                    prefers = {p.strip() for p in (existing["prefer"] + " / " + prefer).split("/")}
                    existing["prefer"] = " / ".join(sorted(p for p in prefers if p))
                    existing["reason"] = "Discouraged across domains. Pick the replacement that fits the context."
                else:
                    g.avoid_map[low] = {"prefer": prefer, "reason": aspec.get("reason", "")}
        # keep only unambiguous aliases (one canonical across all domains)
        for alias, canons in alias_targets.items():
            distinct = {c.lower() for c in canons}
            if len(distinct) == 1:
                g.alias_map[alias] = sorted(canons)[0]
        # if a token is both an alias and an avoid term, keep only the avoid
        # finding so it does not double-flag with a conflicting suggestion
        for k in list(g.alias_map):
            if k in g.avoid_map:
                del g.alias_map[k]
        return g

    def is_approved(self, text):
        return text.lower() in self.terms


def default_glossary_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "glossary.json")


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Safe autofix. Applies only high-confidence lexical fixes and protects every
# code span (fenced blocks and inline code) so no identifier, flag, error code,
# path, or literal is ever changed. It does NOT touch passive voice, sentence
# length, imperative form, noun clusters, or glossary terms: those need judgment.
# --------------------------------------------------------------------------
FIX_TOKEN_RE = re.compile(r"(```.*?```|`[^`]*`)", re.S)


def _match_case(source_word, replacement):
    if source_word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _fix_prose(seg):
    # expand contractions (straight and curly apostrophe), preserve leading case
    for bad, full in CONTRACTIONS.items():
        for variant in (bad, bad.replace("'", "’")):
            seg = re.sub(r"\b" + re.escape(variant) + r"\b",
                         lambda m, f=full: _match_case(m.group(0), f), seg, flags=re.I)
    # swap banned words that have a plain replacement
    for bad, good in BANNED.items():
        if not good:
            continue
        seg = re.sub(r"\b" + re.escape(bad) + r"\b",
                     lambda m, g=good: _match_case(m.group(0), g), seg, flags=re.I)
    # turn em/en dashes, " -- " asides, and prose semicolons into sentence breaks.
    # a sentinel marks inserted breaks so only those get a capital letter.
    seg = re.sub(r"\s*[—–]\s*", "\x00", seg)
    seg = re.sub(r"\s+--\s+", "\x00", seg)
    seg = re.sub(r";\s+", "\x00", seg)
    seg = re.sub(r"\x00([a-z])", lambda m: "\x00" + m.group(1).upper(), seg)
    seg = seg.replace("\x00", ". ")
    return seg


def safe_fix(text):
    return "".join(part if part.startswith("`") else _fix_prose(part)
                   for part in FIX_TOKEN_RE.split(text))


def strip_code(t):
    t = CODE_BLOCK_RE.sub(" ", t)
    t = INLINE_CODE_RE.sub(" ", t)
    # neutralize Markdown tables: drop separator rows, then split cells so that
    # terse cell fragments across a "|" do not form fake noun clusters
    t = TABLE_SEP_RE.sub(" ", t)
    t = t.replace("|", ". ")
    t = t.replace("**", " ")  # drop Markdown bold markers so they do not join clusters
    return t


def wc(s):
    return len(WORD_RE.findall(s))


def normalize(s):
    return re.sub(r"\s+", " ", s.lower()).strip()


def sentences_regex(text):
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^\s*#{1,6}\s*", "", s)
        s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", s)
        if not s:
            continue
        for p in re.split(r"(?<=[.!?:])\s+(?=[A-Z0-9\"'\-])", s):
            p = p.strip()
            if p:
                out.append(p)
    return out


# --------------------------------------------------------------------------
# spaCy layer (optional)
# --------------------------------------------------------------------------
def load_nlp(model):
    if spacy is None:
        return None, "regex"
    try:
        return spacy.load(model, disable=["ner", "lemmatizer"]), model
    except Exception:
        try:
            nlp = spacy.blank("en")
            if "sentencizer" not in nlp.pipe_names:
                nlp.add_pipe("sentencizer")
            return nlp, "spacy.blank.en"
        except Exception:
            return None, "regex"


def conf(v):
    return round(max(0.05, min(0.99, v)), 2)


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------
def finding(rid, confidence, message, sentence, suggestion=None):
    r = RULES[rid]
    return {
        "rule_id": rid,
        "severity": r["severity"],
        "weight": r["weight"],
        "section": r["section"],
        "confidence": round(confidence, 2),
        "message": message,
        "sentence": sentence.strip()[:240],
        "suggestion": suggestion,
    }


def count_ci(text, phrases):
    low = text.lower()
    hits = []
    for ph in phrases:
        for _ in re.finditer(r"(?<![a-z])" + re.escape(ph) + r"(?![a-z])", low):
            hits.append(ph)
    return hits


# --------- parser-backed detectors (used only when a doc parser is present) ---
def passive_spacy(sent):
    deps = {tok.dep_ for tok in sent}
    morph = any("Voice=Pass" in str(tok.morph) for tok in sent)
    passish = {"nsubjpass", "auxpass", "agent", "nsubj:pass", "aux:pass", "obl:agent"} & deps
    if passish or morph:
        return True, conf(0.80 + (0.08 if morph else 0.0))
    return False, 0.0


def imperative_problem_spacy(sent):
    text = sent.text
    low = normalize(text)
    if low.startswith(("if ", "when ", "before ", "after ", "while ")) and "," in text:
        return None  # condition clause handled elsewhere; skip head
    roots = [tok for tok in sent if tok.dep_ == "ROOT"]
    if not roots:
        return None
    root = roots[0]
    # only a subject that is a direct child of the root counts; a subject inside
    # a subordinate clause (e.g. "if the queue is stalled") must not fire.
    subj = [tok for tok in sent
            if tok.dep_ in {"nsubj", "nsubjpass", "nsubj:pass"} and tok.head == root]
    if low.startswith("you "):
        return conf(0.84), "Remove 'you' and use the base verb."
    if root.pos_ == "VERB" and root.tag_ == "VB" and not subj:
        return None
    if subj and root.pos_ in {"VERB", "AUX"}:
        return conf(0.72), "Rewrite as a direct command."
    return None


def multi_instruction_spacy(sent):
    low = normalize(sent.text)
    if any(m in low for m in ("at the same time", "simultaneously", "in parallel")):
        return False, 0.0
    root_verbs = [t for t in sent if t.dep_ == "ROOT" and t.pos_ in {"VERB", "AUX"}]
    conj_verbs = [t for t in sent if t.pos_ == "VERB" and t.dep_ == "conj"]
    base_verbs = [t for t in sent if t.pos_ == "VERB" and t.tag_ == "VB"]
    hit = bool(root_verbs and conj_verbs and len(base_verbs) >= 2)
    return hit, conf(0.83 if hit else 0.0)


def noun_clusters_spacy(sent, glossary):
    out, current = [], []
    for tok in sent:
        if tok.pos_ in {"ADJ", "NOUN", "PROPN"} and not tok.is_stop:
            current.append(tok.text)
            continue
        if len(current) >= 4:
            cluster = " ".join(current)
            if not glossary.is_approved(cluster):
                out.append(cluster)
        current = []
    if len(current) >= 4:
        cluster = " ".join(current)
        if not glossary.is_approved(cluster):
            out.append(cluster)
    return out


# --------- regex fallbacks ---------
def multi_instruction_regex(text):
    low = normalize(text)
    if any(m in low for m in ("at the same time", "simultaneously", "in parallel")):
        return False, 0.0
    hit = len(re.findall(r"\b(?:and|then)\b", low)) >= 1 and wc(text) > 6 and bool(
        re.match(r"^[A-Z][a-z]+\b", text.strip())
    )
    return hit, conf(0.60 if hit else 0.0)


def noun_clusters_regex(text, glossary):
    out = []
    for m in re.finditer(r"\b(?:[A-Za-z][A-Za-z0-9-]*\s+){3,}[A-Za-z][A-Za-z0-9-]*\b", text):
        cluster = m.group(0).strip()
        if not glossary.is_approved(cluster):
            out.append(cluster)
    return out


# --------------------------------------------------------------------------
# Analyze
# --------------------------------------------------------------------------
def analyze(text, mode, glossary, model="en_core_web_sm", raw=None):
    raw = raw if raw is not None else text
    clean = strip_code(text)
    nlp, parser = load_nlp(model)
    degraded = parser in {"regex", "spacy.blank.en"}
    parser_backed = parser not in {"regex", "spacy.blank.en"}

    if nlp is not None:
        doc = nlp(clean)
        sent_objs = list(doc.sents)
        sent_texts = [s.text.strip() for s in sent_objs]
    else:
        sent_objs = None
        sent_texts = sentences_regex(clean)

    words = sum(wc(s) for s in sent_texts) or 1
    findings = []
    limit = 20 if mode == "strict" else 25
    long_rule = "SRE-5.1" if mode == "strict" else "SRE-6.3"

    for i, sent_text in enumerate(sent_texts):
        sent_obj = sent_objs[i] if sent_objs is not None else None
        low = normalize(sent_text)

        if wc(sent_text) > limit:
            findings.append(finding(long_rule, 0.99, f"Sentence has more than {limit} words.",
                                    sent_text, "Split the sentence."))

        if ";" in sent_text:
            findings.append(finding("SRE-8.1", 0.99, "Semicolon found.", sent_text,
                                    "Use a period or a vertical list."))

        if CONTRACTION_RE.search(sent_text):
            findings.append(finding("SRE-4.2", 0.98, "Contraction found.", sent_text,
                                    "Expand the contraction."))

        if NOMINALIZATION_RE.search(sent_text):
            findings.append(finding("SRE-3.7", 0.70, "Weak verb+noun phrase or nominalization.",
                                    sent_text, "Use a direct verb."))

        if re.search(rf"\b{BE}\s+\w+ing\b", sent_text, re.I):
            findings.append(finding("SRE-3.8", 0.70, "'-ing' main verb.", sent_text,
                                    "Use a simple tense."))

        for ph in count_ci(sent_text, MODAL_HEDGE):
            findings.append(finding("SRE-X.1", 0.95, f"Hedge / filler: '{ph}'.", sent_text,
                                    "Delete the phrase."))

        for term in count_ci(sent_text, MARKETING):
            if glossary.is_approved(term):
                continue
            findings.append(finding("SRE-X.1", 0.96, f"Marketing language: '{term}'.", sent_text,
                                    "Replace with a concrete technical statement."))

        for ph in count_ci(sent_text, list(BANNED.keys())):
            repl = BANNED[ph]
            sug = f"Prefer '{repl}'." if repl else "Delete the filler phrase."
            findings.append(finding("SRE-X.1", 0.95, f"Weak or banned phrase: '{ph}'.", sent_text, sug))

        for ph in count_ci(sent_text, list(PHRASAL.keys())):
            if glossary.is_approved(ph):
                continue
            findings.append(finding("SRE-9.3", 0.90, f"Phrasal verb: '{ph}'.", sent_text,
                                    f"Prefer '{PHRASAL[ph]}'."))

        for ph in count_ci(sent_text, list(INCLUSIVE.keys())):
            findings.append(finding("SRE-GR.7", 0.97, f"Non-inclusive expression: '{ph}'.", sent_text,
                                    f"Prefer '{INCLUSIVE[ph]}'."))

        # glossary: alias -> canonical
        for alias, canonical in glossary.alias_map.items():
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", low):
                findings.append(finding("SRE-1.11", 0.90, f"Alias '{alias}' used for '{canonical}'.",
                                        sent_text, f"Use '{canonical}' consistently."))

        # glossary: deprecated / discouraged terms
        for term, spec in glossary.avoid_map.items():
            if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", low):
                prefer = spec.get("prefer") or ""
                reason = spec.get("reason") or ""
                sug = (f"Prefer '{prefer}'. " if prefer else "") + reason
                findings.append(finding("SRE-1.12", 0.92, f"Discouraged term: '{term}'.",
                                        sent_text, sug.strip() or None))

        # noun clusters (needs POS tags; regex cannot do this reliably)
        if parser_backed:
            for cluster in noun_clusters_spacy(sent_obj, glossary):
                findings.append(finding("SRE-2.1", 0.75,
                                        f"Long noun cluster: '{cluster}'.", sent_text,
                                        "Shorten it, define a short form, or add it to the glossary."))

        # passive voice
        if parser_backed:
            is_pass, score = passive_spacy(sent_obj)
        else:
            m = re.search(rf"\b{BE}\s+(?:\w+ed|{PP_IRREG})\b", sent_text, re.I)
            is_pass, score = (bool(m), 0.55 if m else 0.0)
        if is_pass:
            findings.append(finding("SRE-3.6", score, "Possible passive voice.", sent_text,
                                    "Prefer active voice. Keep passive only if the actor is unknown."))

        # strict-mode procedural checks
        if mode == "strict":
            if re.search(r",\s*(if|when|unless)\b", low):
                findings.append(finding("SRE-5.4", 0.90, "Condition appears after the command.",
                                        sent_text, "Put the condition first."))
            if parser_backed:
                multi, mscore = multi_instruction_spacy(sent_obj)
                imp = imperative_problem_spacy(sent_obj)
            else:
                multi, mscore = multi_instruction_regex(sent_text)
                imp = None
                if re.match(r"^(You|The|This|That)\b", sent_text) and not low.startswith(
                    ("if ", "when ", "before ", "after ", "while ")
                ):
                    imp = (0.55, "Rewrite as a direct command.")
            if multi:
                findings.append(finding("SRE-5.2", mscore, "Multiple instructions in one sentence.",
                                        sent_text,
                                        "Split into steps unless the actions occur at the same time."))
            if imp:
                findings.append(finding("SRE-5.3", imp[0], "Instruction may not be imperative.",
                                        sent_text, imp[1]))

    # em dash (whole doc, raw)
    em = raw.count("—") + raw.count("–")
    for _ in range(em):
        findings.append(finding("SRE-8.2", 0.99, "Em dash or en dash found.", "",
                                "Use a period or restructure the sentence."))

    # long paragraphs
    for para in re.split(r"\n\s*\n", raw):
        if para.strip() and len(sentences_regex(strip_code(para))) > 6:
            findings.append(finding("SRE-6.6", 0.90, "Paragraph has more than six sentences.",
                                    para.strip()[:120], "Split the paragraph."))

    weighted = round(sum(f["weight"] * f["confidence"] for f in findings), 2)
    normalized = weighted / max(words / 100.0, 1.0)
    compliance = round(max(0.0, 100.0 - normalized), 1)

    sections = {m["section"] for m in RULES.values()}
    cat_points = {s: 0.0 for s in sections}
    for f in findings:
        cat_points[f["section"]] = cat_points.get(f["section"], 0.0) + f["weight"] * f["confidence"]
    category_scores = {s: round(max(0.0, 100.0 - p * 4), 1) for s, p in cat_points.items()}

    counts = {}
    for f in findings:
        counts[f["rule_id"]] = counts.get(f["rule_id"], 0) + 1

    return {
        "mode": mode,
        "parser": parser,
        "degraded_mode": degraded,
        "words": words,
        "sentences": len(sent_texts),
        "glossary_domains": glossary.domains,
        "total": len(findings),
        "total_per100w": round(len(findings) * 100.0 / words, 2),
        "weighted_points": weighted,
        "compliance_score": compliance,
        "category_scores": category_scores,
        "counts": counts,
        "findings": findings,
    }


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def format_report(rep, explain):
    lines = [
        f"Mode: {rep['mode']}   Parser: {rep['parser']}"
        + ("  (degraded: install spaCy for parser checks)" if rep["degraded_mode"] else ""),
        f"Words: {rep['words']}   Sentences: {rep['sentences']}   "
        f"Glossary domains: {len(rep['glossary_domains'])}",
        f"Findings: {rep['total']}   Per 100 words: {rep['total_per100w']}   "
        f"Compliance: {rep['compliance_score']}/100",
        "",
    ]
    if not rep["findings"]:
        lines.append("No findings.")
        return "\n".join(lines)
    lines.append("Findings by rule:")
    for rid in sorted(rep["counts"]):
        lines.append(f"  {rid:9} x{rep['counts'][rid]:<3} {RULES[rid]['title']} "
                     f"[{RULES[rid]['severity']}]")
    if explain:
        lines.append("")
        lines.append("Detail:")
        for i, f in enumerate(rep["findings"], 1):
            lines.append(f"{i}. [{f['rule_id']}] {f['message']}  "
                         f"(sev {f['severity']}, conf {f['confidence']})")
            if f["sentence"]:
                lines.append(f"     > {f['sentence']}")
            if f["suggestion"]:
                lines.append(f"     fix: {f['suggestion']}")
    return "\n".join(lines)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # readable em dashes on Windows
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="STE-flavored writing linter for software / SRE / DevOps prose.")
    ap.add_argument("input", nargs="*", help="Files or globs. Reads stdin if omitted.")
    ap.add_argument("--mode", choices=["strict", "flavored"], default="flavored")
    ap.add_argument("--strict", action="store_true", help="Shortcut for --mode strict.")
    ap.add_argument("--explain", action="store_true", help="Show each finding.")
    ap.add_argument("--json", action="store_true", help="Emit JSON.")
    ap.add_argument("--glossary", default=None, help="Glossary JSON path (default: glossary.json by the skill).")
    ap.add_argument("--model", default="en_core_web_sm", help="spaCy model name.")
    ap.add_argument("--ci", action="store_true", help="Exit nonzero on any critical finding or low score.")
    ap.add_argument("--threshold", type=float, default=85.0, help="CI compliance threshold (default 85).")
    ap.add_argument("--fix", action="store_true",
                    help="Apply safe lexical fixes (contractions, semicolons, dashes, banned words). "
                         "Protects all code spans. Prints the fixed text unless --write is set.")
    ap.add_argument("--write", action="store_true", help="With --fix, overwrite each input file in place.")
    args = ap.parse_args()

    if args.fix:
        return run_fix(args)

    mode = "strict" if args.strict else args.mode
    glossary = Glossary.load(args.glossary or default_glossary_path())

    # stdin
    if not args.input:
        raw = sys.stdin.read()
        rep = analyze(raw, mode, glossary, args.model, raw=raw)
        print(rep_to_out(rep, args))
        return ci_exit(rep, args)

    files = []
    for f in args.input:
        files += sorted(glob.glob(f)) if any(c in f for c in "*?[") else [f]

    worst = 0
    if len(files) == 1 or args.json or args.explain:
        for f in files:
            with open(f, encoding="utf-8") as fh:
                raw = fh.read()
            rep = analyze(raw, mode, glossary, args.model, raw=raw)
            if len(files) > 1:
                print(f"=== {f} ===")
            print(rep_to_out(rep, args))
            worst = max(worst, ci_status(rep, args))
    else:
        # compact one-line-per-file summary
        for f in files:
            with open(f, encoding="utf-8") as fh:
                raw = fh.read()
            rep = analyze(raw, mode, glossary, args.model, raw=raw)
            crit = sum(1 for x in rep["findings"] if x["severity"] == "critical")
            print(f"{os.path.basename(f):32} words={rep['words']:5d} "
                  f"findings={rep['total']:3d} per100w={rep['total_per100w']:6.2f} "
                  f"compliance={rep['compliance_score']:5.1f} critical={crit}")
            worst = max(worst, ci_status(rep, args))
    return worst if args.ci else 0


def run_fix(args):
    if not args.input:
        sys.stdout.write(safe_fix(sys.stdin.read()))
        return 0
    files = []
    for f in args.input:
        files += sorted(glob.glob(f)) if any(c in f for c in "*?[") else [f]
    for f in files:
        with open(f, encoding="utf-8") as fh:
            fixed = safe_fix(fh.read())
        if args.write:
            with open(f, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(fixed)
            print(f"fixed (in place): {f}")
        else:
            sys.stdout.write(fixed)
    return 0


def rep_to_out(rep, args):
    return json.dumps(rep, indent=2, ensure_ascii=False) if args.json else format_report(rep, args.explain)


def ci_status(rep, args):
    crit = any(f["severity"] == "critical" for f in rep["findings"])
    return 1 if (crit or rep["compliance_score"] < args.threshold) else 0


def ci_exit(rep, args):
    return ci_status(rep, args) if args.ci else 0


if __name__ == "__main__":
    raise SystemExit(main())
