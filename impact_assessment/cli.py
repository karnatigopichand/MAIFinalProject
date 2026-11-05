"""Command line interface for indexing and local ticket replay."""
import argparse
import json
import sys
from pathlib import Path

from .integrations.jira import JiraClient, retry_delivery, serve
from .workflow import AssessmentWorkflow, ticket_from_jira


def _read_ticket(args):
    if args.ticket_json:
        data = json.loads(Path(args.ticket_json).read_text(encoding="utf-8"))
        if "fields" in data:
            return ticket_from_jira(data, args.criteria_field)
        return {
            "ticket_id": data.get("ticket_id", args.ticket_id or "LOCAL-1"),
            "ticket_version": str(data.get("ticket_version", "1")),
            "summary": data.get("summary", ""),
            "description": data.get("description", ""),
            "acceptance_criteria": data.get("acceptance_criteria", []),
        }
    return {"ticket_id": args.ticket_id, "ticket_version": args.ticket_version,
            "summary": args.summary, "description": args.description,
            "acceptance_criteria": args.acceptance_criteria}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="impact-assessment")
    parser.add_argument("--workspace", default=".", help="Workspace root containing sample-repositories/")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("index", help="Build an immutable local evidence snapshot")
    commands.add_parser("webhook", help="Serve authenticated Jira transition webhooks")
    commands.add_parser("mcp", help="Serve read-only MCP retrieval tools over the pinned snapshot")
    commands.add_parser("ui", help="Serve the local browser demo UI")
    publish = commands.add_parser("publish", help="Validate and publish the current snapshot to Pinecone and Neo4j")
    publish.add_argument("--dry-run", action="store_true", help="Build and validate locally without contacting hosted stores")
    evaluate = commands.add_parser("evaluate", help="Replay the fixed eight-ticket evaluation set")
    evaluate.add_argument("--benchmark", help="Benchmark JSON path (defaults to evaluation/benchmark-v1.json)")
    commands.add_parser("extract-graph", help="Run Graphify and reconcile code edges with explicit service contracts")
    deliver = commands.add_parser("deliver", help="Retry posting a saved assessment to Jira")
    deliver.add_argument("run_id")
    assess = commands.add_parser("assess", help="Run the three-agent local assessment")
    assess.add_argument("--ticket-json", help="Local Jira issue JSON or normalized ticket JSON")
    assess.add_argument("--ticket-id", default="LOCAL-1")
    assess.add_argument("--ticket-version", default="1")
    assess.add_argument("--summary", default="")
    assess.add_argument("--description", default="")
    assess.add_argument("--acceptance-criteria", action="append", default=[])
    assess.add_argument("--criteria-field", default="customfield_10000")
    assess.add_argument("--max-debt-hours", type=float, default=3.0)
    assess.add_argument("--orchestrator", choices=("local", "langgraph"), default="local")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    if args.command == "webhook":
        serve(workspace)
        return 0
    if args.command == "mcp":
        from .mcp_server import create_server
        create_server(workspace).run(transport="stdio")
        return 0
    if args.command == "ui":
        from .ui_server import serve as serve_ui
        serve_ui(workspace)
        return 0
    if args.command == "publish":
        from .pipeline import publish_snapshot
        print(json.dumps(publish_snapshot(workspace, dry_run=args.dry_run), indent=2))
        return 0
    if args.command == "extract-graph":
        from .graphify_pipeline import run_graphify
        print(json.dumps(run_graphify(workspace), indent=2))
        return 0
    if args.command == "evaluate":
        from .evaluate import run_benchmark
        benchmark = Path(args.benchmark).resolve() if args.benchmark else None
        print(json.dumps(run_benchmark(workspace, benchmark), indent=2))
        return 0
    if args.command == "deliver":
        print(json.dumps(retry_delivery(workspace, args.run_id, JiraClient())))
        return 0
    if args.command == "index":
        from .store import LocalEvidenceStore
        snapshot = LocalEvidenceStore(workspace).build_snapshot()
        print(json.dumps({"snapshot_id": snapshot["snapshot_id"], "repositories": list(snapshot["repositories"]),
                          "evidence_count": len(snapshot["evidence"]), "edge_count": len(snapshot["edges"]),
                          "debt_item_count": len(snapshot["debts"])}))
        return 0
    workflow = AssessmentWorkflow(workspace, max_hours=getattr(args, "max_debt_hours", 3.0))
    ticket = _read_ticket(args)
    if not ticket.get("summary") and not ticket.get("description"):
        parser.error("Supply --summary/--description or --ticket-json")
    if args.orchestrator == "langgraph":
        from .langgraph_coordinator import build_graph
        state = build_graph(workspace, max_hours=args.max_debt_hours).invoke({"ticket": ticket})
        from .models import Assessment, DebtAssessment, Evidence, ImpactFinding, Risk, RunContext, TraceEvent
        raw = state["assessment"]
        assessment = Assessment(
            context=RunContext(**raw["context"]), status=raw["status"], summary=raw["summary"],
            impacts=[ImpactFinding(**x) for x in raw["impacts"]], dependency_paths=raw["dependency_paths"],
            debt_assessments=[DebtAssessment(**x) for x in raw["debt_assessments"]],
            risks=[Risk(**x) for x in raw["risks"]], questions=raw["questions"],
            limitations=raw["limitations"], evidence=[Evidence(**x) for x in raw["evidence"]],
            trace=[TraceEvent(**x) for x in raw["trace"]], report_markdown=raw["report_markdown"])
    else:
        assessment = workflow.run(ticket)
    run_dir = workflow.state_dir / "runs" / assessment.context.run_id
    print(assessment.report_markdown)
    print(f"\nSaved assessment: {run_dir / 'assessment.json'}", file=sys.stderr)
    print(f"Saved trace: {run_dir / 'trace.ndjson'}", file=sys.stderr)
    return 0 if assessment.status in {"complete", "needs_clarification"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
