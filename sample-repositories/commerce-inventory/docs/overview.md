# commerce-inventory: implementation overview

Reviewed against [reserve](../src/commerce_inventory/service.py), [HTTP handler and worker](../src/commerce_inventory/app.py), [transport/storage](../src/commerce_inventory/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Responsibility

Seeds absolute stock levels, aggregates duplicate SKU lines, checks all availability before decrementing, and stores a reservation.

## Execution flow

1. Return an existing reservation for the same `order_id` without comparing the new request body.
2. Require strictly positive integer quantities (booleans rejected); aggregate repeated SKU lines.
3. Treat missing stock as zero and check every requested SKU before any decrement.
4. Decrement each SKU and store the reservation.

Writes commit separately: a storage failure during updates can leave partial changes. Stock is not automatically released when payment later fails. `POST /stock` sets the absolute quantity (including zero), so repeated seeding can overwrite available stock irrespective of existing reservations. There is no list endpoint or HTTP reservation lookup endpoint.

## Public interfaces

- [Complete HTTP specification](api-contracts.md) and [OpenAPI](openapi.json).
- [Messaging contracts](events.md), including queue names and consumer behavior.
- [Field lineage](field-mappings.md), [storage](data-model.md), [dependencies](dependencies.md), and [configuration/security](configuration.md).
- Multiple authored [technical-debt items](technical-debt/) describe known enhancements; estimates require team review.

## Source map

| Source | Responsibility |
|---|---|
| `src/commerce_inventory/service.py` | Business methods and dependency call sites |
| `src/commerce_inventory/app.py` | HTTP routing, error mapping, worker callbacks and process startup |
| `src/commerce_inventory/runtime.py` | JSON logs, SQLite records, urllib HTTP, STOMP connections and publication |
| `config/*.json` | Runtime hosts, ports, paths, queues and environment variable names |
| `contracts.json` | Maintained dependency metadata; must be checked against code |

## Verification boundary

Service/transport tests and loopback integration tests validate selected behaviors. They do not establish a running development deployment or live ActiveMQ availability. No AI agents, Pinecone indexing, or Neo4j upload is started by this service.
