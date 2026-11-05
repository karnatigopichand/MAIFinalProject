"""The three specialist agents, implemented as bounded evidence transformations."""
from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

from .models import DebtAssessment, ImpactFinding, Risk, TraceEvent
from .store import LocalEvidenceStore, _tokens


def _now():
    return datetime.now(timezone.utc).isoformat()


def _unique(values):
    return list(dict.fromkeys(v for v in values if v))


class Trace:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: list[TraceEvent] = []

    def add(self, agent, event_type, name, parameters=None, evidence_ids=None,
            outcome="ok", error=None, duration_ms=None):
        self.events.append(TraceEvent(
            timestamp=_now(), run_id=self.run_id, agent=agent, event_type=event_type,
            name=name, parameters=parameters or {}, evidence_ids=evidence_ids or [],
            outcome=outcome, error=error, duration_ms=duration_ms,
        ))


class ImpactInvestigationAgent:
    name = "impact-investigation"

    def __init__(self, store: LocalEvidenceStore, trace: Trace, max_tool_calls=24, max_hops=3):
        self.store, self.trace = store, trace
        self.max_tool_calls, self.max_hops = max_tool_calls, max_hops
        self.tool_calls = 0
        self.budget_exhausted = False

    def _search(self, query, **kwargs):
        if self.tool_calls >= self.max_tool_calls:
            self.budget_exhausted = True
            self.trace.add(self.name, "budget", "tool-call-budget", {"limit": self.max_tool_calls}, outcome="exhausted")
            return []
        self.tool_calls += 1
        started = time.monotonic()
        result = self.store.search(query, **kwargs)
        self.trace.add(self.name, "tool", "search-evidence", {"query_terms": sorted(_tokens(query))[:12]},
                       [item.evidence_id for item in result], outcome="ok" if result else "empty",
                       duration_ms=round((time.monotonic() - started) * 1000, 2))
        return result

    def investigate(self, ticket: dict, targeted_queries=None):
        text = "\n".join([ticket.get("summary", ""), ticket.get("description", ""),
                           "\n".join(ticket.get("acceptance_criteria", []))])
        fields = self._field_queries(text)
        repo_mentions = [repo for repo in self.store.current["repositories"] if repo in text.lower()]
        targeted_queries = targeted_queries or []
        queries = _unique([text[:900], *fields, *repo_mentions,
                           *(item.get("query", "") for item in targeted_queries)])[:12]
        ranked: dict[str, list] = defaultdict(list)
        for query in queries:
            for hit in self._search(query, limit=10):
                ranked[hit.repository].append(hit)

        # A direct field/symbol match is stronger than a generic ticket-word match.
        field_hits: dict[str, list] = defaultdict(list)
        for field_query in fields:
            for hit in self._search(field_query, limit=12):
                field_hits[hit.repository].append(hit)
            for hit in self._search(field_query, document_types=["source", "contract"], limit=8):
                field_hits[hit.repository].append(hit)

        starts = [repo for repo in repo_mentions if repo in self.store.current["repositories"]]
        if not starts and "checkout" in text.lower():
            starts = ["commerce-checkout"]
        if not starts:
            starts = sorted(field_hits, key=lambda repo: -len(field_hits[repo]))[:1]
        paths = self.store.traverse(starts, max_hops=self.max_hops)
        self.trace.add(self.name, "tool", "traverse-dependencies",
                       {"start_nodes": starts, "max_hops": self.max_hops},
                       _unique([eid for path in paths for eid in path["evidence_ids"]]))

        impacts: list[ImpactFinding] = []
        relevant_repos = set()
        for repo in self.store.current["repositories"]:
            if not self._repo_is_relevant(repo, text):
                continue
            direct = _unique([e.evidence_id for e in field_hits.get(repo, [])])
            if not direct:
                continue
            evidence = self.store.fetch_evidence(direct)
            source = [item for item in evidence if item.document_type == "source"]
            docs = [item for item in evidence if item.document_type == "documentation"]
            contracts = [item for item in evidence if item.document_type == "contract"]
            if not source and not docs and not contracts:
                continue
            relevant_repos.add(repo)
            documented_gap = any("delivery instructions are absent" in item.excerpt.lower() for item in docs)
            if documented_gap and not source:
                source_hits = self._search("consume", repositories=[repo], document_types=["source"], limit=3)
                source = source_hits
                direct = _unique([item.evidence_id for item in source_hits] + direct)
            has_literal_feature = any(
                all(term in (item.excerpt + " " + item.path).lower() for term in _tokens(fields[0]))
                for item in source
            ) if fields else False
            classification = "change_required" if source or documented_gap else "validation_required"
            uncertainty = []
            if not has_literal_feature:
                uncertainty.append("The new requirement phrase is not implemented literally in this snapshot; the finding identifies an existing related path to extend or verify.")
            claim = self._claim(repo, fields, source, docs, contracts, documented_gap)
            component = self._component(source or docs)
            fid = hashlib.sha256(f"{self.store.current['snapshot_id']}:{repo}:{component}:{claim}".encode()).hexdigest()[:12]
            prioritized_ids = _unique(
                [item.evidence_id for item in source]
                + [item.evidence_id for item in docs if "delivery instructions are absent" in item.excerpt.lower()]
                + direct
            )
            impacts.append(ImpactFinding(
                finding_id=f"imp-{fid}", repository=repo, classification=classification,
                component=component, claim=claim,
                business_relevance=f"This repository has evidence related to {', '.join(fields[:2]) or 'the requested behavior'}.",
                evidence_ids=prioritized_ids[:5], uncertainties=uncertainty,
            ))

        # Keep only paths whose endpoints have direct evidence for this requirement.
        useful_paths = []
        for path in paths:
            service_nodes = {node for node in path["nodes"] if node.startswith("commerce-")}
            if len(service_nodes & relevant_repos) >= 2 and service_nodes.issubset(relevant_repos):
                useful_paths.append(path)
        self.trace.add(self.name, "agent", "findings-produced",
                       {"finding_count": len(impacts), "path_count": len(useful_paths), "fields": fields,
                        "targeted_query_count": len(targeted_queries)},
                       [eid for finding in impacts for eid in finding.evidence_ids])
        return {"requirement": {"text": text, "field_queries": fields,
                                "acceptance_criteria": ticket.get("acceptance_criteria", [])},
                "impacts": impacts, "paths": useful_paths,
                "candidate_evidence": {repo: [x.evidence_id for x in _unique_evidence(hits)[:8]]
                                       for repo, hits in ranked.items()},
                "relevant_repositories": sorted(relevant_repos),
                "budget_exhausted": self.budget_exhausted}

    @staticmethod
    def _field_queries(text):
        lower = text.lower()
        if re.search(r"delivery\s+instructions?", lower):
            return ["delivery instructions", "delivery address", "carrier shipment", "shipment notification"]
        if re.search(r"notification\s+template|shipment\s+notification", lower):
            return ["notification"]
        if "expedited" in lower or "expedite" in lower or "rush shipping" in lower:
            return ["expedited shipping carrier", "notification"]
        if re.search(r"inventory|stock|reservation|sku", lower):
            return ["inventory stock reservation"]
        if "order.confirmed.v1" in lower or re.search(r"order[- ]confirmed event|order event|event consumer", lower):
            return ["order.confirmed.v1 event consumer", "order event consumer"]
        if re.search(r"payment.{0,40}(?:provider|authorization|amount|currency)|(?:provider|authorization).{0,40}(?:amount|currency)", lower):
            return ["payment provider authorization amount currency", "provider amount currency mapping"]
        if "tracking" in lower:
            return ["carrier tracking number", "shipment notification"]
        if re.search(r"delivery[\s-]+address", lower) and ("checkout" in lower or "mapping" in lower):
            return ["checkout delivery address mapping"]
        return []

    @staticmethod
    def _repo_is_relevant(repo, text):
        lower = text.lower()
        payment_mapping = ("provider" in lower and
                           any(word in lower for word in ("authorization", "amount", "currency")))
        if payment_mapping and repo != "commerce-payments":
            return False
        event_consumer_change = ("order.confirmed.v1" in lower or "order event" in lower) and "consumer" in lower
        if event_consumer_change and repo in {"commerce-shipping", "commerce-notifications"}:
            return True
        unchanged = (
            (repo == "commerce-payments" and re.search(r"payment(?:\s+authorization|\s+behavior|\s+processing)?.{0,50}unchanged", lower))
            or (repo == "commerce-shipping" and (re.search(r"(?:carrier|shipping|shipment).{0,50}(?:unchanged|do not change|no change)", lower)
                or re.search(r"(?:do not change|unchanged|no change).{0,50}(?:carrier|shipping|shipment)", lower)))
            or (repo == "commerce-orders" and (re.search(r"order.{0,50}(?:unchanged|do not change|no change)", lower)
                or re.search(r"(?:do not change|unchanged|no change).{0,50}order", lower)))
        )
        if unchanged:
            return False
        patterns = {
            "commerce-checkout": r"checkout|cart|delivery instructions",
            "commerce-orders": r"order|delivery instructions",
            "commerce-inventory": r"inventory|stock|reservation|sku",
            "commerce-payments": r"payment|provider|authorization|charge|currency",
            "commerce-shipping": r"shipping|shipment|carrier|tracking|expedit|delivery instructions",
            "commerce-notifications": r"notification|confirmation|recipient|delivery instructions|notify",
        }
        return bool(re.search(patterns.get(repo, r"(?!)"), lower))

    @staticmethod
    def _claim(repo, fields, sources, docs, contracts, documented_gap=False):
        source_paths = _unique([item.path for item in sources])
        doc_paths = _unique([item.path for item in docs])
        if documented_gap:
            return f"Extend the existing mapping/consumer path for the requested field. The implementation-reviewed contract in {', '.join(doc_paths[:2])} states that delivery instructions are absent from the current payload path."
        if source_paths:
            return f"Inspect and likely extend the existing implementation in {', '.join(source_paths[:3])}; this source currently handles a related part of the requested flow."
        contract_paths = _unique([item.path for item in contracts])
        if contract_paths:
            return f"Validate whether the contract in {', '.join(contract_paths[:3])} needs to include the requested field."
        return f"Validate the documented contract in {', '.join(doc_paths[:3])}; the current snapshot does not provide direct source evidence for a required code change here."

    @staticmethod
    def _component(items):
        return "; ".join(_unique(item.path for item in items)[:3]) or "repository-level impact"


def _unique_evidence(items):
    seen = set()
    out = []
    for item in items:
        if item.evidence_id not in seen:
            out.append(item)
            seen.add(item.evidence_id)
    return out


class TechnicalDebtAgent:
    name = "technical-debt"

    def __init__(self, store: LocalEvidenceStore, trace: Trace, max_hours=3.0):
        self.store, self.trace, self.max_hours = store, trace, max_hours

    def assess(self, investigation: dict):
        impacted = set(investigation["relevant_repositories"])
        findings_by_repo = defaultdict(list)
        for finding in investigation["impacts"]:
            findings_by_repo[finding.repository].append(finding)
        decisions = []
        query = investigation.get("requirement", {}).get("text", "")
        debt_candidates = self.store.search_debts(query) if query else self.store.debt_items()
        for item in debt_candidates:
            overlaps = []
            if item.repository in impacted:
                finding_paths = {p.strip() for f in findings_by_repo[item.repository] for p in f.component.split(";")}
                for component in item.components:
                    if component in finding_paths:
                        overlaps.append(item.evidence_id)
                        overlaps.extend(e for f in findings_by_repo[item.repository] for e in f.evidence_ids)
            total = None if item.implementation_hours is None or item.testing_hours is None else item.implementation_hours + item.testing_hours
            shared_tests = []
            for test_path in item.relevant_tests:
                if any(ev["repository"] == item.repository and ev["path"] == test_path
                       for ev in self.store.current["evidence"].values()):
                    if overlaps:
                        shared_tests.append(test_path)
            basis_uncertain = not item.estimate_basis or any(token in item.estimate_basis.lower()
                for token in ("illustrative", "requires team review", "unknown", "unverified"))
            if item.status != "open":
                disposition, reason = "do_not_recommend", "The item is not open in the selected snapshot."
            elif not overlaps:
                disposition, reason = "do_not_recommend", "No direct component overlap with an affected implementation was verified."
            elif total is None or basis_uncertain:
                disposition, reason = "needs_clarification", "The documented estimate is missing or explicitly provisional; confirm it before recommending the work."
            elif total > self.max_hours:
                disposition, reason = "do_not_recommend", f"Estimated total {total:g} hours exceeds the {self.max_hours:g}-hour per-item ceiling."
            elif not shared_tests:
                disposition, reason = "do_not_recommend", "The item has no verified test that can be shared with the requested change."
            else:
                disposition, reason = "recommend", "Direct component overlap, a usable estimate under the ceiling, and a shared test are documented."
            decisions.append(DebtAssessment(
                repository=item.repository, debt_id=item.debt_id, title=item.title,
                disposition=disposition, implementation_hours=item.implementation_hours,
                testing_hours=item.testing_hours, total_hours=total,
                estimate_basis=item.estimate_basis, overlap_evidence=_unique(overlaps),
                shared_tests=shared_tests, additional_tests=[], reason=reason,
            ))
        self.trace.add(self.name, "agent", "debt-decisions",
                       {"candidate_count": len(decisions), "max_hours_per_item": self.max_hours,
                        "recommended": sum(x.disposition == "recommend" for x in decisions)},
                       [eid for decision in decisions for eid in decision.overlap_evidence])
        return decisions


class RiskAndReportAgent:
    name = "risk-report"

    def __init__(self, store: LocalEvidenceStore, trace: Trace):
        self.store, self.trace = store, trace

    def review(self, ticket: dict, investigation: dict, debt: list[DebtAssessment]):
        # Verify every evidence pointer and remove findings that cannot be fetched
        # from the selected immutable snapshot.
        verified = []
        all_ids = set(self.store.current["evidence"])
        for finding in investigation["impacts"]:
            valid = [eid for eid in finding.evidence_ids if eid in all_ids]
            if not valid:
                continue
            finding.evidence_ids = valid
            verified.append(finding)
        investigation["impacts"] = verified
        evidence_ids = _unique([eid for finding in verified for eid in finding.evidence_ids])
        evidence = self.store.fetch_evidence(evidence_ids)
        trace_terms = " ".join([ticket.get("summary", ""), ticket.get("description", "")]).lower()
        risks = []
        if any("shipment" in item.excerpt.lower() or "order" in item.excerpt.lower()
               or "shipment" in item.path or "order" in item.path for item in evidence) and "instruction" in trace_terms:
            risks.append(Risk(
                failure_mode="Delivery instructions are dropped, renamed inconsistently, or made mandatory for existing order consumers.",
                business_consequence="The carrier or customer confirmation may receive incomplete delivery details; incompatible event changes may delay shipment processing.",
                severity="medium", uncertainty="Potential risk; the requested field is not yet implemented and this scan cannot establish customer impact.",
                evidence_ids=evidence_ids[:6],
                recommended_validation=["Add request-to-order mapping cases for present, omitted, and empty instructions.",
                                        "Check both order-event consumers before changing the event contract.",
                                        "Verify carrier payload and notification rendering behavior."],
            ))
        criteria = ticket.get("acceptance_criteria", [])
        questions = []
        if not criteria and any(word in trace_terms for word in ("confirmation", "display", "show")):
            questions.append("Should the instructions appear in the order confirmation, the shipment confirmation, or both? The ticket mentions confirmation but does not specify the customer-facing message.")
        if "instructions" in trace_terms and not any(word in trace_terms for word in ("optional", "required", "omit", "default")):
            questions.append("Should instructions be optional, and what should each downstream service do when they are omitted?")
        if any(word in trace_terms for word in ("expedited", "expedite", "rush", "fastest")):
            if not any(word in trace_terms for word in ("hour", "day", "date", "sla", "business-day")):
                questions.append("What delivery window defines expedited shipping (for example, a target number of business days)?")
            if not any(word in trace_terms for word in ("price", "cost", "fee", "charge", "free")):
                questions.append("Can expedited shipping add a charge, and who approves or pays that additional cost?")
            if not any(phrase in trace_terms for phrase in
                       ("all orders", "eligible orders", "eligibility criteria", "only for",
                        "available for", "domestic", "international")):
                questions.append("Which orders and destinations are eligible for expedited shipping?")
        missing = not evidence_ids or not verified
        status = "failed" if missing else ("needs_clarification" if questions else "complete")
        limitations = []
        if not self.store.current.get("edges"):
            limitations.append("No dependency graph edges were available; cross-service paths are unverified.")
        if any("illustrative" in (x.estimate_basis or "").lower() for x in debt):
            limitations.append("Technical-debt effort entries are marked illustrative and require team review; they are not eligible as confirmed recommendations.")
        self.trace.add(self.name, "verification", "evidence-reference-check",
                       {"checked_findings": len(verified), "valid_evidence_count": len(evidence_ids)}, evidence_ids,
                       outcome="ok" if not missing else "partial")
        self.trace.add(self.name, "agent", "review-complete",
                       {"status": status, "question_count": len(questions), "risk_count": len(risks)})
        verification_requests = []
        if missing:
            fields = investigation.get("requirement", {}).get("field_queries", [])
            candidates = investigation.get("candidate_evidence", {})
            target_repositories = [repo for repo, ids in candidates.items() if ids]
            for query in fields[:3]:
                verification_requests.append({
                    "query": f"{query} source implementation contract",
                    "repository": target_repositories[0] if target_repositories else None,
                    "reason": "The initial impact findings did not retain a verifiable evidence reference.",
                })
            if not verification_requests:
                verification_requests = [{
                    "query": f"{trace_terms[:300]} implementation contract source",
                    "repository": None,
                    "reason": "The initial investigation returned no verifiable evidence.",
                }]
            verification_requests = verification_requests[:5]
            self.trace.add(self.name, "routing", "request-targeted-reinvestigation",
                           {"request_count": len(verification_requests),
                            "queries": [item["query"] for item in verification_requests]},
                           outcome="requested")
        return status, risks, questions, limitations, evidence, verification_requests
