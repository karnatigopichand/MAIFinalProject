"""Versioned data contracts shared by the assessment agents."""
from dataclasses import asdict, dataclass, field
from typing import Any


CONTRACT_VERSION = "1.0"


@dataclass
class RunContext:
    run_id: str
    ticket_id: str
    ticket_version: str
    snapshot_id: str
    repositories: dict[str, str]
    contract_version: str = CONTRACT_VERSION
    limits: dict[str, int] = field(default_factory=lambda: {"tool_calls": 24, "graph_hops": 3, "verification_rounds": 2})


@dataclass
class Evidence:
    evidence_id: str
    repository: str
    commit: str
    path: str
    line_start: int
    line_end: int
    excerpt: str
    document_type: str
    section: str = ""
    extraction_method: str = "local_snapshot"


@dataclass
class DependencyEdge:
    edge_id: str
    source: str
    target: str
    relationship: str
    evidence_ids: list[str]
    detail: str = ""
    classification: str = "explicit"


@dataclass
class DebtItem:
    repository: str
    debt_id: str
    title: str
    status: str
    components: list[str]
    implementation_hours: float | None
    testing_hours: float | None
    estimate_basis: str
    relevant_tests: list[str]
    evidence_id: str
    path: str
    body: str


@dataclass
class TraceEvent:
    timestamp: str
    run_id: str
    agent: str
    event_type: str
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    outcome: str = "ok"
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class ImpactFinding:
    finding_id: str
    repository: str
    classification: str
    component: str
    claim: str
    business_relevance: str
    evidence_ids: list[str]
    uncertainties: list[str] = field(default_factory=list)


@dataclass
class DebtAssessment:
    repository: str
    debt_id: str
    title: str
    disposition: str
    implementation_hours: float | None
    testing_hours: float | None
    total_hours: float | None
    estimate_basis: str
    overlap_evidence: list[str]
    shared_tests: list[str]
    additional_tests: list[str]
    reason: str


@dataclass
class Risk:
    failure_mode: str
    business_consequence: str
    severity: str
    uncertainty: str
    evidence_ids: list[str]
    recommended_validation: list[str]


@dataclass
class CodeRecommendation:
    repository: str
    title: str
    recommendation: str
    rationale: str
    code_example: str
    evidence_ids: list[str] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Assessment:
    context: RunContext
    status: str
    summary: str
    impacts: list[ImpactFinding]
    dependency_paths: list[dict[str, Any]]
    debt_assessments: list[DebtAssessment]
    risks: list[Risk]
    questions: list[str]
    limitations: list[str]
    evidence: list[Evidence]
    trace: list[TraceEvent]
    report_markdown: str = ""
    langfuse_trace_status: str = "not_configured"
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None
    code_recommendations: list[CodeRecommendation] = field(default_factory=list)
    code_recommendation_status: str = "not_configured"
    classification: dict[str, Any] | None = None
    classification_status: str = "not_configured"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
