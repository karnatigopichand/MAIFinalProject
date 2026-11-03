# Impact Investigation Agent (local prototype)

This is a deterministic, read-only prototype of the planned Impact Investigation Agent. It searches the checked-in `sample-repositories/` corpus, verifies candidate relationships from service contracts, and returns structured findings, evidence references, dependency paths, questions, and limitations. It does not modify the sample applications or call external services.

## Run

From the repository root:

```bash
python3 -m agents.impact --summary "Pass delivery instructions from checkout to shipping" --description "Include delivery instructions in the carrier shipment request."
python3 -m agents.impact --ticket-json path/to/ticket.json --output json
python3 -m unittest tests.test_impact_agent -v
```

Ticket JSON accepts `ticket_id` (or `key`), `version` (or `updated`), `summary`, `description`, and `acceptance_criteria` (string or list). The result carries a deterministic local corpus snapshot hash and evidence paths/line ranges. Since evidence IDs include that snapshot, re-running after corpus changes produces a new snapshot and new IDs.

## Extension points

`ImpactTools` in `agents/impact/tools.py` defines the read-only adapter boundary. `LocalCorpusTools` currently implements lexical document/identifier search, contract lookup, evidence fetching, and bounded traversal of explicit `CALLS`, `PUBLISHES`, `CONSUMES`, and `MAPS_TO` relationships. Jira ticket ingestion, Pinecone semantic retrieval, and Neo4j graph traversal can later implement adapters around the same contract; the investigator does not import those providers.

The current prototype is intentionally conservative: direct source matches are classified `change_required` for investigation (not as a guarantee a code edit is necessary); direct contract-only matches are `validation_required`; documentation-only and graph-expanded impacts are `possible_impact`. An absent result does not establish no impact. Related Jira issue keys in text are surfaced but never looked up. The adapter has no network access or credentials.

## Limitations

- Lexical matching is a baseline, not semantic retrieval or an LLM-driven investigation loop.
- The current dependency graph is synthesized from each service's `contracts.json`; it may omit or lag actual source behavior.
- There is no Jira integration, Pinecone index, Neo4j database, persistence, webhook, or report posting.
- The code has no new third-party dependencies and uses the repository's Python/unittest style.
