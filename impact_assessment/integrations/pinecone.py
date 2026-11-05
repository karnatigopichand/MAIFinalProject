"""Snapshot-scoped Pinecone integrated-embedding index adapter.

The Pinecone index must be configured with an integrated embedding model whose
text field is named ``text``. Existing snapshots remain isolated by namespace.
"""
from __future__ import annotations

import os
import time


class PineconeEvidenceIndex:
    def __init__(self, api_key=None, host=None):
        api_key = api_key or os.environ.get("PINECONE_API_KEY")
        host = host or os.environ.get("PINECONE_INDEX_HOST")
        if not api_key or not host:
            raise RuntimeError("Set PINECONE_API_KEY and PINECONE_INDEX_HOST for Pinecone retrieval")
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError("Install the optional Pinecone SDK from requirements-agent-runtime.txt") from exc
        self.index = Pinecone(api_key=api_key).Index(host=host)

    @staticmethod
    def _namespace(snapshot_id):
        return f"impact-{snapshot_id}"

    def publish(self, snapshot):
        namespace = self._namespace(snapshot["snapshot_id"])
        records = []
        for raw in snapshot["evidence"].values():
            records.append({
                "_id": raw["evidence_id"],
                "text": f"{raw['repository']} {raw['path']} {raw.get('section', '')}\n{raw['excerpt']}",
                "excerpt": raw["excerpt"],
                "evidence_id": raw["evidence_id"], "repository": raw["repository"],
                "commit": raw["commit"], "path": raw["path"],
                "line_start": raw["line_start"], "line_end": raw["line_end"],
                "document_type": raw["document_type"], "section": raw.get("section", ""),
                "snapshot_id": snapshot["snapshot_id"],
            })
        # Pinecone's integrated-embedding record API accepts text records and
        # applies the model configured on the index during upsert.
        for offset in range(0, len(records), 96):
            self.index.upsert_records(namespace=namespace, records=records[offset:offset + 96])
        return {"namespace": namespace, "record_count": len(records)}

    def verify(self, snapshot):
        namespace = self._namespace(snapshot["snapshot_id"])
        raw_stats = self.index.describe_index_stats()
        stats = raw_stats.to_dict() if hasattr(raw_stats, "to_dict") else dict(raw_stats)
        namespace_stats = stats.get("namespaces", {}).get(namespace, {})
        observed_count = namespace_stats.get("vector_count", namespace_stats.get("record_count", 0))
        expected_count = len(snapshot["evidence"])
        if observed_count != expected_count:
            raise RuntimeError(f"Pinecone snapshot count mismatch: expected {expected_count}, observed {observed_count}")
        known_ids = set(snapshot["evidence"])
        last_hits = []
        for _ in range(5):
            last_hits = self.search("delivery instructions", snapshot["snapshot_id"],
                                    repositories=["commerce-checkout"], limit=5)
            if last_hits:
                break
            time.sleep(1)
        if not last_hits:
            raise RuntimeError("Pinecone read-after-write check returned no delivery-instructions evidence")
        if any(item.evidence_id not in known_ids for item in last_hits):
            raise RuntimeError("Pinecone returned an evidence ID outside the published snapshot")
        return {"namespace": namespace, "record_count": observed_count,
                "smoke_query_hits": len(last_hits)}

    def search(self, query, snapshot_id, repositories=None, document_types=None, limit=8):
        filters = {"snapshot_id": {"$eq": snapshot_id}}
        if repositories:
            filters["repository"] = {"$in": list(repositories)}
        if document_types:
            filters["document_type"] = {"$in": list(document_types)}
        result = self.index.search(
            namespace=self._namespace(snapshot_id),
            query={"top_k": limit, "inputs": {"text": query}, "filter": filters},
            fields=["evidence_id", "repository", "commit", "path", "line_start", "line_end", "excerpt",
                    "document_type", "section", "snapshot_id", "text"],
        )
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        hits = payload.get("result", {}).get("hits", payload.get("hits", []))
        evidence = []
        for hit in hits:
            fields = hit.get("fields", hit.get("metadata", {}))
            if fields.get("snapshot_id") != snapshot_id:
                continue
            evidence.append({
                "evidence_id": fields.get("evidence_id", hit.get("_id", hit.get("id", ""))),
                "repository": fields.get("repository", ""), "commit": fields.get("commit", ""),
                "path": fields.get("path", ""), "line_start": int(fields.get("line_start", 1)),
                "line_end": int(fields.get("line_end", 1)), "excerpt": fields.get("excerpt", ""),
                "document_type": fields.get("document_type", "other"),
                "section": fields.get("section", ""), "extraction_method": "pinecone_integrated_embedding",
            })
        from ..models import Evidence
        return [Evidence(**item) for item in evidence]
