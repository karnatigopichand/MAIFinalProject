# commerce-orders: implementation overview

Reviewed against [create_order](../src/commerce_orders/service.py), [HTTP handler and worker](../src/commerce_orders/app.py), [transport/storage](../src/commerce_orders/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Responsibility

Reserves inventory before authorizing payment, persists confirmation, then publishes to both order queues. A failure may leave completed earlier side effects.

## Execution flow

1. Read `orders` by `order_id`. On a retry, attempt any pending publication, then return the stored result without rechecking the new request body.
2. Require nonempty items and a strict positive Python integer `total_cents` (booleans rejected).
3. POST reservation to inventory. If rejected, payment is not attempted.
4. POST authorization to payments. If rejected, stock is not released automatically.
5. Store `{order_id,status:"confirmed",delivery_address}`.
6. Publish `order.confirmed.v1` to shipping and notifications queues and record publication completion.

The order result can exist even when POST returned 503 due to publication failure. Retry the same ID to retry publication. A partially successful fan-out can duplicate a delivery. Downstream HTTP response payloads for reservation/payment are not inspected; success is determined by HTTP success and parseable JSON. The caller supplies the total; there is no pricing engine.

## Public interfaces

- [Complete HTTP specification](api-contracts.md) and [OpenAPI](openapi.json).
- [Messaging contracts](events.md), including queue names and consumer behavior.
- [Field lineage](field-mappings.md), [storage](data-model.md), [dependencies](dependencies.md), and [configuration/security](configuration.md).
- Multiple authored [technical-debt items](technical-debt/) describe known enhancements; estimates require team review.

## Source map

| Source | Responsibility |
|---|---|
| `src/commerce_orders/service.py` | Business methods and dependency call sites |
| `src/commerce_orders/app.py` | HTTP routing, error mapping, worker callbacks and process startup |
| `src/commerce_orders/runtime.py` | JSON logs, SQLite records, urllib HTTP, STOMP connections and publication |
| `config/*.json` | Runtime hosts, ports, paths, queues and environment variable names |
| `contracts.json` | Maintained dependency metadata; must be checked against code |

## Verification boundary

Service/transport tests and loopback integration tests validate selected behaviors. They do not establish a running development deployment or live ActiveMQ availability. No AI agents, Pinecone indexing, or Neo4j upload is started by this service.
