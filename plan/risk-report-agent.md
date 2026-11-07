# Risk and Report Agent plan

> **Implementation status:** Evidence verification, bounded reinvestigation requests, structured risks/questions, report rendering, and local trace persistence are implemented across `impact_assessment/agents.py` and `impact_assessment/workflow.py`. Langfuse export is optional. The LLM judge is a separate opt-in evaluator; its candidate rubric is not calibrated or a release gate.

## Purpose

Verify the other agents' findings, explain technical and business risks, and produce an actionable assessment. Evidence verification is part of this agent rather than a separate fourth specialist.

## Inputs and outputs

Input: ticket and snapshot context, normalized requirement, investigation findings, dependency paths, debt assessments, evidence IDs, and remaining retry budget.

Output: either targeted verification requests or a final structured assessment with rendered Markdown. Final statuses are `complete`, `needs_clarification`, `partial`, or `failed`. A successful tool sequence does not automatically mean the assessment is complete.

The agent prepares the Jira response. A delivery component persists and posts it, allowing posting retries without rerunning analysis.

## Tools

- Fetch original source evidence and document sections.
- Query graph relationships and inspect supporting references.
- Fetch original debt metadata and contracts.
- Validate source paths, symbols, snapshot identity, and evidence references.

Use programmatic validation for existence and schema checks, then model reasoning for whether the evidence actually supports the claim. Do not rely exclusively on another prose summary.

## Verification workflow

1. Validate required artifact fields, evidence references, and snapshot alignment.
2. Independently inspect support for each confirmed impact and proposed debt recommendation.
3. Check that dependency paths contain supported links, particularly publisher-to-consumer and field mappings.
4. Separate required code changes from validation-only impacts and possible impacts.
5. Reject or qualify claims supported only by semantic similarity.
6. For resolvable evidence gaps, return targeted requests to the coordinator. Default maximum is two verification-driven reinvestigation rounds per run.
7. On exhausted budget or unavailable tools, finish with qualified findings and explicit limitations.
8. Assess risks, recommend implementation/testing steps, and render the final report.

## Risk assessment

For each risk, record failure mode, affected behavior, business consequence, evidence, severity, uncertainty, and suggested validation. Keep severity separate from confidence: a severe hypothetical failure can still have weak evidence.

Consider API/event compatibility, persistence and defaults, field omission/transformation, retries and duplicate events, error handling, and consumer behavior. Discuss only risks relevant to evidence found; avoid generic risk lists.

Example: if an event field becomes required while existing producers omit it, a consumer may reject messages, delaying shipment creation. Verify schema enforcement and producer behavior before calling this a confirmed risk.

## Report structure

1. **Assessment summary:** ticket/version, repository snapshot, status, requested behavior.
2. **Repository impact table:** repository, classification, components/fields, reason, evidence.
3. **Dependency paths:** HTTP/MQ relationships and field lineage, with references.
4. **Business and technical risks:** severity, rationale, uncertainty, tests.
5. **Recommended changes and validation:** sequence and suggested tests, not a claim that code is already changed.
6. **Optional technical debt:** eligible IDs, effort including testing, shared tests, additional work, cumulative effort, caveats.
7. **Questions and limitations:** missing requirements, unproven relationships, stale/missing evidence, and investigation limits.

Include readable source references such as `commerce-shipping@<commit>:src/carrier_mapping.py`, symbol/line metadata, and evidence IDs. If no remote URL exists, do not invent clickable GitHub links.

## Questions to the product owner

Questions should resolve specific decisions, explain why they matter, and avoid repeating information already in the ticket. Example: “Should omitted delivery instructions remain absent or be sent as an empty string? The carrier adapter currently omits optional fields.”

Questions do not suspend the run indefinitely. Post the qualified report automatically; a later ticket update can trigger reassessment.

## Trace requirements

Expose tool calls, concise retrieval queries, evidence IDs/excerpts, graph paths, verification decisions, routing, elapsed time, tool errors, and usage when available. Provide short action rationales; do not expose private chain-of-thought. Remove secrets and minimize sensitive ticket data in exported traces.

## Implementation tasks

1. Implement deterministic artifact/source-reference checks.
2. Implement claim-support review and targeted verification-request schema.
3. Define severity guidance and structured risk output.
4. Build Markdown report renderer from validated structured data.
5. Add uncertainty/status rules and technical-debt presentation.
6. Integrate report persistence/delivery with the coordinator owner.

## Validation and definition of done

- Unsupported claims are removed, qualified, or sent for reinvestigation.
- Missing consumers and broken path links are visible.
- Over-threshold/unknown debt is not upgraded to a recommendation.
- Risk severity does not masquerade as certainty or an uncalibrated probability.
- Failed retrieval produces a partial assessment, not fabricated evidence.
- Report includes business impact, field details, shared tests, and actionable questions.
- Reposting uses the same persisted result and does not regenerate a different assessment.

Owner deliverables: verification module, risk guidance, structured report schema, Markdown renderer, adversarial fixtures, and sample complete/partial reports.
