# commerce-orders: persistence and state transitions

Reviewed against [create_order](../src/commerce_orders/service.py), [HTTP handler and worker](../src/commerce_orders/app.py), [transport/storage](../src/commerce_orders/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Physical schema

Database: `data/orders.sqlite`. Runtime uses this single physical table:

```sql
CREATE TABLE IF NOT EXISTS records (
  kind TEXT,
  key TEXT,
  payload TEXT,
  PRIMARY KEY(kind, key)
);
```

Logical record kinds below are not separate SQL tables. Keys are stringified on access; payload is JSON. `Database.put` performs INSERT OR REPLACE and commits each write. There are no foreign keys, migration files, or automatic schema versioning. Tests generally use an in-memory database; the runnable API uses its configured file.

## Stored records

### `orders`

Key example: `demo-1`. Payload:

```json
{
  "order_id": "demo-1",
  "status": "confirmed",
  "delivery_address": "10 Main St"
}
```

### `published_events`

Key example: `order.confirmed.v1:order:demo-1`. Payload:

```json
{
  "event_id": "order:demo-1",
  "status": "sent"
}
```

## State changes and failure boundaries

1. Read `orders` by `order_id`. On a retry, attempt any pending publication, then return the stored result without rechecking the new request body.
2. Require nonempty items and a strict positive Python integer `total_cents` (booleans rejected).
3. POST reservation to inventory. If rejected, payment is not attempted.
4. POST authorization to payments. If rejected, stock is not released automatically.
5. Store `{order_id,status:"confirmed",delivery_address}`.
6. Publish `order.confirmed.v1` to shipping and notifications queues and record publication completion.

The order result can exist even when POST returned 503 due to publication failure. Retry the same ID to retry publication. A partially successful fan-out can duplicate a delivery. Downstream HTTP response payloads for reservation/payment are not inspected; success is determined by HTTP success and parseable JSON. The caller supplies the total; there is no pricing engine.

SQLite writes and external HTTP/MQ actions are not atomic. No service-level transaction wraps multi-record writes or provider calls. The HTTP server executes sequentially per process, but separate API/worker processes can still contend on SQLite. There is no reservation concurrency control or durable background publication dispatcher.

GET returns only `orders` records; other logical kinds are internal. Unknown records produce JSON 404. See [API contracts](api-contracts.md) for exact public response shapes and error behavior.
