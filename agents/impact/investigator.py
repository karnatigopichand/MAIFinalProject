"""Bounded local-first investigation; remote services can replace the tool adapter."""
from __future__ import annotations

from collections import defaultdict
import re
import uuid
from typing import Iterable

from .models import DependencyPath, ImpactFinding, InvestigationResult, Requirement, RunContext, Ticket
from .tools import ImpactTools, terms

ISSUE_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
FIELD = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


class ImpactInvestigationAgent:
    """Investigate a ticket against an injected, read-only evidence adapter."""

    def __init__(self, tools: ImpactTools, max_tool_calls: int = 20, max_graph_hops: int = 3, result_limit: int = 25):
        self.tools = tools
        self.max_tool_calls = max_tool_calls
        self.max_graph_hops = max_graph_hops
        self.result_limit = result_limit

    def investigate(self, ticket: Ticket | dict, verification_requests: Iterable[dict] | None = None) -> InvestigationResult:
        if isinstance(ticket, dict):
            ticket = Ticket.from_dict(ticket)
        if not ticket.summary and not ticket.description:
            raise ValueError("Ticket must include a summary or description")

        all_text = " ".join((ticket.summary, ticket.description, *ticket.acceptance_criteria)).strip()
        fields = tuple(sorted(set(FIELD.findall(all_text))))
        entities = tuple(sorted({"commerce-" + name for name in ("checkout", "orders", "inventory", "payments", "shipping", "notifications") if name in all_text.lower()}))
        ambiguities = self._ambiguities(all_text)
        requirement = Requirement(
            requested_behavior=" ".join(part for part in (ticket.summary, ticket.description) if part).strip(),
            acceptance_criteria=ticket.acceptance_criteria,
            entities=entities,
            fields=fields,
            ambiguities=ambiguities,
        )
        context = RunContext(
            run_id=str(uuid.uuid4()), ticket_id=ticket.ticket_id, ticket_version=ticket.version,
            snapshot_id=self.tools.snapshot_id, repo_manifest=dict(self.tools.repo_manifest),
            max_tool_calls=self.max_tool_calls, max_graph_hops=self.max_graph_hops,
        )
        trace: list[dict] = []
        evidence_by_id = {}
        budget = self.max_tool_calls

        def spend(name: str, action):
            nonlocal budget
            if budget <= 0:
                return []
            budget -= 1
            try:
                result = action()
                trace.append({"tool": name, "status": "ok", "result_count": len(result), "remaining_budget": budget})
                for item in result:
                    if hasattr(item, "evidence_id"):
                        evidence_by_id[item.evidence_id] = item
                return result
            except Exception as exc:  # Fail soft: preserve supported evidence and expose the gap.
                trace.append({"tool": name, "status": "error", "error_type": type(exc).__name__, "remaining_budget": budget})
                return []

        docs = spend("search_docs", lambda: self.tools.search_docs(all_text, context.snapshot_id, limit=self.result_limit))
        # Search field identifiers separately so mapping evidence can be found despite prose wording.
        identifier_query = " ".join(fields) if fields else ticket.summary
        identifiers = spend("search_identifiers", lambda: self.tools.search_identifiers(identifier_query, context.snapshot_id, limit=self.result_limit))
        for item in identifiers:
            evidence_by_id[item.evidence_id] = item
        direct = list({item.evidence_id: item for item in [*docs, *identifiers]}.values())

        # Mark repository candidates from retrieved evidence, then inspect explicit graph neighbors.
        direct_by_repo: dict[str, list] = defaultdict(list)
        for item in direct:
            direct_by_repo[item.repository].append(item)
        starts = [f"repository:{repo}" for repo in sorted(direct_by_repo)]
        graph_paths = spend("traverse_dependencies", lambda: self.tools.traverse_dependencies(starts, context.snapshot_id, max_hops=self.max_graph_hops, direction="both", limit=self.result_limit)) if starts else []
        for path in graph_paths:
            # Graph edge evidence is fetched from the same immutable corpus to retain provenance.
            edge_ids = [item for item in path.evidence_ids if item not in evidence_by_id]
            if edge_ids:
                fetched = spend("fetch_evidence", lambda ids=edge_ids: self.tools.fetch_evidence(ids, context.snapshot_id))
                evidence_by_id.update({item.evidence_id: item for item in fetched})

        related_issue_keys = tuple(sorted(set(ISSUE_KEY.findall(all_text)) - {ticket.ticket_id}))
        connected: dict[str, list[DependencyPath]] = defaultdict(list)
        for path in graph_paths:
            for node in path.nodes:
                if node.startswith("repository:"):
                    connected[node.removeprefix("repository:")].append(path)

        findings: list[ImpactFinding] = []
        all_repos = sorted(set(direct_by_repo) | set(connected))
        query_terms = terms(all_text)
        for repo in all_repos:
            evidence_items = direct_by_repo.get(repo, [])
            is_direct = bool(evidence_items)
            path_items = connected.get(repo, [])
            if not is_direct and not path_items:
                continue
            direct_source = [item for item in evidence_items if item.document_type == "source"]
            direct_contract = [item for item in evidence_items if item.document_type == "contract"]
            if direct_source:
                classification = "change_required"
                basis = "Relevant implementation source was retrieved; verify the cited behavior against the change's acceptance criteria."
            elif direct_contract:
                classification = "validation_required"
                basis = "A service contract or mapping matches the request, but the inspected source does not establish that a code change is required."
            elif is_direct:
                classification = "possible_impact"
                basis = "Documentation is relevant, but direct implementation evidence was not found."
            else:
                classification = "possible_impact"
                basis = "The component is connected to a directly relevant component in the explicit dependency graph; its impact is not yet demonstrated."
            best_evidence = evidence_items[:5]
            ids = [item.evidence_id for item in best_evidence]
            if not is_direct:
                for path in path_items[:2]:
                    ids.extend(path.evidence_ids)
            uncertainty = []
            if classification != "change_required":
                uncertainty.append("Impact is not proven by a matching implementation source excerpt.")
            if ambiguities:
                uncertainty.extend(ambiguities[:2])
            findings.append(ImpactFinding(
                finding_id=f"impact-{len(findings)+1}", repository=repo, component=repo,
                classification=classification,
                claim=f"{repo} may need investigation for this requirement. {basis}",
                business_relevance="Potential effect on the requested behavior or its documented service dependencies.",
                evidence_ids=tuple(dict.fromkeys(ids)), uncertainties=tuple(dict.fromkeys(uncertainty)),
            ))

        # Paths rooted in direct hits only, to prevent unrelated graph walks from appearing as impact evidence.
        direct_nodes = set(starts)
        selected_paths = tuple(path for path in graph_paths if path.nodes and path.nodes[0] in direct_nodes)
        evidence = tuple(sorted(evidence_by_id.values(), key=lambda item: (item.repository, item.path, item.line_start)))
        limitations = [
            "The prototype searches the local sample-repositories corpus with deterministic lexical matching; it does not use an LLM or semantic vector retrieval.",
            "Jira, Pinecone, and Neo4j are not connected. Related issue keys mentioned in the input are not looked up or verified.",
            "The result is limited to the inspected local snapshot; absence of a match is not proof of no impact.",
        ]
        if budget <= 0:
            limitations.append("The configured tool-call budget was exhausted; some evidence or dependency branches may not have been inspected.")
        if not graph_paths and starts:
            limitations.append("No dependency path was returned; this may reflect missing graph evidence rather than absence of a dependency.")
        if not findings:
            limitations.append("No matching local evidence was found for the request.")
        questions = list(ambiguities)
        if not fields:
            questions.append("Which specific data fields, APIs, events, or business rules should this change affect?")
        status = "partial" if budget <= 0 or any(item.get("status") == "error" for item in trace) else ("needs_clarification" if questions else "complete")
        return InvestigationResult(context, requirement, status, tuple(findings), selected_paths, evidence,
                                   related_issue_keys, tuple(dict.fromkeys(questions)), tuple(dict.fromkeys(limitations)), tuple(trace))

    @staticmethod
    def _ambiguities(text: str) -> tuple[str, ...]:
        lower = text.lower()
        questions = []
        if any(word in lower for word in ("fast", "quick", "better", "seamless", "user-friendly")):
            questions.append("The request uses a subjective outcome; what measurable acceptance criteria define success?")
        if "optional" in lower or "optional" in lower:
            questions.append("Should the new value be optional, and what behavior is required when it is omitted?")
        if "display" in lower and any(word in lower for word in ("confirmation", "notification", "receipt")):
            questions.append("Which confirmation or notification surfaces should display the value?")
        return tuple(questions)
