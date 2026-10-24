# commerce-payments: implementation overview

Reviewed against [authorize](../src/commerce_payments/service.py), [HTTP handler and worker](../src/commerce_payments/app.py), [transport/storage](../src/commerce_payments/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Responsibility

Checks positive integer cents and USD, calls an external provider, and stores successful authorization metadata without the token.

## Execution flow

1. Return stored authorization for an existing `order_id`, without comparing the token, amount, or currency in a retry.
2. Require `amount_cents` to be a strict positive integer and currency exactly `USD`.
3. Map amount to provider `amount`, retain currency, map payment_token to provider `token`.
4. Require provider response status `authorized`; otherwise raise business rejection.
5. Store order_id, authorization_id, and status. No token is persisted.

There is no capture, refund, cancellation, or provider idempotency key. A provider success followed by a local storage failure can lead to another authorization on retry. Provider responses are not schema-validated; missing fields can surface as 422.

## Public interfaces

- [Complete HTTP specification](api-contracts.md) and [OpenAPI](openapi.json).
- [Messaging contracts](events.md), including queue names and consumer behavior.
- [Field lineage](field-mappings.md), [storage](data-model.md), [dependencies](dependencies.md), and [configuration/security](configuration.md).
- Multiple authored [technical-debt items](technical-debt/) describe known enhancements; estimates require team review.

## Source map

| Source | Responsibility |
|---|---|
| `src/commerce_payments/service.py` | Business methods and dependency call sites |
| `src/commerce_payments/app.py` | HTTP routing, error mapping, worker callbacks and process startup |
| `src/commerce_payments/runtime.py` | JSON logs, SQLite records, urllib HTTP, STOMP connections and publication |
| `config/*.json` | Runtime hosts, ports, paths, queues and environment variable names |
| `contracts.json` | Maintained dependency metadata; must be checked against code |

## Verification boundary

Service/transport tests and loopback integration tests validate selected behaviors. They do not establish a running development deployment or live ActiveMQ availability. No AI agents, Pinecone indexing, or Neo4j upload is started by this service.
