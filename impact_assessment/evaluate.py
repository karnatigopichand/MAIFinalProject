"""Run the fixed, provisional eight-ticket replay benchmark."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .workflow import AssessmentWorkflow


def run_benchmark(workspace: Path, benchmark_path: Path | None = None):
    workspace = workspace.resolve()
    benchmark_path = benchmark_path or workspace / "evaluation" / "benchmark-v1.json"
    fixture = json.loads(benchmark_path.read_text(encoding="utf-8"))
    workflow = AssessmentWorkflow(workspace)
    rows = []
    total_tp = total_fp = total_fn = 0
    for case in fixture["cases"]:
        started = time.monotonic()
        assessment = workflow.run(case["ticket"])
        elapsed = round((time.monotonic() - started) * 1000, 2)
        actual = {item.repository for item in assessment.impacts}
        expected = set(case.get("expected_repositories", []))
        tp, fp, fn = len(actual & expected), len(actual - expected), len(expected - actual)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        debt_by_id = {item.debt_id: item for item in assessment.debt_assessments}
        questions = "\n".join(assessment.questions).lower()
        question_checks = {term: term.lower() in questions for term in case.get("expected_question_terms", [])}
        forbidden = sorted(actual & set(case.get("forbidden_repositories", [])))
        bad_debt = [item.debt_id for item in assessment.debt_assessments
                    if case.get("debt_must_not_be_recommended", False) and item.disposition == "recommend"]
        requested_debt = case.get("expected_debt_disposition")
        requested_debt_id = case.get("expected_debt_id")
        debt_matches = None
        if requested_debt and requested_debt_id:
            debt_matches = (debt_by_id.get(requested_debt_id) is not None and
                            debt_by_id[requested_debt_id].disposition == requested_debt)
        elif requested_debt:
            debt_matches = any(item.disposition == requested_debt for item in assessment.debt_assessments)
        known_edge_ids = {edge["edge_id"] for edge in workflow.store.current["edges"]}
        invalid_path_edges = sorted({edge.get("edge_id", "") for path in assessment.dependency_paths
                                     for edge in path.get("edges", [])
                                     if edge.get("edge_id") not in known_edge_ids})
        unsupported_path_evidence = sorted({eid for path in assessment.dependency_paths
                                             for edge in path.get("edges", [])
                                             for eid in edge.get("evidence_ids", [])
                                             if eid not in workflow.store.current["evidence"]})
        tool_errors = sum(1 for event in assessment.trace
                          if event.outcome in {"error", "failed", "timeout"})
        rows.append({
            "case_id": case["id"], "run_id": assessment.context.run_id,
            "snapshot_id": assessment.context.snapshot_id, "status": assessment.status,
            "expected_repositories": sorted(expected), "actual_repositories": sorted(actual),
            "repository_counts": {"true_positive": tp, "false_positive": fp, "false_negative": fn},
            "evidence_count": len(assessment.evidence),
            "invalid_evidence_references": sorted({eid for finding in assessment.impacts
                for eid in finding.evidence_ids if eid not in workflow.store.current["evidence"]}),
            "dependency_paths": assessment.dependency_paths,
            "invalid_dependency_edge_references": invalid_path_edges,
            "invalid_path_evidence_references": unsupported_path_evidence,
            "question_checks": question_checks, "questions": assessment.questions,
            "forbidden_repositories_found": forbidden,
            "recommended_debt_when_forbidden": bad_debt,
            "expected_debt_disposition": requested_debt, "debt_disposition_matched": debt_matches,
            "expected_debt_id": requested_debt_id,
            "runtime_ms": elapsed, "trace_event_count": len(assessment.trace), "tool_error_count": tool_errors,
            "known_fixture_gap": case.get("known_fixture_gap"),
        })
    precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 1.0
    recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 1.0
    result = {
        "benchmark_id": fixture["benchmark_id"], "label_status": fixture["label_status"],
        "source": fixture["source"], "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": workflow.store.current["snapshot_id"], "case_count": len(rows),
        "repository_precision_micro": round(precision, 4), "repository_recall_micro": round(recall, 4),
        "invalid_evidence_reference_count": sum(len(row["invalid_evidence_references"]) for row in rows),
        "invalid_dependency_edge_reference_count": sum(len(row["invalid_dependency_edge_references"]) for row in rows),
        "invalid_path_evidence_reference_count": sum(len(row["invalid_path_evidence_references"]) for row in rows),
        "tool_error_count": sum(row["tool_error_count"] for row in rows),
        "forbidden_repository_count": sum(len(row["forbidden_repositories_found"]) for row in rows),
        "ineligible_debt_recommendation_count": sum(len(row["recommended_debt_when_forbidden"]) for row in rows),
        "cases": rows,
        "limitations": ["Labels are provisional and require review by a domain owner.",
                        "Local debt estimates are illustrative; B07 cannot validate a reviewed two-hour recommendation.",
                        "This local replay does not validate Jira, hosted stores, Replit, or live-broker readiness."],
    }
    output_dir = workflow.state_dir / "evaluations"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{fixture['benchmark_id']}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
