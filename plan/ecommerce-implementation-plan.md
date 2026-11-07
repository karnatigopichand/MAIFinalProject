# Codex implementation plan: six e-commerce repositories

## Goal and architecture alignment

Implement a lightweight application corpus for the three-agent final project, not a production commerce platform. The agents remain Impact Investigation, Technical Debt, and Risk and Report. The corpus provides concrete code, docs, dependency contracts, and multiple debt documents for Pinecone retrieval and Neo4j traversal.

Six repositories are retained from the overall plan: checkout, orders, inventory, payments, shipping, and notifications. Notifications completes the downstream event path even though the latest request explicitly named only the first five.

## Current deliverables

The initial implementation is in `sample-repositories/`. Each directory contains an independent Python package, unit tests, machine-readable contracts, implementation-reviewed docs, OpenAPI specifications, and four authored technical-debt documents. Workspace scripts call the running APIs, run tests, and validate reviewed documentation. Separate Git repositories and remotes have not been created.

The current iteration implements real HTTP JSON clients and HTTP servers, plus ActiveMQ Classic STOMP publishers and workers. Environment-specific JSON files define external API hosts, ports, endpoints, and queue bindings. Production service code has no stub fallback; tests inject isolated doubles. A workspace-level deterministic payment and carrier demo API is available in `scripts/mock_providers.py`, and `docker-compose.yml` provisions a local ActiveMQ Classic broker. SQLite uses one generic `records` table per service database with named logical record kinds; it does not implement the separate physical tables suggested in the initial plan. API servers are runnable now. SQLite/broker/provider persistence is demo-grade.

## Repository implementation breakdown

| Repository | Entry points | Features and data | Evidence for graph |
|---|---|---|---|
| Checkout | `Service.checkout` | Validate nonempty cart; map delivery/cart fields; sequential retry by checkout ID | POST orders call and field mappings |
| Orders | `Service.create_order` | Reserve stock; authorize; persist confirmation; publish once on successful sequential retry | Two HTTP calls; order event; delivery field |
| Inventory | `Service.seed_stock`, `Service.reserve` | Aggregate duplicate SKUs; validate quantities; check availability before updates; deduplicate reservation | Stock and reservation kinds; item-to-stock mapping |
| Payments | `Service.authorize` | Validate cents/currency; map provider payload; reject decline; persist safe result | Provider HTTP call and amount mapping |
| Shipping | `Service.consume` | Accept order confirmation; map address to carrier; persist shipment; emit tracking; deduplicate | Consumer, carrier call, shipment publisher |
| Notifications | `Service.consume` | Render two message types; persist outbox; deduplicate event IDs | Two consumers and template field mappings |

## Codex work sequence

For each service, use this repeatable assignment:

1. Read `overall-plan.md`, the service's contract, and upstream/downstream contracts.
2. Implement only its listed behavior, with injectable transport and storage adapters. Never import another service's implementation into business code.
3. Name remote repository targets and event topics explicitly in code and contracts.
4. Keep field transformations visible in mapping expressions; avoid hiding all dependencies in generic runtime logic.
5. Add success, validation/rejection, mapping, and retry/redelivery tests appropriate to that service.
6. Run service tests and integration checks before reviewing documentation.
7. Read implemented handlers, business methods, runtime adapters, and config; maintain detailed API/OpenAPI docs and verify them against source. Avoid replacing reviewed prose with generated summary templates.
8. Maintain authored debt files separately. Include component/test references and clearly labeled implementation/testing estimates.

Do not implement delivery instructions in the baseline: use that requirement to demonstrate discovery of the future propagation path. Do not index benchmark answer keys alongside repository evidence.

## Test plan and current verification

Run `python3 scripts/test_samples.py` from the workspace root. The suite covers service behavior, real loopback HTTP, persistent-message/receipt handling, queue fan-out, worker ACK/NACK, configuration, JSON logs, and cross-service HTTP flows. A separate opt-in test checks a live ActiveMQ broker.

Service checks cover cart rejection, mapping and retry; duplicate SKU aggregation, unavailable stock, invalid quantity; order confirmation and dependency failure; authorization mapping/decline/amount; shipping mapping/redelivery; and notification templates/deduplication.

Integration checks cover full checkout-to-shipment notification with repeated event delivery, insufficient stock stopping payment, and payment decline producing no confirmation. The decline test explicitly documents that reservation compensation is absent. No test claims concurrent or crash-safe idempotency.

For future changes, add tests for meaningful new behavior rather than duplicating every implementation statement. Keep deterministic provider responses in tests and isolated database connections; runtime providers are external APIs.

## Implementation-reviewed documentation

Documentation is written from the implemented HTTP handlers, service methods, transport adapters, and environment files. Each repository has a detailed API contract and OpenAPI 3.1 document describing configured servers, security, headers, request/response schemas and examples, status mapping, and retry behavior. Companion docs explain exact field mappings, physical/logical persistence, downstream API bodies, queue payloads, and operational limits.

The previous `generate_sample_docs.py` summary generator has been removed to prevent overwriting reviewed documentation. Run `python3 scripts/validate_sample_docs.py` after source/documentation review. It checks configured servers, routes, source hashes, local references, and links; it does not regenerate prose or imply full runtime schema validation.

Review source hashes are stored in each `docs/source-review.json`. Refresh them only after reviewing changed behavior and updating affected specifications. Once targets become independent repositories, also capture their immutable commits. Do not present configured hosts as verified deployments or document authentication/schema enforcement that is not implemented.

## Integration and deployment status

1. Agree on service contracts and review the small generated application with teammates.
2. Assign one target directory per teammate or pair; ownership is independent of agent ownership.
3. Extract each directory into its own Git repository when authorized; preserve package layout and add a local documentation-review/validation workflow.
4. Record repository URLs and immutable commits in the AI-system manifest.
5. The workspace now has Graphify extraction/reconciliation, Pinecone and Neo4j publishing adapters, snapshot-scoped hosted retrieval, and an MCP retrieval server. Configure and verify those external stores before selecting hosted mode.
6. Start each API and shipping/notifications workers using the service guide; verify actual provider and broker connectivity. Configure Jira and hosted delivery separately.
7. Validate Replit runtime/storage/network behavior; retain local replay as a fallback.

The application corpus is accompanied by the workspace AI workflow, demo UI, MCP tools, optional LangGraph orchestration, Pinecone/Neo4j adapters, Jev/OpenAI classification, Langfuse tracing, and deterministic/LLM-judge evaluation. These integrations are optional and require configured credentials/packages; the agents still use deterministic evidence and policy logic rather than generative model reasoning. Jira account setup, live broker/provider verification, and Replit deployment remain external integration work.

## Acceptance criteria

- All six packages run independently with standard-library adapters.
- The workspace flow produces order confirmation, shipment, and two outbox messages.
- HTTP/MQ boundaries and field mappings are discoverable in source and documents.
- Tests pass before documentation review.
- Each target has multiple debt documents with source/test references and labeled estimates.
- Reviewed docs accurately describe real network transport, configured queues, JSON logs, actual storage, provenance, and limitations.
- Tests require no external provider credentials. The local provider APIs and broker use synthetic demo behavior/credentials; replace them with secured external dependencies for deployment.
