# Technical Debt Agent plan

## Purpose

Find small repository-local technical enhancements that overlap with the requirement's implementation and testing. Recommend opportunities to avoid repeated testing, without automatically expanding ticket scope.

This agent searches `TECH_DEBT.md` and generated docs, not Jira backlog tickets. It proposes work; it does not implement it or mark debt resolved.

## Technical-debt document template

Use one section per item with stable, machine-readable metadata and a clear narrative:

```markdown
## SHIP-TD-001: Consolidate carrier address mapping
- Status: open
- Components: src/carrier_mapping.py::build_address
- Implementation estimate hours: 1.0
- Testing estimate hours: 1.0
- Estimate basis: two duplicate mapping functions; existing adapter fixtures
- Relevant tests: tests/test_carrier_mapping.py
- Dependencies: none

### Problem
Two carrier payload paths duplicate the same address transformation.

### Proposed change
Extract one mapping helper while preserving existing payload behavior.

### Acceptance criteria
Both paths use the helper and existing payload tests continue to pass.
```

Repository identity and source commit are attached during indexing. Do not treat a generated estimate as a verified human estimate; retain its origin and uncertainty.

## Inputs and outputs

Input: normalized requirement, investigation findings, affected components, test candidates, evidence store, snapshot, and effort threshold.

Output: candidate assessments with `recommend`, `do_not_recommend`, or `needs_clarification`; debt ID; overlap evidence; estimate breakdown; shared and additional tests; incremental scope/risk; and justification.

## Tools

- Semantic retrieval restricted to technical-debt documents in the selected snapshot.
- General documentation retrieval to understand the candidate's implementation.
- Fetch the full original debt item and referenced code/tests.
- Neo4j traversal to establish component overlap.
- Exact symbol/test lookup when document references are incomplete.

Semantic similarity is candidate discovery, not eligibility proof.

## Eligibility policy

Planning default: maximum three person-hours per item, including implementation and testing; two hours or less preferred. This threshold remains configurable and requires team confirmation.

A recommendation requires:

1. The debt is open and current for the selected snapshot.
2. A documented estimate fits the threshold, with enough basis to be usable.
3. The requirement and debt touch the same implementation component or a demonstrated tightly coupled path.
4. At least one meaningful validation activity can be shared.
5. Extra scope and risk are small enough to explain clearly.

Unknown or unreliable estimates produce `needs_clarification`. Over-threshold or merely similar items produce `do_not_recommend`. Preserve all candidate dispositions in structured output for evaluation.

Do not automatically bundle many eligible items: expose cumulative effort and default to at most two recommendations per report. The team can configure a separate total effort cap. Never infer that six three-hour tasks constitute a small enhancement.

## Autonomous workflow

1. Form searches from affected fields, mappings, APIs, events, and repositories.
2. Retrieve candidate debt items and deduplicate by repository plus debt ID.
3. Read full items and inspect referenced components/tests.
4. Compare candidate change footprint against the investigation result.
5. Verify test overlap, listing what can be shared and what remains additional.
6. Apply effort/status/scope gates.
7. Rank eligible items by direct overlap, evidence quality, and small incremental scope.
8. Return recommendations and excluded/uncertain candidates to the final agent.

## Example

Requirement: forward delivery instructions to the carrier.

Candidate: a two-hour address-mapping consolidation in the exact adapter being changed. Recommend only if the source supports overlap and the same payload regression tests exercise both changes. Explain that instruction-specific tests may still be additional.

Counterexamples: a two-hour payment logging improvement is unrelated; a six-hour shipping adapter rewrite exceeds the threshold; a similar debt item with no estimate requires clarification.

Report wording: “Potential shared validation: carrier payload regression suite. Additional validation: delivery-instructions omission/default behavior. Estimated combined effort is uncertain.” Avoid guaranteed savings or precise hours saved without a baseline.

## Implementation tasks

1. Define debt metadata parser and validation rules with the ingestion owner.
2. Implement candidate retrieval with snapshot/document-type filtering.
3. Implement evidence-based overlap comparison and deterministic eligibility gates.
4. Add structured recommendations and reason codes for exclusions.
5. Include cumulative effort, estimate origin, and test overlap in output.
6. Integrate trace events and downstream verification feedback.

## Validation and definition of done

Fixtures cover direct overlap under the threshold, exact threshold, excessive effort, missing estimate, closed debt, semantic-only similarity, duplicate retrieval, and shared-code/no-shared-test cases. A source mismatch must prevent recommendation. An empty debt corpus returns no recommendations without failing the whole assessment.

Owner deliverables: agent module, debt template/parser contract, eligibility policy/configuration, fixtures, focused checks, and one positive/negative demo pair.
