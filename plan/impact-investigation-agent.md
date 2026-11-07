# Impact Investigation Agent plan

> **Implementation status:** The deterministic investigation stage is implemented in `impact_assessment/agents.py` and uses the evidence-store interface, exact identifier search, and dependency traversal. The optional MCP server exposes equivalent bounded retrieval tools, but the workflow currently calls the store directly. Jev/OpenAI classification is advisory intake classification; it does not replace evidence-backed impact analysis.

## Purpose

Understand the Jira requirement and establish which e-commerce components need changes or validation. This agent incorporates the former Requirements Agent; there is no separate requirements specialist.

## Inputs and outputs

Input: ticket ID/version, summary, description, acceptance criteria, selected repository snapshot, investigation budget, and optional targeted questions from verification.

Output: normalized requirement, field/business-rule list, ambiguities, repository findings, dependency paths, evidence references, test candidates, and investigation limitations. Every impact classification includes its reason and evidence IDs.

Classifications:

- `change_required`: evidence supports an implementation change.
- `validation_required`: a contract/dependency needs checking, without proof of a code change.
- `possible_impact`: plausible relationship not yet established.
- `no_impact_found`: no impact found in the inspected scope; not a claim of exhaustive absence.

## Tools

- `search_docs(query, snapshot_id, repositories?, document_types?, limit)` via Pinecone.
- `search_identifiers(query, snapshot_id, repositories?, limit)` for exact field/topic/symbol matches.
- `traverse_dependencies(start_ids, relationship_types, direction, max_hops, snapshot_id)` via Neo4j.
- `fetch_evidence(evidence_ids, snapshot_id)` for source excerpts and provenance.
- `get_contract(component_id, snapshot_id)` for API/event/data definitions.

Read-only investigation tools must enforce snapshot selection. A missing result is not proof that a dependency does not exist.

## Autonomous workflow

1. Parse the requested behavior, actors, inputs/outputs, fields, and acceptance criteria.
2. Record missing business decisions without inventing answers. Continue independent investigation where possible.
3. Search docs semantically for likely entry points; search exact names when supplied.
4. Read source evidence for promising matches.
5. Follow callers, HTTP endpoints, event publishers/consumers, field mappings, and table access.
6. Choose follow-up searches based on discovered fields, events, or unresolved graph links.
7. Assess each repository and build evidence-backed dependency paths.
8. Return findings and unresolved questions. On a verification retry, investigate only the requested gaps.

Initial bounds: configurable maximum graph depth and tool-call count; coordinator owns the overall deadline. Log truncation and unvisited branches explicitly.

## Example

Ticket: “Allow delivery instructions at checkout, forward them to the carrier, and display them in the shipping confirmation.”

Investigate the checkout request and order mapping; order schema and persistence; confirmed-order event; shipping consumer and carrier adapter; shipment event; notification template. Check whether the existing code already forwards the field before recommending edits. Inventory and payments should not be declared affected solely because orders invokes them.

Possible question: “Should delivery instructions appear only in the shipping confirmation, or also in the order confirmation?” The agent can still assess the unambiguous path.

## Implementation tasks

1. Implement shared Pydantic input/output models and one fixture result.
2. Create ticket-normalization prompt and structured-output validation.
3. Connect retrieval and traversal tools through the shared tool layer.
4. Implement evidence registration and dependency-path assembly.
5. Add bounded search loop and targeted reinvestigation handling.
6. Emit trace events and return partial results on recoverable tool failures.
7. Integrate with the coordinator and downstream debt agent.

## Validation and definition of done

- Delivery-instructions fixture identifies the relevant path and excludes unsupported payment/inventory changes.
- A field-name mismatch is resolved through mapping evidence rather than semantic similarity alone.
- An ambiguous ticket produces questions and qualified findings.
- A missing graph edge triggers source/identifier investigation or explicit uncertainty.
- Sources resolve to the selected commit; a different snapshot cannot leak into findings.
- Budget exhaustion returns usable partial output with limitations.

Owner deliverables: agent module, prompt/configuration, typed fixtures, focused checks for the above behaviors, and a sample trace. Do not generate a final Jira report or technical-debt eligibility decision in this agent.
