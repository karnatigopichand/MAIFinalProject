# commerce-notifications: implementation overview

Reviewed against [consume](../src/commerce_notifications/service.py), [HTTP handler and worker](../src/commerce_notifications/app.py), [transport/storage](../src/commerce_notifications/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Responsibility

Consumes order/shipment events and writes rendered text to a local outbox. It does not deliver email or SMS. HTTP is read-only.

## Execution flow

1. Accept only `order.confirmed.v1` and `shipment.created.v1`.
2. Deduplicate using event_id, irrespective of topic or body changes.
3. Render `Order {order_id} confirmed` or `Order {order_id} shipped: {tracking_number}`.
4. Store event_id, topic, and body under the outbox kind.

There is no business POST endpoint, recipient directory, email delivery, or SMS delivery. Duplicate event IDs across unrelated messages will suppress the later message. The order and shipment queues can be processed in either order; notifications do not establish global event ordering.

## Public interfaces

- [Complete HTTP specification](api-contracts.md) and [OpenAPI](openapi.json).
- [Messaging contracts](events.md), including queue names and consumer behavior.
- [Field lineage](field-mappings.md), [storage](data-model.md), [dependencies](dependencies.md), and [configuration/security](configuration.md).
- Multiple authored [technical-debt items](technical-debt/) describe known enhancements; estimates require team review.

## Source map

| Source | Responsibility |
|---|---|
| `src/commerce_notifications/service.py` | Business methods and dependency call sites |
| `src/commerce_notifications/app.py` | HTTP routing, error mapping, worker callbacks and process startup |
| `src/commerce_notifications/runtime.py` | JSON logs, SQLite records, urllib HTTP, STOMP connections and publication |
| `config/*.json` | Runtime hosts, ports, paths, queues and environment variable names |
| `contracts.json` | Maintained dependency metadata; must be checked against code |

## Verification boundary

Service/transport tests and loopback integration tests validate selected behaviors. They do not establish a running development deployment or live ActiveMQ availability. No AI agents, Pinecone indexing, or Neo4j upload is started by this service.
