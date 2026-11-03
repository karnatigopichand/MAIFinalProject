"""Read-only evidence adapters and a deterministic local corpus implementation.

The protocol is the seam for later Pinecone, Neo4j, and source-snapshot adapters.
This module intentionally has no network or credential dependencies.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Protocol

from .models import DependencyPath, Evidence


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with", "will", "should", "must", "allow", "change", "support", "ensure", "when", "where", "which", "what", "how",
}


def terms(text: str) -> set[str]:
    """Split prose, snake_case, and camelCase into useful lowercase terms."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    found = re.findall(r"[A-Za-z][A-Za-z0-9]*", text.replace("_", " "))
    return {word.lower() for word in found if len(word) > 1 and word.lower() not in STOP_WORDS}


@dataclass(frozen=True)
class EvidenceFile:
    repository: str
    path: str
    text: str
    document_type: str


class ImpactTools(Protocol):
    snapshot_id: str

    def search_docs(self, query: str, snapshot_id: str, repositories: Iterable[str] | None = None, limit: int = 20) -> list[Evidence]: ...
    def search_identifiers(self, query: str, snapshot_id: str, repositories: Iterable[str] | None = None, limit: int = 20) -> list[Evidence]: ...
    def traverse_dependencies(self, start_ids: Iterable[str], snapshot_id: str, max_hops: int = 3, direction: str = "both", limit: int = 50) -> list[DependencyPath]: ...
    def fetch_evidence(self, evidence_ids: Iterable[str], snapshot_id: str) -> list[Evidence]: ...
    def get_contract(self, repository: str, snapshot_id: str) -> dict | None: ...


class LocalCorpusTools:
    """Search sample-repositories locally and build a small graph from contracts.json."""

    def __init__(self, corpus_root: str | Path):
        self.corpus_root = Path(corpus_root).resolve()
        if not self.corpus_root.is_dir():
            raise FileNotFoundError(f"Corpus directory not found: {self.corpus_root}")
        self.files: list[EvidenceFile] = []
        self.contracts: dict[str, dict] = {}
        self._evidence_by_id: dict[str, Evidence] = {}
        self._edges: list[tuple[str, str, str, Evidence]] = []
        self._load()
        digest = hashlib.sha256()
        for record in sorted(self.files, key=lambda item: (item.repository, item.path)):
            digest.update(record.repository.encode())
            digest.update(record.path.encode())
            digest.update(record.text.encode())
        self.snapshot_id = f"local-sha256:{digest.hexdigest()}"
        self.repo_manifest = {repo: self.snapshot_id for repo in sorted(self.contracts)}
        self._build_graph()

    def _load(self) -> None:
        for repo_dir in sorted(self.corpus_root.glob("commerce-*")):
            if not repo_dir.is_dir():
                continue
            repo = repo_dir.name
            contract_path = repo_dir / "contracts.json"
            if contract_path.exists():
                self.contracts[repo] = json.loads(contract_path.read_text(encoding="utf-8"))
            paths = [contract_path, repo_dir / "README.md"]
            paths.extend(sorted((repo_dir / "src").rglob("*.py")) if (repo_dir / "src").exists() else [])
            paths.extend(sorted((repo_dir / "docs").rglob("*.md")) if (repo_dir / "docs").exists() else [])
            paths.extend(sorted((repo_dir / "docs").rglob("*.json")) if (repo_dir / "docs").exists() else [])
            seen: set[Path] = set()
            for path in paths:
                if path in seen or not path.is_file():
                    continue
                seen.add(path)
                relative = path.relative_to(repo_dir).as_posix()
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if relative == "contracts.json" or relative.endswith(".json"):
                    kind = "contract"
                elif relative.startswith("src/"):
                    kind = "source"
                elif "/technical-debt/" in f"/{relative}/":
                    kind = "technical_debt"
                else:
                    kind = "documentation"
                self.files.append(EvidenceFile(repo, relative, text, kind))

    def _check_snapshot(self, snapshot_id: str) -> None:
        if snapshot_id != self.snapshot_id:
            raise ValueError(f"Snapshot mismatch: requested {snapshot_id}, available {self.snapshot_id}")

    def _make_evidence(self, record: EvidenceFile, line_start: int, line_end: int, excerpt: str, method: str) -> Evidence:
        evidence_id = hashlib.sha256(f"{self.snapshot_id}:{record.repository}:{record.path}:{line_start}:{line_end}".encode()).hexdigest()[:16]
        evidence = Evidence(evidence_id, record.repository, self.snapshot_id, record.path, line_start, line_end, excerpt.strip(), record.document_type, method)
        self._evidence_by_id[evidence_id] = evidence
        return evidence

    def _search(self, query: str, snapshot_id: str, repositories: Iterable[str] | None, limit: int, method: str, exact: bool) -> list[Evidence]:
        self._check_snapshot(snapshot_id)
        query_terms = terms(query)
        if not query_terms:
            return []
        allowed = set(repositories) if repositories else None
        matches: list[tuple[int, Evidence]] = []
        for record in self.files:
            if allowed is not None and record.repository not in allowed:
                continue
            lines = record.text.splitlines()
            text_terms = terms(record.text)
            overlap = query_terms & text_terms
            if not overlap:
                continue
            if exact:
                # Exact-identifier mode requires at least one identifier token or original phrase match.
                identifiers = {item for item in re.findall(r"[A-Za-z][A-Za-z0-9_./:-]*", query) if len(item) > 2}
                joined = "\n".join(lines).lower()
                identifier_hits = sum(1 for item in identifiers if item.lower() in joined)
                if identifier_hits == 0 and not any(token in joined for token in query_terms if "_" in query):
                    continue
                score = 10 * identifier_hits + len(overlap)
                positions = [i for i, line in enumerate(lines) if any(item.lower() in line.lower() for item in identifiers)]
            else:
                score = len(overlap) + sum(1 for phrase in (query.strip().lower(),) if len(phrase) > 3 and phrase in record.text.lower()) * 3
                positions = [i for i, line in enumerate(lines) if terms(line) & query_terms]
            if not positions:
                positions = [0]
            start = max(0, positions[0] - 2)
            end = min(len(lines), max(positions[0] + 3, start + 1))
            evidence = self._make_evidence(record, start + 1, end, "\n".join(lines[start:end])[:1200], method)
            matches.append((score, evidence))
        matches.sort(key=lambda pair: (-pair[0], pair[1].repository, pair[1].path))
        return [item for _, item in matches[:max(0, limit)]]

    def search_docs(self, query: str, snapshot_id: str, repositories: Iterable[str] | None = None, limit: int = 20) -> list[Evidence]:
        return self._search(query, snapshot_id, repositories, limit, "local_lexical_search", False)

    def search_identifiers(self, query: str, snapshot_id: str, repositories: Iterable[str] | None = None, limit: int = 20) -> list[Evidence]:
        return self._search(query, snapshot_id, repositories, limit, "local_identifier_search", True)

    def fetch_evidence(self, evidence_ids: Iterable[str], snapshot_id: str) -> list[Evidence]:
        self._check_snapshot(snapshot_id)
        missing = [item for item in evidence_ids if item not in self._evidence_by_id]
        if missing:
            raise KeyError(f"Evidence IDs were not issued by this local snapshot: {', '.join(missing)}")
        return [self._evidence_by_id[item] for item in evidence_ids]

    def get_contract(self, repository: str, snapshot_id: str) -> dict | None:
        self._check_snapshot(snapshot_id)
        return self.contracts.get(repository)

    def _build_graph(self) -> None:
        for repo, contract in self.contracts.items():
            repo_node = f"repository:{repo}"
            contract_evidence = next((self._make_evidence(record, 1, min(30, len(record.text.splitlines())), record.text[:1200], "contract_graph") for record in self.files if record.repository == repo and record.path == "contracts.json"), None)
            if contract_evidence is None:
                continue
            for call in contract.get("calls", []):
                target = call.get("target")
                if target:
                    self._edges.append((repo_node, f"repository:{target}", "CALLS", contract_evidence))
            for topic in contract.get("publishes", []):
                self._edges.append((repo_node, f"event:{topic}", "PUBLISHES", contract_evidence))
            for topic in contract.get("consumes", []):
                self._edges.append((f"event:{topic}", repo_node, "CONSUMES", contract_evidence))
            for field_name, mapping in contract.get("mappings", {}).items():
                self._edges.append((repo_node, f"field:{field_name}", "MAPS_TO", contract_evidence))

    def traverse_dependencies(self, start_ids: Iterable[str], snapshot_id: str, max_hops: int = 3, direction: str = "both", limit: int = 50) -> list[DependencyPath]:
        self._check_snapshot(snapshot_id)
        if direction not in {"out", "in", "both"}:
            raise ValueError("direction must be 'out', 'in', or 'both'")
        paths: list[DependencyPath] = []
        for start in start_ids:
            queue = deque([(start, (start,), (), ())])
            visited = {start}
            while queue and len(paths) < limit:
                node, nodes, relations, evidence_ids = queue.popleft()
                if len(relations) >= max_hops:
                    continue
                for source, target, relation, evidence in self._edges:
                    next_node = None
                    if direction in {"out", "both"} and source == node:
                        next_node = target
                    elif direction in {"in", "both"} and target == node:
                        next_node = source
                    if next_node is None or next_node in visited:
                        continue
                    visited.add(next_node)
                    next_nodes = nodes + (next_node,)
                    next_relations = relations + (relation,)
                    next_evidence = evidence_ids + (evidence.evidence_id,)
                    paths.append(DependencyPath(next_nodes, next_relations, next_evidence, "explicit"))
                    queue.append((next_node, next_nodes, next_relations, next_evidence))
        return paths
