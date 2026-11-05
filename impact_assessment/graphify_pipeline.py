"""Run Graphify over the six service repositories and reconcile contracts."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .store import LocalEvidenceStore


def run_graphify(workspace: Path):
    workspace = workspace.resolve()
    output_root = workspace / ".impact_assessment" / "graphify"
    output_root.mkdir(parents=True, exist_ok=True)
    executable = shutil.which("graphify")
    if not executable:
        candidate = Path(sys.executable).parent / "graphify"
        if candidate.exists():
            executable = str(candidate)
    if not executable:
        raise RuntimeError("Graphify CLI is missing; install the `graphifyy` package in the active Python environment")
    command = [executable, "extract", str(workspace / "sample-repositories"),
               "--code-only", "--no-cluster", "--out", str(output_root)]
    version_result = subprocess.run([executable, "--version"], cwd=workspace, check=True,
                                    text=True, capture_output=True)
    subprocess.run(command, cwd=workspace, check=True)
    graph_path = output_root / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        raise RuntimeError(f"Graphify completed without writing {graph_path}")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))

    store = LocalEvidenceStore(workspace)
    snapshot = store.build_snapshot()
    id_to_repository = {}
    for node in graph.get("nodes", []):
        source_path = node.get("source_file", "")
        repo = source_path.split("/", 1)[0]
        if repo in snapshot["repositories"]:
            id_to_repository[node.get("id")] = repo
    cross_repo = []
    for edge in graph.get("edges", []):
        source_repo = id_to_repository.get(edge.get("source"))
        target_repo = id_to_repository.get(edge.get("target"))
        if source_repo and target_repo and source_repo != target_repo:
            cross_repo.append({"source_repository": source_repo, "target_repository": target_repo,
                               "relation": edge.get("relation"), "confidence": edge.get("confidence"),
                               "source_file": edge.get("source_file"),
                               "source_location": edge.get("source_location")})
    relationship_counts = Counter(edge["relationship"] for edge in snapshot["edges"])
    contracts = {}
    for path in sorted((workspace / "sample-repositories").glob("commerce-*/contracts.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        contracts[path.parent.name] = {"call_count": len(data.get("calls", [])),
                                        "mapping_count": len(data.get("mappings", {})),
                                        "event_count": len(data.get("publishes", [])) + len(data.get("consumes", []))}
    paths = store.traverse(["commerce-checkout"], max_hops=3)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": snapshot["snapshot_id"], "graphify_version": version_result.stdout.strip(),
        "graph_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
        "graph_path": str(graph_path.relative_to(workspace)),
        "graphify_node_count": len(graph.get("nodes", [])),
        "graphify_edge_count": len(graph.get("edges", [])),
        "graphify_cross_repository_edge_count": len(cross_repo),
        "graphify_cross_repository_edges": cross_repo,
        "explicit_contract_edge_count": len(snapshot["edges"]),
        "explicit_contract_relationship_counts": dict(relationship_counts),
        "contracts": contracts,
        "checkout_dependency_paths": paths,
        "interpretation": (
            "Graphify parsed code structure within the separately packaged services. No cross-service source-code edge was extracted. "
            "The cross-repository runtime relationships are declared by HTTP and ActiveMQ contracts and are retained as explicit edges."
        ),
    }
    report_path = output_root / "reconciliation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
