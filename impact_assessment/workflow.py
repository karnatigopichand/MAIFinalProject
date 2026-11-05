"""Bounded orchestration and durable local run artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

from .agents import ImpactInvestigationAgent, RiskAndReportAgent, TechnicalDebtAgent, Trace
from .models import Assessment, RunContext
from .store import LocalEvidenceStore


def _plain(value):
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), list):
            return " ".join(_plain(v) for v in value["content"])
        return " ".join(_plain(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_plain(v) for v in value)
    if value is None:
        return ""
    return str(value)


def ticket_from_jira(issue: dict, criteria_field="customfield_10000") -> dict:
    fields = issue.get("fields", {})
    criteria = fields.get(criteria_field) or []
    if isinstance(criteria, str):
        criteria = [criteria]
    return {
        "ticket_id": issue.get("key", "LOCAL-1"),
        "ticket_version": str(fields.get("updated") or issue.get("id") or "1"),
        "summary": _plain(fields.get("summary", "")),
        "description": _plain(fields.get("description", "")),
        "acceptance_criteria": [_plain(x) for x in criteria if _plain(x).strip()],
    }


def render_report(assessment: Assessment) -> str:
    ctx = assessment.context
    lines = [
        f"# Impact assessment: {ctx.ticket_id}", "",
        f"**Status:** {assessment.status}  ",
        f"**Snapshot:** `{ctx.snapshot_id}`  ",
        f"**Commit:** `{next(iter(ctx.repositories.values()), 'unknown')}`  ",
        f"**Summary:** {assessment.summary}", "",
        "## Repository impacts", "",
        "| Repository | Classification | Components | Evidence |",
        "|---|---|---|---|",
    ]
    if assessment.impacts:
        for finding in assessment.impacts:
            refs = ", ".join(f"`{eid}`" for eid in finding.evidence_ids)
            lines.append(f"| `{finding.repository}` | {finding.classification} | {finding.component} | {refs} |")
    else:
        lines.append("| No supported impact found | — | — | — |")
    for finding in assessment.impacts:
        lines.extend(["", f"### {finding.repository}: {finding.claim}", "", finding.business_relevance])
        for uncertainty in finding.uncertainties:
            lines.append(f"- Uncertainty: {uncertainty}")
    lines.extend(["", "## Dependency paths", ""])
    if assessment.dependency_paths:
        for path in assessment.dependency_paths:
            edge_labels = [f"{edge['source']} -[{edge['relationship']}:{edge.get('detail','')}]-> {edge['target']}"
                           for edge in path["edges"]]
            lines.append("- " + " → ".join(edge_labels) + " (evidence: " + ", ".join(path["evidence_ids"]) + ")")
    else:
        lines.append("No cross-repository path was confirmed in the local snapshot.")
    lines.extend(["", "## Business and technical risks", ""])
    if assessment.risks:
        for risk in assessment.risks:
            lines.extend([f"- **{risk.severity.title()} severity:** {risk.failure_mode}",
                          f"  Consequence: {risk.business_consequence}",
                          f"  Uncertainty: {risk.uncertainty}",
                          f"  Validate: {'; '.join(risk.recommended_validation)}",
                          f"  Evidence: {', '.join(risk.evidence_ids)}"])
    else:
        lines.append("No specific risk was verified from retrieved evidence.")
    lines.extend(["", "## Technical-debt candidates", ""])
    decisions = assessment.debt_assessments
    candidates = [x for x in decisions if x.disposition != "do_not_recommend"]
    if candidates:
        for item in candidates:
            total = "unknown" if item.total_hours is None else f"{item.total_hours:g} h"
            tests = ", ".join(item.shared_tests) if item.shared_tests else "none verified"
            lines.append(f"- **{item.repository}/{item.debt_id} — {item.title}: {item.disposition}**; effort {total}; candidate shared tests: {tests}. {item.reason}")
    else:
        lines.append("No related debt item qualified for recommendation.")
    exclusions = [x for x in decisions if x.disposition == "do_not_recommend"]
    if exclusions:
        lines.extend(["", "Excluded candidates:"])
        for item in exclusions:
            lines.append(f"- `{item.repository}/{item.debt_id}` — {item.reason}")
    lines.extend(["", "## Clarification questions", ""])
    lines.extend([f"- {question}" for question in assessment.questions] or ["None identified."])
    lines.extend(["", "## Limitations", ""])
    lines.extend([f"- {limitation}" for limitation in assessment.limitations] or ["- Local evidence snapshot; no live Jira, Pinecone, Neo4j, LangGraph, or model service was used."])
    lines.extend(["", "## Evidence index", ""])
    for evidence in assessment.evidence:
        ref = f"{evidence.repository}@{evidence.commit}:{evidence.path}:{evidence.line_start}-{evidence.line_end}"
        lines.append(f"- `{evidence.evidence_id}` — `{ref}` ({evidence.document_type}, {evidence.section})")
    lines.append("")
    return "\n".join(lines)


class AssessmentWorkflow:
    def __init__(self, workspace: Path, max_hours=3.0, tool_budget=24, graph_hops=3):
        self.workspace = workspace.resolve()
        self.state_dir = self.workspace / ".impact_assessment"
        backend = os.environ.get("IMPACT_EVIDENCE_BACKEND", "local").lower()
        if backend == "local":
            self.store = LocalEvidenceStore(self.workspace, self.state_dir)
        elif backend == "hosted":
            from .integrations.hosted_store import HostedEvidenceStore
            self.store = HostedEvidenceStore(self.workspace, self.state_dir)
        else:
            raise ValueError("IMPACT_EVIDENCE_BACKEND must be 'local' or 'hosted'")
        self.max_hours, self.tool_budget, self.graph_hops = max_hours, tool_budget, graph_hops

    def run(self, ticket: dict, rebuild_snapshot=True) -> Assessment:
        snapshot = self.store.build_snapshot() if rebuild_snapshot else self.store.load_current()
        ticket_id = ticket.get("ticket_id", "LOCAL-1")
        ticket_version = str(ticket.get("ticket_version", "1"))
        run_material = f"{ticket_id}\0{ticket_version}\0{snapshot['snapshot_id']}"
        run_id = hashlib.sha256(run_material.encode()).hexdigest()[:24]
        context = RunContext(run_id, ticket_id, ticket_version, snapshot["snapshot_id"],
                             snapshot["repositories"], limits={"tool_calls": self.tool_budget,
                             "graph_hops": self.graph_hops, "verification_rounds": 2})
        trace = Trace(run_id)
        trace.add("coordinator", "routing", "start-assessment",
                  {"ticket_id": ticket_id, "ticket_version": ticket_version, "snapshot_id": snapshot["snapshot_id"]})

        investigator = ImpactInvestigationAgent(self.store, trace, self.tool_budget, self.graph_hops)
        investigation = investigator.investigate(ticket)
        verification_requests = []
        for verification_round in range(context.limits["verification_rounds"] + 1):
            debt = TechnicalDebtAgent(self.store, trace, self.max_hours).assess(investigation)
            status, risks, questions, limitations, evidence, verification_requests = RiskAndReportAgent(
                self.store, trace).review(ticket, investigation, debt)
            if not verification_requests or verification_round >= context.limits["verification_rounds"]:
                break
            trace.add("coordinator", "routing", "bounded-reinvestigation",
                      {"round": verification_round + 1,
                       "round_limit": context.limits["verification_rounds"],
                       "request_count": len(verification_requests)}, outcome="reinvestigating")
            investigation = investigator.investigate(ticket, targeted_queries=verification_requests)
            trace.add("coordinator", "routing", "reinvestigation-complete",
                      {"round": verification_round + 1,
                       "finding_count": len(investigation["impacts"])})
        if verification_requests:
            status = "partial"
            limitations.append("Targeted evidence verification reached the bounded reinvestigation limit; unsupported findings were not promoted.")
            if not questions:
                questions.append("Can you clarify the affected service, field, or expected behavior so the evidence search can be narrowed?")
        if not investigation["paths"]:
            limitations.append("The local dependency graph did not confirm a multi-service path for the ticket's evidence; possible impacts are not promoted to confirmed paths.")
        if not investigation["impacts"]:
            status = "partial"
            limitations.append("No impact finding had evidence in source or implementation-reviewed documentation.")
        if snapshot.get("debt_validation_errors"):
            limitations.append(f"{len(snapshot['debt_validation_errors'])} technical-debt metadata validation issue(s) were found; malformed/duplicate items are not eligible.")
        if investigation.get("budget_exhausted"):
            status = "partial"
            limitations.append("The tool-call budget was exhausted before the complete search space was inspected.")

        assessment = Assessment(context, status,
            ticket.get("summary", "Untitled requirement"), investigation["impacts"],
            investigation["paths"], debt, risks, questions, _dedupe(limitations), evidence, trace.events)
        assessment.report_markdown = render_report(assessment)
        self.persist(assessment)
        return assessment

    def persist(self, assessment: Assessment):
        run_dir = self.state_dir / "runs" / assessment.context.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "assessment.json").write_text(json.dumps(assessment.to_dict(), indent=2), encoding="utf-8")
        (run_dir / "report.md").write_text(assessment.report_markdown, encoding="utf-8")
        with (run_dir / "trace.ndjson").open("w", encoding="utf-8") as stream:
            for event in assessment.trace:
                stream.write(json.dumps(event.__dict__, sort_keys=True) + "\n")


def _dedupe(values):
    return list(dict.fromkeys(values))
