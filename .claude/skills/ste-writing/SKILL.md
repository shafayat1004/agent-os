---
name: ste-writing
description: Rewrite prose (docs, READMEs, PR descriptions, error messages, release notes, runbooks, incident updates, postmortems, tickets, and comments, but never code) into ASD-STE100-aligned Simplified Technical English for software, SRE, DevOps, and IT. Use when asked to make writing not sound like AI, make docs clear or plain, enforce a controlled writing style, or write technical documentation that reads human. Two modes, strict (procedures and safety) and STE-flavored (general prose). A doc-verified domain glossary approves technical terms and catches deprecated or non-inclusive ones.
---

# ste-writing

Write prose in ASD-STE100-aligned Simplified Technical English for software work. This covers documentation, READMEs, pull-request text, error messages, release notes, runbooks, incident updates, postmortems, tickets, and comments.

This skill is an adaptation, not a claim of certified STE compliance. It has two goals:

1. Keep the official STE core where it fits software writing.
2. Add local rules for SRE, DevOps, and anti-slop cleanup, plus a domain glossary.

It does not apply to marketing copy, essays, or anything that needs a voice. STE strips voice on purpose. It also does not apply to code (see Code awareness).

## Scope

- Default language: en-US.
- Default audience: engineers, operators, reviewers, and support staff.
- In scope: prose in Markdown, plain text, doc comments, or ticket text.
- Out of scope: code, shell commands, config keys, API field names, identifiers, file paths, URLs, SQL, and literal log text.

## Modes

- **strict**: procedures, runbooks, incident steps, change plans, break-glass steps, safety text, and user-facing error messages. Apply every rule and the 20-word cap. Use the imperative. Put the condition first. One instruction per sentence.
- **STE-flavored**: general prose: READMEs, architecture notes, PR descriptions, release notes, and postmortem narrative. Apply the sentence, paragraph, active-voice, and no-phrasal-verb discipline with a 25-word cap. Allow more domain vocabulary. Still forbid filler, hype, contractions, and avoidable ambiguity.

## Rule catalog

Use these IDs in explanations and reviews. Severity drives CI gating. Weight drives the compliance score. The linter reports the same IDs.

| ID | Base | Severity | Weight | Rule |
|---|---|---|---:|---|
| SRE-1.11 | STE 1.11 / 9.4 | major | 5 | Use one canonical name for one thing. Replace glossary aliases. |
| SRE-1.12 | local | major | 5 | Replace deprecated or non-inclusive terms flagged by the glossary. |
| SRE-2.1 | STE 2.1 / 2.2 | major | 5 | Keep noun clusters short. Define a long technical noun once, then shorten it. |
| SRE-3.6 | STE 3.6 | critical | 8 | Prefer active voice. Keep passive only when the actor is unknown in descriptive text. |
| SRE-3.7 | STE 3.7 | major | 5 | Prefer a direct verb over a weak verb+noun phrase. |
| SRE-3.8 | STE 3.x | major | 4 | Do not use an "-ing" main verb where a simple tense works. |
| SRE-4.2 | STE 4.2 | major | 4 | Do not use contractions. |
| SRE-4.5 | STE 4.5 | minor | 2 | Use articles where normal English needs them. |
| SRE-5.1 | STE 5.1 | major | 5 | In strict mode, keep each sentence within 20 words. |
| SRE-5.2 | STE 5.2 | critical | 8 | In strict mode, one instruction per sentence unless the actions happen at the same time. |
| SRE-5.3 | STE 5.3 | critical | 8 | In strict mode, write each instruction as a command. |
| SRE-5.4 | STE 5.4 | major | 5 | Put the condition before the command. |
| SRE-6.3 | STE 6.3 | major | 4 | In flavored mode, keep each sentence within 25 words. |
| SRE-6.6 | STE 6.6 | minor | 2 | Keep paragraphs at six sentences or fewer. |
| SRE-8.1 | STE 8.1 | major | 4 | Do not use semicolons. |
| SRE-8.2 | local | minor | 2 | Do not use em dashes or en dashes. |
| SRE-9.3 | STE 9.3 | major | 4 | Avoid phrasal verbs unless the glossary approves the exact expression. |
| SRE-GR.7 | STE GR-7 | minor | 3 | Use inclusive language. |
| SRE-X.1 | local | major | 4 | Remove hype, filler, and AI-style padding. |

## Writing rules

WORDS
- Use one name for one thing. Do not call the same item by two names.
- Use the short common word: start (not begin/commence/initiate), use (not utilize/leverage), help (not facilitate), make sure (not ensure), before (not prior to), after (not subsequent to), get (not obtain/acquire), show (not demonstrate), also (not additionally/furthermore/moreover).
- Give each word one meaning. "fall" means to move down, not to decrease.
- No marketing adjectives: seamless, robust, powerful, cutting-edge, effortless, world-class, next-generation, revolutionary.
- American spelling.

VERBS
- Use the active voice. Write "the parser reads the file", not "the file is read by the parser".
- Use a verb for an action. Write "analyze the log", not "perform an analysis of the log".
- No stacked auxiliaries. Write "this improves X", not "it is important to note that this may help to improve X".
- No "-ing" main verb where a simple tense works.

SENTENCES
- One main idea per sentence. Max 20 words (strict), max 25 (flavored).
- No contractions. Use articles: a, an, the, this, these.

PUNCTUATION
- No semicolons. Write two sentences.
- No em dash or en dash. STE bans only the semicolon, but this workspace also removes the em dash as a slop marker.

STRUCTURE
- One topic per paragraph, max six sentences.
- For steps, use a numbered vertical list. One action per item. Imperative form. Put the condition before its command.

Write only the requested text. No preamble, no summary, no closing remarks.

## Terminology policy

ONE NAME FOR ONE THING
- Use one canonical name in a document. Do not switch names for the same concept.
- Example: use `pod`, not `pod` in one line and `instance` in the next, unless the glossary says they differ.

GLOSSARY-FIRST TECHNICAL TERMS
- A domain glossary approves technical nouns and verbs that are normal in software work. The linter does not flag approved terms.
- The glossary maps aliases to one canonical name. Example: `k8s` maps to `Kubernetes`.
- The glossary lists deprecated or non-inclusive terms with a preferred replacement. Example: `master node` maps to `control plane node`.

LONG TECHNICAL NAMES
- Keep multi-word nouns short. If a technical noun runs longer than three words:
  1. Write it in full the first time.
  2. Define a shorter approved form.
  3. Use the short form after that.

## Domain glossary

`glossary.json` holds doc-verified controlled terminology for 16 domains: azure, gcp, aws, datadog, kubernetes, docker, git, jira, opsgenie, csharp, fsharp, dotnet, go, javascript, oop, and fp. Each domain records the source URLs used to verify its terms.

Each domain block has four parts:
- `technical_nouns` and `technical_verbs`: approved terms. The linter does not flag them.
- `canonical`: alias-to-canonical mappings for one name for one thing.
- `avoid`: deprecated or non-inclusive terms with a preferred replacement and a reason.

The linter loads the glossary and curates it for precision. It drops generic single words, ambiguous cross-domain acronyms, and pure-casing entries, so it does not flag the correct form. The full file stays as the reference of record.

To extend the glossary:
1. Add the term under the right domain and part.
2. Add a source URL to that domain's `sources`.
3. Keep exact canonical casing from the vendor docs.
4. Re-run the linter to confirm no false positives appear.

## Machine linter

`scripts/ste-lint.py` checks the mechanical subset of these rules and reports the rule IDs above. It has two layers:

- **Regex layer**: the default. No third-party dependency, so `uv run` executes it with no setup.
- **spaCy layer**: optional. If spaCy and an English model are installed, the linter uses the parser for passive voice, imperative form, noun clusters, and multiple-instruction detection. Without spaCy it falls back to regex and prints `degraded`.

Run the linter (regex, no setup):

```
uv run .claude/skills/ste-writing/scripts/ste-lint.py your-draft.md          # flavored
uv run .claude/skills/ste-writing/scripts/ste-lint.py --strict runbook.md     # strict
uv run .claude/skills/ste-writing/scripts/ste-lint.py --explain your-draft.md # show each finding
uv run .claude/skills/ste-writing/scripts/ste-lint.py --json your-draft.md    # machine output
uv run .claude/skills/ste-writing/scripts/ste-lint.py --ci docs/*.md          # exit nonzero below threshold
```

Enable the optional parser layer one time. The `spacy download` command fails in some environments (missing `click`, or it cannot find a venv), so install the model wheel directly. Match the model version to the installed spaCy (spaCy 3.8.x uses en_core_web_sm-3.8.0):

```
uv venv .venv --python 3.12
uv pip install --python .venv spacy click
uv pip install --python .venv "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

Then run the linter with that interpreter so it loads spaCy:

```
.venv/Scripts/python .claude/skills/ste-writing/scripts/ste-lint.py --strict runbook.md   # Windows
.venv/bin/python     .claude/skills/ste-writing/scripts/ste-lint.py --strict runbook.md    # macOS or Linux
```

The plain `uv run` path stays regex-only, because the script declares no dependencies and needs no install. The header prints `Parser: en_core_web_sm` when the parser layer is active, and `degraded` when it falls back to regex.

The report gives a compliance score out of 100 and findings per 100 words. Higher score is cleaner. Run the linter before and after a rewrite. The score delta is the signal. In CI, `--ci` exits nonzero on any critical finding or below the compliance threshold (default 85).

The linter is not a certified STE checker. It is a deterministic proxy for the machine-checkable part of the standard.

## Self-lint (run before returning text)

1. Any sentence over the mode cap (20 strict, 25 flavored)? Split it.
2. Any semicolon or em dash? Replace with a period.
3. Any contraction? Expand it.
4. Any passive voice with a known actor? Make it active.
5. Any "-ing" main verb, nominalization ("perform an analysis"), or phrasal verb ("spin up")? Replace with a plain verb.
6. Same thing named two ways? Pick one name. Replace any glossary alias.
7. Any deprecated or non-inclusive term? Use the glossary replacement.
8. In strict mode: is each step a command, one instruction, with the condition first?

## Limitations

This skill improves the form of technical writing. It does not guarantee that the content is correct. It does not replace a domain expert, an architecture review, or the project glossary owner. It is STE-aligned, not formally certified.

Full STE also needs human judgment (the right technical noun, whether a sentence "makes good sense"). A checker cannot certify that, and slop is not about that. This skill fixes the FORM of slop. It cannot make a hollow paragraph true.

Free official standard (do not paste it in full; it is copyrighted): https://asd-ste100.org

Adaptation source and video companion: https://github.com/woosal1337/blog/tree/main/videos/ep01-the-cure-for-ai-slop
