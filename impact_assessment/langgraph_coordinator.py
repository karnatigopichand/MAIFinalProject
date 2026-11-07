"""Optional LangGraph adapter for the same three independently typed agents."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, TypedDict
import hashlib

from .agents import ImpactInvestigationAgent, RiskAndReportAgent, TechnicalDebtAgent, Trace
from .models import (Assessment, DebtAssessment, Evidence, ImpactFinding, Risk,
                     RunContext, TraceEvent)
from .workflow import AssessmentWorkflow, render_report


class AgentState(TypedDict, total=False):
    workspace: str
    ticket: dict[str, Any]
    context: dict[str, Any]
    snapshot_id: str
    run_id: str
    investigation: dict[str, Any]
    debt: list[dict[str, Any]]
    review: dict[str, Any]
    trace: list[dict[str, Any]]
    assessment: dict[str, Any]
    verification_requests: list[dict[str, Any]]
    verification_round: int


def build_graph(workspace: Path, max_hours=3.0, tool_budget=24, graph_hops=3):
    """Build the target LangGraph coordinator while keeping agent nodes reusable."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install requirements-agent-runtime.txt to use the LangGraph coordinator") from exc

    root = workspace.resolve()
    workflow = AssessmentWorkflow(root, max_hours, tool_budget, graph_hops)
    store = workflow.store

    def restore_trace(state):
        trace = Trace(state["run_id"])
        trace.events = [TraceEvent(**event) for event in state.get("trace", [])]
        return trace

    def initialize(state: AgentState):
        snapshot = store.build_snapshot()
        ticket = state["ticket"]
        ticket_id = ticket.get("ticket_id", "LOCAL-1")
        version = str(ticket.get("ticket_version", "1"))
        run_id = hashlib.sha256(f"{ticket_id}\0{version}\0{snapshot['snapshot_id']}".encode()).hexdigest()[:24]
        context = RunContext(run_id, ticket_id, version, snapshot["snapshot_id"], snapshot["repositories"],
                             limits={"tool_calls": tool_budget, "graph_hops": graph_hops, "verification_rounds": 2})
        trace = Trace(run_id)
        trace.add("coordinator", "routing", "start-assessment",
                  {"ticket_id": ticket_id, "ticket_version": version, "snapshot_id": snapshot["snapshot_id"]})
        return {"workspace": str(root), "context": asdict(context), "snapshot_id": snapshot["snapshot_id"],
                "run_id": run_id, "trace": [event.__dict__ for event in trace.events],
                "verification_requests": [], "verification_round": 0}

    def impact_node(state: AgentState):
        trace = restore_trace(state)
        result = ImpactInvestigationAgent(store, trace, tool_budget, graph_hops).investigate(state["ticket"])
        result["impacts"] = [asdict(item) for item in result["impacts"]]
        return {"investigation": result, "trace": [event.__dict__ for event in trace.events]}

    def debt_node(state: AgentState):
        trace = restore_trace(state)
        investigation = dict(state["investigation"])
        investigation["impacts"] = [ImpactFinding(**item) for item in investigation["impacts"]]
        result = TechnicalDebtAgent(store, trace, max_hours).assess(investigation)
        return {"debt": [asdict(item) for item in result], "trace": [event.__dict__ for event in trace.events]}

    def review_node(state: AgentState):
        trace = restore_trace(state)
        investigation = dict(state["investigation"])
        investigation["impacts"] = [ImpactFinding(**item) for item in investigation["impacts"]]
        debt = [DebtAssessment(**item) for item in state["debt"]]
        status, risks, questions, limitations, evidence, requests = RiskAndReportAgent(store, trace).review(
            state["ticket"], investigation, debt)
        result = {"status": status, "risks": [asdict(item) for item in risks], "questions": questions,
                  "limitations": limitations, "evidence": [asdict(item) for item in evidence]}
        return {"review": result, "investigation": {**investigation,
                "impacts": [asdict(item) for item in investigation["impacts"]]},
                "verification_requests": requests, "trace": [event.__dict__ for event in trace.events]}

    def reinvestigate_node(state: AgentState):
        trace = restore_trace(state)
        spent = sum(1 for item in trace.events if item.event_type == "tool" and item.name == "search-evidence")
        remaining = max(0, tool_budget - spent)
        trace.add("coordinator", "routing", "bounded-reinvestigation",
                  {"round": state["verification_round"] + 1,
                   "round_limit": 2, "request_count": len(state["verification_requests"]),
                   "remaining_tool_calls": remaining}, outcome="reinvestigating")
        result = ImpactInvestigationAgent(store, trace, remaining, graph_hops).investigate(
            state["ticket"], targeted_queries=state["verification_requests"])
        result["impacts"] = [asdict(item) for item in result["impacts"]]
        trace.add("coordinator", "routing", "reinvestigation-complete",
                  {"round": state["verification_round"] + 1,
                   "finding_count": len(result["impacts"])})
        return {"investigation": result, "verification_round": state["verification_round"] + 1,
                "trace": [event.__dict__ for event in trace.events]}

    def route_after_review(state: AgentState):
        if state.get("verification_requests") and state.get("verification_round", 0) < 2:
            return "reinvestigate"
        return "persist"

    def persist_node(state: AgentState):
        trace = restore_trace(state)
        investigation = state["investigation"]
        review = state["review"]
        status = review["status"]
        limitations = list(review["limitations"])
        questions = list(review["questions"])
        if state.get("verification_requests"):
            status = "partial"
            limitations.append("Targeted evidence verification reached the bounded reinvestigation limit; unsupported findings were not promoted.")
            if not questions:
                questions.append("Can you clarify the affected service, field, or expected behavior so the evidence search can be narrowed?")
        if not investigation["paths"]:
            limitations.append("The local dependency graph did not confirm a multi-service path for the ticket's evidence; possible impacts are not promoted to confirmed paths.")
        if investigation.get("budget_exhausted"):
            status = "partial"
            limitations.append("The tool-call budget was exhausted before the complete search space was inspected.")
        if not investigation["impacts"]:
            status = "partial"
            limitations.append("No impact finding had evidence in source or implementation-reviewed documentation.")
        if store.current.get("debt_validation_errors"):
            limitations.append(f"{len(store.current['debt_validation_errors'])} technical-debt metadata validation issue(s) were found; malformed/duplicate items are not eligible.")
        trace.add("coordinator", "routing", "persist-assessment", {"status": status})
        context = RunContext(**state["context"])
        assessment = Assessment(
            context=context, status=status, summary=state["ticket"].get("summary", "Untitled requirement"),
            impacts=[ImpactFinding(**item) for item in investigation["impacts"]],
            dependency_paths=investigation["paths"],
            debt_assessments=[DebtAssessment(**item) for item in state["debt"]],
            risks=[Risk(**item) for item in review["risks"]], questions=questions,
            limitations=list(dict.fromkeys(limitations)),
            evidence=[Evidence(**item) for item in review["evidence"]], trace=trace.events)
        from .integrations.jev_classifier import classify_jira_requirement
        assessment.classification_status, assessment.classification = classify_jira_requirement(state["ticket"], trace)
        from .integrations.code_recommendations import generate_code_recommendations
        (assessment.code_recommendation_status,
         assessment.code_recommendations) = generate_code_recommendations(assessment, trace)
        from .integrations.langfuse_trace import export_assessment
        langfuse = export_assessment(assessment)
        assessment.langfuse_trace_status = langfuse["status"] or "error"
        assessment.langfuse_trace_id = langfuse["trace_id"]
        assessment.langfuse_trace_url = langfuse["trace_url"]
        assessment.report_markdown = render_report(assessment)
        workflow.persist(assessment)
        return {"assessment": assessment.to_dict(), "trace": [event.__dict__ for event in trace.events]}

    builder = StateGraph(AgentState)
    builder.add_node("initialize", initialize)
    builder.add_node("impact_investigation", impact_node)
    builder.add_node("technical_debt", debt_node)
    builder.add_node("risk_and_report", review_node)
    builder.add_node("reinvestigate", reinvestigate_node)
    builder.add_node("persist", persist_node)
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "impact_investigation")
    builder.add_edge("impact_investigation", "technical_debt")
    builder.add_edge("technical_debt", "risk_and_report")
    builder.add_conditional_edges("risk_and_report", route_after_review,
                                  {"reinvestigate": "reinvestigate", "persist": "persist"})
    builder.add_edge("reinvestigate", "technical_debt")
    builder.add_edge("persist", END)
    return builder.compile()
