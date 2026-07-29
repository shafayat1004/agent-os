from agentos.grades import grade_for
from agentos.result import CheckResult, Finding

_REQUIRED = ["Commands", "Invariants", "Forbidden", "Approval gates", "Scope",
             "Conventions"]


def _headings(text):
    headings = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            headings.append(stripped[3:].strip())
    return headings


def check_rules(path, soft=150, hard=250):
    with open(path) as rules_file:
        text = rules_file.read()
    nonblank_lines = [line for line in text.splitlines() if line.strip()]
    findings = []
    line_count = len(nonblank_lines)
    if line_count > hard:
        findings.append(Finding("error", "rule file has %d lines, over hard cap %d"
                                % (line_count, hard)))
    elif line_count > soft:
        findings.append(Finding("warn", "rule file has %d lines, over soft cap %d"
                                % (line_count, soft)))
    # Match required sections against '##' headings only, so a section name in
    # body text cannot count as present. A heading may extend the name (for
    # example "Conventions (pointer)"), so match on prefix.
    heading_texts = [heading.lower() for heading in _headings(text)]
    section_positions = {}
    for section in _REQUIRED:
        section_lower = section.lower()
        position = next((index for index, heading in enumerate(heading_texts)
                         if heading == section_lower
                         or heading.startswith(section_lower + " ")), None)
        if position is None:
            findings.append(Finding("warn", "missing section '%s'" % section))
        else:
            section_positions[section] = position
    present_sections = [section for section in _REQUIRED if section in section_positions]
    if present_sections != sorted(present_sections, key=section_positions.get):
        findings.append(Finding("warn", "sections out of required order: expected %s"
                                % ", ".join(_REQUIRED)))
    return CheckResult("rules", grade_for("rules"), findings)
