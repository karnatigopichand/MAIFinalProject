"""Read-only MCP tools over a pinned local evidence snapshot.

Uses the official MCP Python SDK v2 API. Install `mcp` to run this server.
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer

from .models import DebtItem
from .workflow import AssessmentWorkflow


def create_server(workspace: Path | None = None, snapshot_id: str | None = None):
    root = (workspace or Path(os.environ.get("IMPACT_WORKSPACE", "."))).resolve()
    store = AssessmentWorkflow(root).store
    if snapshot_id:
        snapshot_path = store.snapshots_dir / f"{snapshot_id}.json"
        if not snapshot_path.exists():
            raise ValueError("Requested snapshot is not indexed")
        import json
        store.current = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        store.load_current()
    pinned_snapshot = store.current["snapshot_id"]
    server = MCPServer("commerce-impact-evidence")

    def check_snapshot(requested: str):
        if requested != pinned_snapshot:
            raise ValueError("Snapshot mismatch; reconnect to the requested snapshot")

    def check_repositories(repositories: list[str] | None):
        if repositories is None:
            return None
        unknown = set(repositories) - set(store.current["repositories"])
        if unknown:
            raise ValueError(f"Unknown repositories: {', '.join(sorted(unknown))}")
        return repositories

    @server.tool()
    def search_docs(query: str, snapshot_id: str, repositories: list[str] | None = None,
                    limit: int = 8) -> dict:
        """Search general implementation-reviewed documentation in one snapshot."""
        check_snapshot(snapshot_id)
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        results = store.search(query, check_repositories(repositories),
                               document_types=["documentation", "contract"], limit=limit)
        return {"snapshot_id": pinned_snapshot, "results": [item.__dict__ for item in results]}

    @server.tool()
    def search_technical_debt(query: str, snapshot_id: str, repositories: list[str] | None = None,
                              limit: int = 12) -> dict:
        """Find debt items by relevance; eligibility must be verified separately."""
        check_snapshot(snapshot_id)
        if not 1 <= limit <= 30:
            raise ValueError("limit must be between 1 and 30")
        allowed = check_repositories(repositories)
        evidence = store.search(query, allowed, document_types=["technical_debt"], limit=limit)
        ids = {item.evidence_id for item in evidence}
        items = [item.__dict__ for item in store.debt_items(allowed) if item.evidence_id in ids]
        return {"snapshot_id": pinned_snapshot, "results": items}

    @server.tool()
    def search_identifiers(query: str, snapshot_id: str, repositories: list[str] | None = None,
                           limit: int = 12) -> dict:
        """Search exact field, symbol, route, or event names with provenance."""
        check_snapshot(snapshot_id)
        if not 1 <= limit <= 30:
            raise ValueError("limit must be between 1 and 30")
        results = store.search_identifiers(query, check_repositories(repositories), limit)
        return {"snapshot_id": pinned_snapshot, "results": [item.__dict__ for item in results]}

    @server.tool()
    def traverse_dependencies(start_ids: list[str], snapshot_id: str,
                              relationships: list[str] | None = None,
                              max_hops: int = 3, limit: int = 20) -> dict:
        """Traverse configured API and event edges with evidence for every edge."""
        check_snapshot(snapshot_id)
        allowed = {"CALLS", "PUBLISHES", "CONSUMES", "DECLARES_FIELD", "MAPS_TO",
                   "READS", "WRITES", "LOCATED_IN"}
        if relationships is not None and not set(relationships).issubset(allowed):
            raise ValueError("Unsupported relationship type")
        if not 1 <= max_hops <= 5 or not 1 <= limit <= 50 or len(start_ids) > 20:
            raise ValueError("Traversal bounds exceeded")
        if not set(start_ids).issubset(set(store.current["repositories"]) | {
            edge["source"] for edge in store.current["edges"]
        } | {edge["target"] for edge in store.current["edges"]}):
            raise ValueError("Unknown start node")
        paths = store.traverse(start_ids, max_hops, relationships)[:limit]
        return {"snapshot_id": pinned_snapshot, "paths": paths}

    @server.tool()
    def fetch_evidence(evidence_ids: list[str], snapshot_id: str) -> dict:
        """Fetch source excerpts and provenance for evidence IDs from this snapshot."""
        check_snapshot(snapshot_id)
        if not 1 <= len(evidence_ids) <= 30:
            raise ValueError("Provide between 1 and 30 evidence IDs")
        results = store.fetch_evidence(evidence_ids)
        return {"snapshot_id": pinned_snapshot, "results": [item.__dict__ for item in results]}

    @server.tool()
    def get_contract(component_id: str, snapshot_id: str) -> dict:
        """Fetch matching API/event contract evidence by repository, path, or identifier."""
        check_snapshot(snapshot_id)
        if len(component_id) > 240:
            raise ValueError("component_id is too long")
        results = store.search_identifiers(component_id, limit=12)
        results = [item for item in results if item.document_type in {"contract", "documentation"}]
        return {"snapshot_id": pinned_snapshot, "results": [item.__dict__ for item in results]}

    return server


def main():
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
