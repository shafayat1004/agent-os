from dataclasses import dataclass, field


@dataclass
class Finding:
    level: str  # "error" or "warn"
    message: str


@dataclass
class CheckResult:
    name: str
    grade: str
    findings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(finding.level != "error" for finding in self.findings)
