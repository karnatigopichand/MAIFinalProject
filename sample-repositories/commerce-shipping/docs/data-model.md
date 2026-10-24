# commerce-shipping: persistence and state transitions

Reviewed against [consume](../src/commerce_shipping/service.py), [HTTP handler and worker](../src/commerce_shipping/app.py), [transport/storage](../src/commerce_shipping/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Physical schema

Database: `data/shipping.sqlite`. Runtime uses this single physical table:

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

### `shipments`

Key example: `demo-1`. Payload:

```json
{
  "order_id": "demo-1",
  "tracking_number": "TRACK-1"
}
```

### `published_events`

Key example: `shipment.created.v1:shipment:demo-1`. Payload:

```json
{
  "event_id": "shipment:demo-1",
  "status": "sent"
}
```

## State changes and failure boundaries

1. Require the consumed logical topic `order.confirmed.v1`.
2. Read shipment by order_id; a redelivery retries pending publication then returns stored tracking.
3. Map event order_id to carrier reference and delivery_address to carrier address.
4. Persist carrier tracking_number, then publish `shipment.created.v1`.

There is no business POST endpoint; messages drive creation. A carrier success followed by a storage failure can create another shipment on redelivery. Receipt timeout after storage leaves a shipment readable but publication incomplete. Carrier output is not schema-validated.

SQLite writes and external HTTP/MQ actions are not atomic. No service-level transaction wraps multi-record writes or provider calls. The HTTP server executes sequentially per process, but separate API/worker processes can still contend on SQLite. There is no reservation concurrency control or durable background publication dispatcher.

GET returns only `shipments` records; other logical kinds are internal. Unknown records produce JSON 404. See [API contracts](api-contracts.md) for exact public response shapes and error behavior.
