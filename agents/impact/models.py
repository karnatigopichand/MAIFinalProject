"""Typed, serializable artifacts shared by the impact agent and its adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    summary: str
    description: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    version: str = "local"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Ticket":
        criteria = value.get("acceptance_criteria", ())
        if isinstance(criteria, str):
            criteria = (criteria,)
        return cls(
            ticket_id=str(value.get("ticket_id") or value.get("key") or "PROPOSED-CHANGE"),
            summary=str(value.get("summary", "")).strip(),
            description=str(value.get("description", "")).strip(),
            acceptance_criteria=tuple(str(item) for item in criteria),
            version=str(value.get("version") or value.get("updated") or "local"),
        )


@dataclass(frozen=True)
class Requirement:
    requested_behavior: str
    acceptance_criteria: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    ambiguities: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunContext:
    run_id: str
    ticket_id: str
    ticket_version: str
    snapshot_id: str
    repo_manifest: dict[str, str]
    max_tool_calls: int = 20
    max_graph_hops: int = 3


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    repository: str
    commit: str
    path: str
    line_start: int
    line_end: int
    excerpt: str
    document_type: str
    method: str


@dataclass(frozen=True)
class DependencyPath:
    nodes: tuple[str, ...]
    relationships: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    certainty: str = "explicit"


@dataclass(frozen=True)
class ImpactFinding:
    finding_id: str
    repository: str
    component: str
    classification: str
    claim: str
    business_relevance: str
    evidence_ids: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()


@dataclass(frozen=True)
class InvestigationResult:
    context: RunContext
    requirement: Requirement
    status: str
    findings: tuple[ImpactFinding, ...] = ()
    dependency_paths: tuple[DependencyPath, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    related_issue_keys: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    trace: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# Impact investigation: {self.context.ticket_id}",
            "",
            f"**Status:** {self.status}  ",
            f"**Snapshot:** `{self.context.snapshot_id}`  ",
            f"**Requested behavior:** {self.requirement.requested_behavior}",
            "",
            "## Findings",
        ]
        if not self.findings:
            lines.append("No impact was established from the inspected evidence.")
        for finding in self.findings:
            lines.append(f"- **{finding.repository} / {finding.component} — {finding.classification}:** {finding.claim}")
            if finding.evidence_ids:
                lines.append(f"  Evidence: {', '.join(f'`{item}`' for item in finding.evidence_ids)}")
            if finding.uncertainties:
                lines.append(f"  Uncertainty: {'; '.join(finding.uncertainties)}")
        lines.extend(["", "## Dependency paths"])
        if not self.dependency_paths:
            lines.append("No dependency path was established.")
        for path in self.dependency_paths:
            lines.append(f"- {' -- '.join(path.nodes)} ({path.certainty}; {', '.join(path.evidence_ids)})")
        lines.extend(["", "## Questions and limitations"])
        for question in self.questions:
            lines.append(f"- Question: {question}")
        for limitation in self.limitations:
            lines.append(f"- Limitation: {limitation}")
        if not self.questions and not self.limitations:
            lines.append("None identified.")
        return "\n".join(lines) + "\n"
