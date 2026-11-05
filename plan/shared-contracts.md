# Shared contracts and integration plan

## Development agreement

Use the versioned contracts in `impact_assessment/models.py` as the executable local baseline. They currently use standard-library dataclasses so local replay has no extra dependency. Add Pydantic validation at persisted and hosted agent boundaries before enabling external model/tool calls. Version contracts and validate at every agent boundary.

## Core artifacts

| Artifact | Required fields |
|---|---|
| `RunContext` | `run_id`, `ticket_id`, `ticket_version`, `snapshot_id`, repository-to-commit manifest, limits, contract version |
| `Requirement` | requested behavior, acceptance criteria, entities/fields, assumptions, ambiguities |
| `Evidence` | `evidence_id`, repository, commit, path, symbol/line range where available, excerpt, document/source type, extraction method |
| `DependencyPath` | ordered node IDs, relationship types, evidence IDs per edge, explicit/inferred/ambiguous classification |
| `ImpactFinding` | finding ID, repository/component, impact classification, claim, business relevance, evidence IDs, uncertainties |
| `DebtAssessment` | repository/debt ID, disposition, implementation/testing hours, estimate origin, overlap evidence, shared/additional tests, incremental scope |
| `VerificationRequest` | target agent, finding/debt IDs, missing support, specific investigation question |
| `Risk` | failure mode, business consequence, severity, evidence IDs, uncertainty, recommended validation |
| `Assessment` | context, status, impacts, paths, risks, debt assessments, questions, limitations, Markdown report |
| `TraceEvent` | run/agent/tool IDs, timestamp, event type, sanitized parameters, evidence IDs, outcome/error, duration |

Agents receive structured artifacts and reference a shared evidence store. Avoid compressing all evidence into successive prose summaries. Evidence IDs must remain stable within a snapshot.

## Shared run state

The coordinator holds context, requirement, impact findings, debt assessments, evidence references, verification requests, retry count, status, and final result. Each agent returns a bounded state update; it must not mutate another agent's output silently. Preserve revisions so the trace can show why a finding changed.

Interfaces:

```text
investigate(context, ticket, verification_requests?) -> InvestigationResult
assess_debt(context, requirement, investigation) -> DebtResult
verify_and_report(context, requirement, investigation, debt) -> ReviewResult

ReviewResult = targeted_requests | final_assessment
```

Changing investigation findings invalidates overlapping debt decisions. Rerun debt assessment for changed components before final reporting. The coordinator handles this dependency.

## Tool boundaries

Retrieval MCP server:

```text
search_docs
search_technical_debt
search_identifiers
traverse_dependencies
fetch_evidence
get_contract
```

All tools accept/validate a snapshot ID and return provenance and explicit empty/error outcomes. Traversal uses approved relationship types, direction, maximum depth, and result bounds.

Separate controlled write pipeline:

```text
prepare_snapshot -> generate_docs -> upsert_embeddings
                 -> upsert_graph -> validate_snapshot -> publish_snapshot
```

The refresh workflow can expose typed write operations if a tool interface is needed. Assessment agents have read access to application evidence. Result persistence and Jira commenting are dedicated integration operations, not arbitrary database writes chosen by an LLM.

## Initial AI-system layout

```text
agents/impact/
agents/technical_debt/
agents/risk_report/
contracts/
orchestration/
tools/
ingestion/
integrations/jira/
evaluation/
ui/
plan/
```

This is a proposed layout; do not create empty implementation modules until their work starts.

## Integration order

1. Agree on contracts and commit representative fixtures.
2. Each agent runs independently with stub tools and produces validated outputs.
3. Coordinator executes one complete fixture workflow.
4. Replace stubs with Pinecone, Neo4j, and snapshot source access.
5. Integrate verification retries and debt invalidation.
6. Add Jira input/output and deduplication.
7. Add trace UI and hosted deployment.
8. Evaluate the fixed eight-ticket set and rehearse demo/replay.

## Failure behavior

| Condition | Required response |
|---|---|
| Pinecone unavailable | Use available exact/graph evidence only if sufficient; mark retrieval coverage partial |
| Neo4j unavailable | Do not claim graph-confirmed cross-repository paths; report limitations |
| Snapshot mismatch | Reject mixed evidence; request refresh or fail the assessment clearly |
| No related debt | Continue with an empty recommendation list |
| Tool budget exhausted | Return supported partial findings and unvisited scope |
| Invalid agent output | Bounded repair attempt, then explicit failure/partial status |
| Jira posting fails | Persist and retry delivery; do not rerun analysis |
| Duplicate trigger | Reuse/deduplicate by ticket version and snapshot |

## Course demonstration checklist

- Three distinct agents execute with inspectable structured outputs.
- Pinecone retrieval supplies documentation/debt evidence.
- Neo4j traversal establishes a real cross-repository dependency path.
- An agent chooses a follow-up tool call based on a discovery.
- Verification rejects or qualifies an unsupported finding.
- A debt recommendation explains effort and shared testing.
- The final report includes actionable ambiguity questions when needed.
- A Jira event drives the flow without intermediate human approval.
- Trace and result can be replayed if external connectivity fails.
