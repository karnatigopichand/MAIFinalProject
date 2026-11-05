"""Snapshot-scoped Neo4j graph publisher and bounded reader."""
from __future__ import annotations

import os


ALLOWED_RELATIONSHIPS = {"CALLS", "PUBLISHES", "CONSUMES", "DECLARES_FIELD", "MAPS_TO"}
DEFAULT_TRAVERSAL_RELATIONSHIPS = {"CALLS", "PUBLISHES", "CONSUMES"}


class Neo4jDependencyGraph:
    def __init__(self, uri=None, username=None, password=None, database=None):
        uri = uri or os.environ.get("NEO4J_URI")
        username = username or os.environ.get("NEO4J_USERNAME")
        password = password or os.environ.get("NEO4J_PASSWORD")
        if not uri or not username or not password:
            raise RuntimeError("Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD for Neo4j")
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("Install the optional Neo4j driver from requirements-agent-runtime.txt") from exc
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database or os.environ.get("NEO4J_DATABASE", "neo4j")

    def close(self):
        self.driver.close()

    def publish(self, snapshot, graphify_graph=None):
        nodes = set(snapshot["repositories"])
        nodes.update(edge["source"] for edge in snapshot["edges"])
        nodes.update(edge["target"] for edge in snapshot["edges"])
        edge_rows = []
        for edge in snapshot["edges"]:
            relation = edge["relationship"]
            if relation not in ALLOWED_RELATIONSHIPS:
                continue
            nodes.add(edge["source"])
            nodes.add(edge["target"])
            edge_rows.append({"source": edge["source"], "target": edge["target"],
                              "relationship": relation, "edge_id": edge["edge_id"],
                              "evidence_ids": edge["evidence_ids"], "detail": edge.get("detail", ""),
                              "classification": edge.get("classification", "explicit")})
        node_rows = [{"node_id": node,
                      "kind": ("event" if node.startswith("event:") else
                               "field" if node.startswith("field:") else "repository")}
                     for node in sorted(nodes)]
        graphify_edges = []
        if graphify_graph:
            graphify_nodes = graphify_graph.get("nodes", [])
            graphify_node_ids = {item.get("id") for item in graphify_nodes if item.get("id")}
            node_metadata = {}
            for item in graphify_nodes:
                node_id = item.get("id")
                if not node_id:
                    continue
                source_path = item.get("source_file", "")
                repo = source_path.split("/", 1)[0] if source_path else ""
                if repo not in snapshot["repositories"]:
                    repo = ""
                external_id = f"gf:{node_id}"
                node_rows.append({"node_id": external_id, "kind": item.get("type", "code"),
                                  "label": str(item.get("label", ""))[:500],
                                  "path": source_path[:1000],
                                  "source_location": str(item.get("source_location", ""))[:100],
                                  "confidence": str(item.get("confidence", "EXTRACTED")),
                                  "repository": repo})
                node_metadata[node_id] = {"external_id": external_id, "repository": repo}
                if repo:
                    graphify_edges.append({"source": repo, "target": external_id, "relation": "CONTAINS_CODE",
                                           "confidence": "EXTRACTED", "source_path": source_path,
                                           "source_location": str(item.get("source_location", "")),
                                           "evidence_ids": []})
            for item in graphify_graph.get("edges", []):
                source = node_metadata.get(item.get("source"))
                target = node_metadata.get(item.get("target"))
                if not source or not target:
                    continue
                graphify_edges.append({"source": source["external_id"], "target": target["external_id"],
                                       "relation": str(item.get("relation", "references"))[:100],
                                       "confidence": str(item.get("confidence", "EXTRACTED")),
                                       "source_path": str(item.get("source_file", ""))[:1000],
                                       "source_location": str(item.get("source_location", ""))[:100],
                                       "evidence_ids": []})
        with self.driver.session(database=self.database) as session:
            session.run("""UNWIND $rows AS row
                MERGE (n:ImpactNode {snapshot_id: $snapshot_id, node_id: row.node_id})
                SET n.kind = row.kind, n.label = row.label, n.path = row.path,
                    n.source_location = row.source_location, n.confidence = row.confidence,
                    n.repository = row.repository""",
                rows=node_rows, snapshot_id=snapshot["snapshot_id"]).consume()
            for relation in sorted(ALLOWED_RELATIONSHIPS):
                rows = [row for row in edge_rows if row["relationship"] == relation]
                if not rows:
                    continue
                # Relationship names come from the fixed allowlist above.
                statement = f"""UNWIND $rows AS row
                    MATCH (a:ImpactNode {{snapshot_id: $snapshot_id, node_id: row.source}})
                    MATCH (b:ImpactNode {{snapshot_id: $snapshot_id, node_id: row.target}})
                    MERGE (a)-[r:{relation} {{snapshot_id: $snapshot_id, edge_id: row.edge_id}}]->(b)
                    SET r.evidence_ids = row.evidence_ids, r.detail = row.detail,
                        r.classification = row.classification"""
                session.run(statement, rows=rows, snapshot_id=snapshot["snapshot_id"]).consume()
            if graphify_edges:
                session.run("""UNWIND $rows AS row
                    MATCH (a:ImpactNode {snapshot_id: $snapshot_id, node_id: row.source})
                    MATCH (b:ImpactNode {snapshot_id: $snapshot_id, node_id: row.target})
                    MERGE (a)-[r:GRAPHIFY_EDGE {snapshot_id: $snapshot_id,
                        relation: row.relation, source_path: row.source_path,
                        source_location: row.source_location}]->(b)
                    SET r.confidence = row.confidence, r.evidence_ids = row.evidence_ids""",
                    rows=graphify_edges, snapshot_id=snapshot["snapshot_id"]).consume()
        return {"node_count": len(node_rows), "edge_count": len(edge_rows),
                "graphify_node_count": len(node_rows) - len(nodes),
                "graphify_edge_count": len(graphify_edges)}

    def verify(self, snapshot, expected_node_count, expected_contract_edge_count,
               expected_graphify_edge_count):
        snapshot_id = snapshot["snapshot_id"]
        with self.driver.session(database=self.database) as session:
            node_record = session.run(
                "MATCH (n:ImpactNode {snapshot_id: $snapshot_id}) RETURN count(n) AS count",
                snapshot_id=snapshot_id).single()
            edge_record = session.run(
                "MATCH ()-[r]->() WHERE r.snapshot_id = $snapshot_id RETURN count(r) AS count",
                snapshot_id=snapshot_id).single()
        node_count = node_record["count"] if node_record else 0
        edge_count = edge_record["count"] if edge_record else 0
        expected_edges = expected_contract_edge_count + expected_graphify_edge_count
        if node_count != expected_node_count or edge_count != expected_edges:
            raise RuntimeError(
                f"Neo4j snapshot count mismatch: expected {expected_node_count} nodes/{expected_edges} edges, "
                f"observed {node_count} nodes/{edge_count} edges")
        paths = self.traverse(["commerce-checkout"], snapshot_id, max_hops=3)
        if not any("commerce-notifications" in path["nodes"] for path in paths):
            raise RuntimeError("Neo4j known-path check failed: checkout does not reach notifications")
        evidence = snapshot["evidence"]
        if any(eid not in evidence for path in paths for eid in path["evidence_ids"]):
            raise RuntimeError("Neo4j known-path check returned unsupported evidence provenance")
        return {"node_count": node_count, "edge_count": edge_count,
                "known_path": ["commerce-checkout", "commerce-orders", "event:order.confirmed.v1",
                               "commerce-notifications"]}

    def traverse(self, starts, snapshot_id, max_hops=3, relationships=None, limit=200):
        allowed = set(relationships or DEFAULT_TRAVERSAL_RELATIONSHIPS)
        if not allowed or not allowed.issubset(ALLOWED_RELATIONSHIPS):
            raise ValueError("Unsupported Neo4j relationship type")
        if not 1 <= max_hops <= 5 or not 1 <= limit <= 500:
            raise ValueError("Graph traversal bounds exceeded")
        statement = f"""UNWIND $starts AS start_id
            MATCH p=(s:ImpactNode {{snapshot_id: $snapshot_id, node_id: start_id}})
                -[rs*1..{max_hops}]->(t:ImpactNode {{snapshot_id: $snapshot_id}})
            WHERE all(r IN relationships(p) WHERE r.snapshot_id = $snapshot_id
                AND type(r) IN $relationships)
            RETURN [n IN nodes(p) | n.node_id] AS nodes,
                   [r IN relationships(p) | {{edge_id:r.edge_id, source:startNode(r).node_id,
                      target:endNode(r).node_id, relationship:type(r), detail:r.detail,
                      evidence_ids:r.evidence_ids, classification:r.classification}}] AS edges
            LIMIT $limit"""
        with self.driver.session(database=self.database) as session:
            records = session.run(statement, starts=list(starts), snapshot_id=snapshot_id,
                                  relationships=sorted(allowed), limit=limit)
            paths = []
            for record in records:
                edges = record["edges"]
                paths.append({"nodes": record["nodes"], "edges": edges,
                              "evidence_ids": list(dict.fromkeys(
                                  eid for edge in edges for eid in edge.get("evidence_ids", [])))})
            return paths


def configured():
    return all(os.environ.get(name) for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"))
