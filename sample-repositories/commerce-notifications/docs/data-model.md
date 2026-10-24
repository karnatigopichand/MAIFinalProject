# commerce-notifications: persistence and state transitions

Reviewed against [consume](../src/commerce_notifications/service.py), [HTTP handler and worker](../src/commerce_notifications/app.py), [transport/storage](../src/commerce_notifications/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Physical schema

Database: `data/notifications.sqlite`. Runtime uses this single physical table:

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

### `outbox`

Key example: `shipment:demo-1`. Payload:

```json
{
  "event_id": "shipment:demo-1",
  "topic": "shipment.created.v1",
  "body": "Order demo-1 shipped: TRACK-1"
}
```

## State changes and failure boundaries

1. Accept only `order.confirmed.v1` and `shipment.created.v1`.
2. Deduplicate using event_id, irrespective of topic or body changes.
3. Render `Order {order_id} confirmed` or `Order {order_id} shipped: {tracking_number}`.
4. Store event_id, topic, and body under the outbox kind.

There is no business POST endpoint, recipient directory, email delivery, or SMS delivery. Duplicate event IDs across unrelated messages will suppress the later message. The order and shipment queues can be processed in either order; notifications do not establish global event ordering.

SQLite writes and external HTTP/MQ actions are not atomic. No service-level transaction wraps multi-record writes or provider calls. The HTTP server executes sequentially per process, but separate API/worker processes can still contend on SQLite. There is no reservation concurrency control or durable background publication dispatcher.

GET returns only `outbox` records; other logical kinds are internal. Unknown records produce JSON 404. See [API contracts](api-contracts.md) for exact public response shapes and error behavior.
