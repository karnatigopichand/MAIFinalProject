# commerce-shipping: implementation overview

Reviewed against [consume](../src/commerce_shipping/service.py), [HTTP handler and worker](../src/commerce_shipping/app.py), [transport/storage](../src/commerce_shipping/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Responsibility

Consumes confirmed orders, calls an external carrier, stores tracking information, and publishes shipment creation. HTTP is read-only.

## Execution flow

1. Require the consumed logical topic `order.confirmed.v1`.
2. Read shipment by order_id; a redelivery retries pending publication then returns stored tracking.
3. Map event order_id to carrier reference and delivery_address to carrier address.
4. Persist carrier tracking_number, then publish `shipment.created.v1`.

There is no business POST endpoint; messages drive creation. A carrier success followed by a storage failure can create another shipment on redelivery. Receipt timeout after storage leaves a shipment readable but publication incomplete. Carrier output is not schema-validated.

## Public interfaces

- [Complete HTTP specification](api-contracts.md) and [OpenAPI](openapi.json).
- [Messaging contracts](events.md), including queue names and consumer behavior.
- [Field lineage](field-mappings.md), [storage](data-model.md), [dependencies](dependencies.md), and [configuration/security](configuration.md).
- Multiple authored [technical-debt items](technical-debt/) describe known enhancements; estimates require team review.

## Source map

| Source | Responsibility |
|---|---|
| `src/commerce_shipping/service.py` | Business methods and dependency call sites |
| `src/commerce_shipping/app.py` | HTTP routing, error mapping, worker callbacks and process startup |
| `src/commerce_shipping/runtime.py` | JSON logs, SQLite records, urllib HTTP, STOMP connections and publication |
| `config/*.json` | Runtime hosts, ports, paths, queues and environment variable names |
| `contracts.json` | Maintained dependency metadata; must be checked against code |

## Verification boundary

Service/transport tests and loopback integration tests validate selected behaviors. They do not establish a running development deployment or live ActiveMQ availability. No AI agents, Pinecone indexing, or Neo4j upload is started by this service.
