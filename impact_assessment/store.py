"""Local snapshot evidence store. Production Pinecone/Neo4j adapters implement this interface."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import deque
from pathlib import Path
from typing import Iterable

from .models import DebtItem, DependencyEdge, Evidence


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
IGNORE_DIRS = {".git", ".venv", "__pycache__", "node_modules", "data"}
INDEXER_VERSION = "1.4"


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text) if len(t) > 1}


def _kind(path: str) -> str:
    if "/docs/technical-debt/" in f"/{path}/" or path.endswith("TECH_DEBT.md"):
        return "technical_debt"
    if "/docs/" in f"/{path}/" or path.startswith("docs/"):
        return "documentation"
    if "/tests/" in f"/{path}/" or path.startswith("tests/"):
        return "test"
    if "/config/" in f"/{path}/" or path.endswith("contracts.json"):
        return "contract"
    if path.endswith(".py"):
        return "source"
    return "other"


class LocalEvidenceStore:
    """Read-only, snapshot-scoped retrieval and graph traversal over this workspace."""

    def __init__(self, workspace: Path, state_dir: Path | None = None):
        self.workspace = workspace.resolve()
        self.state_dir = (state_dir or self.workspace / ".impact_assessment").resolve()
        self.snapshots_dir = self.state_dir / "snapshots"
        self.current: dict = {}

    def build_snapshot(self) -> dict:
        services_root = self.workspace / "sample-repositories"
        files: list[tuple[str, str, str]] = []
        source_hashes: dict[str, str] = {}
        for repo_dir in sorted(services_root.glob("commerce-*")):
            if not repo_dir.is_dir():
                continue
            repo = repo_dir.name
            for path in sorted(repo_dir.rglob("*")):
                if not path.is_file() or any(part in IGNORE_DIRS for part in path.parts):
                    continue
                rel = path.relative_to(repo_dir).as_posix()
                if not (rel.endswith((".md", ".py", ".json")) or rel == "README.md"):
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                key = f"{repo}:{rel}"
                digest = hashlib.sha256(content.encode()).hexdigest()
                source_hashes[key] = digest
                files.append((repo, rel, content))

        commit = self._commit()
        manifest = {"commit": commit, "files": source_hashes, "indexer_version": INDEXER_VERSION}
        snapshot_id = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
        evidence: dict[str, dict] = {}
        by_path: dict[tuple[str, str], list[str]] = {}
        for repo, rel, content in files:
            for start, end, section, excerpt in self._chunks(rel, content):
                evidence_id = hashlib.sha256(
                    f"{snapshot_id}\0{repo}\0{rel}\0{start}\0{end}\0{excerpt}".encode()
                ).hexdigest()[:24]
                record = Evidence(evidence_id, repo, commit, rel, start, end, excerpt,
                                  _kind(rel), section)
                evidence[evidence_id] = record.__dict__
                by_path.setdefault((repo, rel), []).append(evidence_id)

        repositories = sorted({repo for repo, _, _ in files})
        edges = self._build_edges(snapshot_id, files, evidence, by_path)
        debts, debt_validation_errors = self._parse_debt(files, by_path, evidence)
        snapshot = {
            "snapshot_id": snapshot_id,
            "indexer_version": INDEXER_VERSION,
            "commit": commit,
            "repositories": {repo: commit for repo in repositories},
            "source_hashes": source_hashes,
            "evidence": evidence,
            "edges": edges,
            "debts": debts,
            "debt_validation_errors": debt_validation_errors,
        }
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        target = self.snapshots_dir / f"{snapshot_id}.json"
        if not target.exists():
            target.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        self.current = snapshot
        (self.state_dir / "current_snapshot").write_text(snapshot_id, encoding="utf-8")
        return snapshot

    def load_current(self) -> dict:
        pointer = self.state_dir / "current_snapshot"
        if not pointer.exists():
            return self.build_snapshot()
        snapshot_id = pointer.read_text().strip()
        path = self.snapshots_dir / f"{snapshot_id}.json"
        self.current = json.loads(path.read_text(encoding="utf-8"))
        if self.current["snapshot_id"] != snapshot_id:
            raise ValueError("Snapshot pointer mismatch")
        return self.current

    def search(self, query: str, repositories: Iterable[str] | None = None,
               document_types: Iterable[str] | None = None, limit: int = 8) -> list[Evidence]:
        snap = self._snapshot()
        terms = _tokens(query)
        repos, kinds = set(repositories or []), set(document_types or [])
        matches = []
        for raw in snap["evidence"].values():
            if repos and raw["repository"] not in repos:
                continue
            if kinds and raw["document_type"] not in kinds:
                continue
            text = f"{raw['section']} {raw['path']} {raw['excerpt']}"
            words = _tokens(text)
            overlap = terms & words
            if not overlap:
                continue
            required_overlap = 1 if len(terms) == 1 else len(terms) if len(terms) <= 3 else 2
            if len(overlap) < required_overlap:
                continue
            exact = sum(3 for term in terms if term in text.lower())
            score = len(overlap) / max(len(terms), 1) + exact / max(3 * len(terms), 1)
            matches.append((score, raw["evidence_id"], raw))
        matches.sort(key=lambda x: (-x[0], x[1]))
        return [Evidence(**raw) for _, _, raw in matches[:limit]]

    def search_identifiers(self, query: str, repositories: Iterable[str] | None = None,
                           limit: int = 8) -> list[Evidence]:
        snap = self._snapshot()
        needle = query.lower()
        repos = set(repositories or [])
        matches = []
        for raw in snap["evidence"].values():
            if repos and raw["repository"] not in repos:
                continue
            text = f"{raw['path']}\n{raw['excerpt']}".lower()
            if needle in text:
                matches.append(raw)
        matches.sort(key=lambda r: (r["repository"], r["path"], r["line_start"]))
        return [Evidence(**r) for r in matches[:limit]]

    def fetch_evidence(self, evidence_ids: Iterable[str]) -> list[Evidence]:
        evidence = self._snapshot()["evidence"]
        result = []
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise KeyError(f"Evidence {evidence_id} is not in selected snapshot")
            result.append(Evidence(**evidence[evidence_id]))
        return result

    def traverse(self, starts: Iterable[str], max_hops: int = 3,
                 relationships: Iterable[str] | None = None) -> list[dict]:
        snap = self._snapshot()
        allowed = set(relationships or {"CALLS", "PUBLISHES", "CONSUMES"})
        edges = [DependencyEdge(**raw) for raw in snap["edges"] if raw["relationship"] in allowed]
        by_source: dict[str, list[DependencyEdge]] = {}
        for edge in edges:
            by_source.setdefault(edge.source, []).append(edge)
        queue = deque((node, [node], [], 0) for node in starts)
        seen: set[tuple[str, int]] = set()
        paths = []
        while queue:
            node, nodes, path_edges, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for edge in by_source.get(node, []):
                marker = (edge.target, depth + 1)
                if marker in seen or edge.target in nodes:
                    continue
                seen.add(marker)
                next_nodes, next_edges = nodes + [edge.target], path_edges + [edge.__dict__]
                paths.append({"nodes": next_nodes, "edges": next_edges,
                              "evidence_ids": [eid for item in next_edges for eid in item["evidence_ids"]]})
                queue.append((edge.target, next_nodes, next_edges, depth + 1))
        return paths

    def debt_items(self, repositories: Iterable[str] | None = None) -> list[DebtItem]:
        allowed = set(repositories or [])
        items = [DebtItem(**item) for item in self._snapshot()["debts"]]
        return [item for item in items if not allowed or item.repository in allowed]

    def search_debts(self, query: str, limit: int = 48) -> list[DebtItem]:
        """Expose all snapshot debt locally; hosted stores override this semantically."""
        return self.debt_items()

    def _snapshot(self) -> dict:
        return self.current or self.load_current()

    def _commit(self) -> str:
        try:
            return subprocess.check_output(["git", "-C", str(self.workspace), "rev-parse", "HEAD"],
                                           text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return "uncommitted"

    @staticmethod
    def _chunks(path: str, content: str):
        lines = content.splitlines()
        if not lines:
            return [(1, 1, "", "")]
        if path.endswith(".md"):
            headings = [i for i, line in enumerate(lines) if line.startswith("#")]
            starts = sorted(set([0, *headings]))
            result = []
            for n, start0 in enumerate(starts):
                end0 = starts[n + 1] if n + 1 < len(starts) else len(lines)
                block = "\n".join(lines[start0:end0]).strip()
                if block:
                    heading = next((line.lstrip("# ").strip() for line in lines[start0:end0]
                                    if line.startswith("#")), "")
                    result.append((start0 + 1, end0, heading, block[:12000]))
            return result
        result = []
        size = 70
        for start0 in range(0, len(lines), size):
            end0 = min(len(lines), start0 + size)
            result.append((start0 + 1, end0, "", "\n".join(lines[start0:end0])[:12000]))
        return result

    def _build_edges(self, snapshot_id, files, evidence, by_path):
        configs = {}
        contracts = {}
        for repo, rel, content in files:
            if rel == "config/local.json":
                try:
                    configs[repo] = json.loads(content)
                except json.JSONDecodeError:
                    continue
            elif rel == "contracts.json":
                try:
                    contracts[repo] = json.loads(content)
                except json.JSONDecodeError:
                    continue

        edges: list[dict] = []

        def add(source, target, relation, refs, detail=""):
            ids = [eid for path in refs for eid in by_path.get((source, path), [])]
            if not ids:
                return
            identity = (source, target, relation, detail if relation != "CALLS" else "")
            existing = next((edge for edge in edges if
                             (edge["source"], edge["target"], edge["relationship"],
                              edge["detail"] if relation != "CALLS" else "") == identity), None)
            if existing:
                existing["evidence_ids"] = list(dict.fromkeys(existing["evidence_ids"] + ids))
                if relation == "CALLS" and detail != "HTTP dependency":
                    existing["detail"] = detail
                return
            edge_id = hashlib.sha256(f"{snapshot_id}:{source}:{target}:{relation}:{detail}".encode()).hexdigest()[:20]
            edges.append(DependencyEdge(edge_id, source, target, relation,
                                        list(dict.fromkeys(ids)), detail).__dict__)

        for repo, config in configs.items():
            for target in config.get("http", {}):
                if target in configs:
                    contract_refs = []
                    for call in contracts.get(repo, {}).get("calls", []):
                        if call.get("target") == target:
                            contract_refs.append("contracts.json")
                    add(repo, target, "CALLS", ["config/local.json", *contract_refs], "HTTP dependency")
            publish_topics = set(config.get("mq", {}).get("publish", {}))
            if publish_topics:
                event_path = "config/local.json"
                for target, other in configs.items():
                    consumed = set(other.get("mq", {}).get("consume", {}).values())
                    for topic in sorted(publish_topics & consumed):
                        event_node = f"event:{topic}"
                        add(repo, event_node, "PUBLISHES", [event_path], topic)
                        consumer_ids = by_path.get((target, event_path), [])
                        if consumer_ids:
                            edge_id = hashlib.sha256(
                                f"{snapshot_id}:{event_node}:{target}:CONSUMES:{topic}".encode()).hexdigest()[:20]
                            edges.append(DependencyEdge(edge_id, event_node, target, "CONSUMES",
                                                       [consumer_ids[0]], topic).__dict__)
        # Contract files are implementation-reviewed declarations. Keep their
        # citations on runtime edges so a path is backed by both config and API
        # contract evidence wherever the two describe the same call.
        for repo, contract in contracts.items():
            for call in contract.get("calls", []):
                target = call.get("target")
                if target in configs:
                    detail = f"{call.get('method', 'HTTP')} {call.get('path', '')}".strip()
                    add(repo, target, "CALLS", ["contracts.json"], detail)
            contract_ids = by_path.get((repo, "contracts.json"), [])
            if contract_ids:
                for source_field, target_field in contract.get("mappings", {}).items():
                    source_node = f"field:{repo}:{source_field}"
                    target_node = f"field:{repo}:{target_field}"
                    mappings = [
                        (repo, source_node, "DECLARES_FIELD", source_field),
                        (repo, target_node, "DECLARES_FIELD", target_field),
                        (source_node, target_node, "MAPS_TO", f"{source_field} → {target_field}"),
                    ]
                    for source, target, relation, detail in mappings:
                        edge_id = hashlib.sha256(
                            f"{snapshot_id}:{source}:{target}:{relation}:{detail}".encode()).hexdigest()[:20]
                        edges.append(DependencyEdge(edge_id, source, target, relation,
                                                    [contract_ids[0]], detail).__dict__)
        # Deduplicate repeated topic bindings across multiple queues in the same service pair.
        unique = {edge["edge_id"]: edge for edge in edges}
        return list(unique.values())

    def _parse_debt(self, files, by_path, evidence):
        items: list[dict] = []
        errors: list[str] = []
        seen_ids: set[tuple[str, str]] = set()
        for repo, rel, content in files:
            if not ("/docs/technical-debt/" in f"/{rel}/" or rel == "TECH_DEBT.md"):
                continue
            headings = list(re.finditer(r"^#{1,6}\s+([A-Z][A-Z0-9_-]*-TD-\d+)\s*:\s*(.+)$", content, re.M))
            path_ids = by_path.get((repo, rel), [])
            if not headings:
                errors.append(f"{repo}:{rel}: no stable debt item heading found")
                continue
            if not path_ids:
                errors.append(f"{repo}:{rel}: no evidence chunk available for debt item")
                continue
            for index, heading in enumerate(headings):
                end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
                body = content[heading.start():end]
                def field(name):
                    match = re.search(rf"^-\s*{re.escape(name)}:\s*(.+)$", body, re.M | re.I)
                    return match.group(1).strip() if match else ""
                def estimate(name):
                    raw = field(name)
                    try:
                        return float(raw)
                    except (ValueError, TypeError):
                        return None
                heading_line = content[:heading.start()].count("\n") + 1
                evidence_id = next((eid for eid in path_ids
                                    if evidence[eid]["line_start"] <= heading_line <= evidence[eid]["line_end"]),
                                   path_ids[0])
                debt_id = heading.group(1)
                identity = (repo, debt_id)
                if identity in seen_ids:
                    errors.append(f"{repo}:{rel}: duplicate debt ID {debt_id}; later occurrence quarantined")
                    continue
                seen_ids.add(identity)
                required_fields = ("Status", "Components", "Implementation estimate hours",
                                   "Testing estimate hours", "Estimate basis", "Relevant tests")
                missing = [name for name in required_fields if not field(name)]
                if missing:
                    errors.append(f"{repo}:{rel}:{debt_id}: missing {', '.join(missing)}")
                items.append(DebtItem(
                    repository=repo, debt_id=debt_id, title=heading.group(2).strip(),
                    status=field("Status").lower(),
                    components=[x.strip() for x in field("Components").split(";") if x.strip()],
                    implementation_hours=estimate("Implementation estimate hours"),
                    testing_hours=estimate("Testing estimate hours"),
                    estimate_basis=field("Estimate basis"),
                    relevant_tests=[x.strip() for x in field("Relevant tests").split(";") if x.strip()],
                    evidence_id=evidence_id, path=rel, body=body.strip(),
                ).__dict__)
        return items, errors
