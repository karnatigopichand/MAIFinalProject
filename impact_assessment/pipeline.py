"""Publish one validated local evidence snapshot to hosted retrieval stores."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .integrations.neo4j import Neo4jDependencyGraph
from .integrations.pinecone import PineconeEvidenceIndex
from .store import LocalEvidenceStore


def publish_pinecone_snapshot(workspace: Path):
    """Publish only semantic evidence vectors; graph traversal remains local."""
    store = LocalEvidenceStore(workspace.resolve())
    snapshot = store.build_snapshot()
    errors = validate_snapshot(snapshot)
    if errors:
        raise RuntimeError("Snapshot validation failed: " + "; ".join(errors[:8]))

    pinecone = PineconeEvidenceIndex()
    vector_result = pinecone.publish(snapshot)
    vector_validation = pinecone.verify(snapshot)
    marker = {
        "snapshot_id": snapshot["snapshot_id"],
        "published_at": datetime.now(timezone.utc).isoformat(),
        "pinecone": vector_result,
        "pinecone_validation": vector_validation,
        "source_hashes": snapshot["source_hashes"],
    }
    marker_dir = store.state_dir / "pinecone"
    marker_dir.mkdir(parents=True, exist_ok=True)
    temporary = marker_dir / f".{snapshot['snapshot_id']}.tmp"
    temporary.write_text(json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(marker_dir / f"{snapshot['snapshot_id']}.json")
    return {"snapshot_id": snapshot["snapshot_id"], "evidence_count": len(snapshot["evidence"]),
            "published": True, "pinecone": vector_result, "pinecone_validation": vector_validation}


def validate_snapshot(snapshot):
    evidence = snapshot["evidence"]
    errors = []
    for edge in snapshot["edges"]:
        if not edge.get("evidence_ids") or any(item not in evidence for item in edge["evidence_ids"]):
            errors.append(f"edge {edge.get('edge_id')} has missing evidence provenance")
        if (edge["source"] not in snapshot["repositories"]
                and not edge["source"].startswith(("event:", "field:"))):
            errors.append(f"edge {edge.get('edge_id')} has unknown source node {edge['source']}")
        if (edge["target"] not in snapshot["repositories"]
                and not edge["target"].startswith(("event:", "field:"))):
            errors.append(f"edge {edge.get('edge_id')} has unknown target node {edge['target']}")
    for debt in snapshot["debts"]:
        if debt["evidence_id"] not in evidence:
            errors.append(f"debt {debt['repository']}/{debt['debt_id']} has no evidence")
    return errors


def publish_snapshot(workspace: Path, dry_run=False):
    store = LocalEvidenceStore(workspace.resolve())
    snapshot = store.build_snapshot()
    errors = validate_snapshot(snapshot)
    if errors:
        raise RuntimeError("Snapshot validation failed: " + "; ".join(errors[:8]))
    result = {"snapshot_id": snapshot["snapshot_id"], "repository_count": len(snapshot["repositories"]),
              "evidence_count": len(snapshot["evidence"]), "edge_count": len(snapshot["edges"]),
              "debt_count": len(snapshot["debts"]), "debt_validation_errors": snapshot["debt_validation_errors"],
              "published": False}
    if dry_run:
        graph_path = store.state_dir / "graphify" / "graphify-out" / "graph.json"
        if graph_path.is_file():
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            result["graphify"] = {"node_count": len(graph.get("nodes", [])),
                                  "edge_count": len(graph.get("edges", []))}
        else:
            result["graphify_error"] = "Run `impact_assessment extract-graph` before publishing"
        return result

    graph_path = store.state_dir / "graphify" / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        raise RuntimeError("Graphify output missing; run `impact_assessment extract-graph` before publishing")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    reconciliation_path = graph_path.parent.parent / "reconciliation.json"
    if not reconciliation_path.is_file():
        raise RuntimeError("Graphify reconciliation report missing; rerun `impact_assessment extract-graph`")
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    if reconciliation.get("snapshot_id") != snapshot["snapshot_id"]:
        raise RuntimeError("Graphify reconciliation is stale; rerun `impact_assessment extract-graph`")

    pinecone = PineconeEvidenceIndex()
    neo4j = Neo4jDependencyGraph()
    try:
        graph_result = neo4j.publish(snapshot, graph)
        vector_result = pinecone.publish(snapshot)
        vector_validation = pinecone.verify(snapshot)
        graph_validation = neo4j.verify(snapshot, graph_result["node_count"],
                                        graph_result["edge_count"],
                                        graph_result["graphify_edge_count"])
    finally:
        neo4j.close()
    marker = {
        "snapshot_id": snapshot["snapshot_id"], "published_at": datetime.now(timezone.utc).isoformat(),
        "pinecone": vector_result, "neo4j": graph_result,
        "pinecone_validation": vector_validation, "neo4j_validation": graph_validation,
        "graphify": {"node_count": len(graph.get("nodes", [])), "edge_count": len(graph.get("edges", [])),
                     "cross_repository_edges": reconciliation.get("graphify_cross_repository_edge_count", 0)},
        "source_hashes": snapshot["source_hashes"],
    }
    marker_dir = store.state_dir / "published"
    marker_dir.mkdir(parents=True, exist_ok=True)
    temporary = marker_dir / f".{snapshot['snapshot_id']}.tmp"
    temporary.write_text(json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(marker_dir / f"{snapshot['snapshot_id']}.json")
    result.update({"published": True, "pinecone": vector_result, "neo4j": graph_result})
    return result
