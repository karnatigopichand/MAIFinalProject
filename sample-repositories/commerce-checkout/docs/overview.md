# commerce-checkout: implementation overview

Reviewed against [checkout](../src/commerce_checkout/service.py), [HTTP handler and worker](../src/commerce_checkout/app.py), [transport/storage](../src/commerce_checkout/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Responsibility

Accepts a cart, forwards an order request, then stores the confirmed response. It does not price items or directly reserve stock.

## Execution flow

1. Look up `checkouts` by `checkout_id`; an existing result returns immediately, even if the new body differs.
2. Require a nonempty `cart.items`, then map to the orders API.
3. Forward `checkout_id → order_id`, `cart.items → items`, `delivery.address → delivery_address`, `total_cents`, `payment_token`, and currency (default USD only when omitted).
4. Call orders synchronously. Persist its response only after HTTP succeeds.

No price calculation, sum validation, address validation, currency normalization, or request-payload conflict check is implemented. The service trusts the orders response rather than validating its schema. If orders confirms but its event publish fails, checkout may return an error while the order is already stored upstream.

## Public interfaces

- [Complete HTTP specification](api-contracts.md) and [OpenAPI](openapi.json).
- [Messaging contracts](events.md), including queue names and consumer behavior.
- [Field lineage](field-mappings.md), [storage](data-model.md), [dependencies](dependencies.md), and [configuration/security](configuration.md).
- Multiple authored [technical-debt items](technical-debt/) describe known enhancements; estimates require team review.

## Source map

| Source | Responsibility |
|---|---|
| `src/commerce_checkout/service.py` | Business methods and dependency call sites |
| `src/commerce_checkout/app.py` | HTTP routing, error mapping, worker callbacks and process startup |
| `src/commerce_checkout/runtime.py` | JSON logs, SQLite records, urllib HTTP, STOMP connections and publication |
| `config/*.json` | Runtime hosts, ports, paths, queues and environment variable names |
| `contracts.json` | Maintained dependency metadata; must be checked against code |

## Verification boundary

Service/transport tests and loopback integration tests validate selected behaviors. They do not establish a running development deployment or live ActiveMQ availability. No AI agents, Pinecone indexing, or Neo4j upload is started by this service.
