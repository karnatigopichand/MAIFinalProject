"""Evidence-store facade backed by local provenance plus hosted search/graph."""
from __future__ import annotations

import json

from .neo4j import Neo4jDependencyGraph
from .pinecone import PineconeEvidenceIndex
from ..store import LocalEvidenceStore


class HostedEvidenceStore(LocalEvidenceStore):
    def __init__(self, workspace, state_dir=None):
        super().__init__(workspace, state_dir)
        self.semantic_index = PineconeEvidenceIndex()
        self.dependency_graph = Neo4jDependencyGraph()

    def close(self):
        self.dependency_graph.close()

    def _ensure_published(self):
        snapshot = self._snapshot()
        marker = self.state_dir / "published" / f"{snapshot['snapshot_id']}.json"
        if not marker.exists():
            raise RuntimeError(
                f"Snapshot {snapshot['snapshot_id']} is not published to Pinecone and Neo4j; run `impact_assessment publish` first"
            )
        published = json.loads(marker.read_text(encoding="utf-8"))
        if published.get("snapshot_id") != snapshot["snapshot_id"]:
            raise RuntimeError("Hosted-store publication marker does not match the selected snapshot")
        return snapshot

    def search(self, query, repositories=None, document_types=None, limit=8):
        snapshot = self._ensure_published()
        return self.semantic_index.search(query, snapshot["snapshot_id"], repositories,
                                          document_types, limit)

    def search_debts(self, query, limit=48):
        snapshot = self._ensure_published()
        hits = self.semantic_index.search(query, snapshot["snapshot_id"],
                                          document_types=["technical_debt"], limit=limit)
        ids = {hit.evidence_id for hit in hits}
        return [item for item in self.debt_items() if item.evidence_id in ids]

    def traverse(self, starts, max_hops=3, relationships=None):
        snapshot = self._ensure_published()
        return self.dependency_graph.traverse(starts, snapshot["snapshot_id"], max_hops, relationships)


class PineconeEvidenceStore(LocalEvidenceStore):
    """Use Pinecone for semantic vectors and the local snapshot for graph/provenance."""

    def __init__(self, workspace, state_dir=None):
        super().__init__(workspace, state_dir)
        self.semantic_index = PineconeEvidenceIndex()

    def _ensure_published(self):
        snapshot = self._snapshot()
        marker = self.state_dir / "pinecone" / f"{snapshot['snapshot_id']}.json"
        if not marker.exists():
            raise RuntimeError(
                f"Snapshot {snapshot['snapshot_id']} is not in Pinecone; run `impact_assessment publish-pinecone` first"
            )
        published = json.loads(marker.read_text(encoding="utf-8"))
        if published.get("snapshot_id") != snapshot["snapshot_id"]:
            raise RuntimeError("Pinecone publication marker does not match the current local snapshot")
        return snapshot

    def search(self, query, repositories=None, document_types=None, limit=8):
        snapshot = self._ensure_published()
        return self.semantic_index.search(query, snapshot["snapshot_id"], repositories,
                                          document_types, limit)

    def search_debts(self, query, limit=48):
        snapshot = self._ensure_published()
        hits = self.semantic_index.search(query, snapshot["snapshot_id"],
                                          document_types=["technical_debt"], limit=limit)
        ids = {hit.evidence_id for hit in hits}
        return [item for item in self.debt_items() if item.evidence_id in ids]
