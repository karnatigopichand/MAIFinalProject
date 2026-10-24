# commerce-inventory: persistence and state transitions

Reviewed against [reserve](../src/commerce_inventory/service.py), [HTTP handler and worker](../src/commerce_inventory/app.py), [transport/storage](../src/commerce_inventory/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Physical schema

Database: `data/inventory.sqlite`. Runtime uses this single physical table:

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

### `stock`

Key example: `book`. Payload:

```json
{
  "quantity": 5
}
```

### `reservations`

Key example: `demo-1`. Payload:

```json
{
  "order_id": "demo-1",
  "status": "reserved",
  "items": {
    "book": 1
  }
}
```

## State changes and failure boundaries

1. Return an existing reservation for the same `order_id` without comparing the new request body.
2. Require strictly positive integer quantities (booleans rejected); aggregate repeated SKU lines.
3. Treat missing stock as zero and check every requested SKU before any decrement.
4. Decrement each SKU and store the reservation.

Writes commit separately: a storage failure during updates can leave partial changes. Stock is not automatically released when payment later fails. `POST /stock` sets the absolute quantity (including zero), so repeated seeding can overwrite available stock irrespective of existing reservations. There is no list endpoint or HTTP reservation lookup endpoint.

SQLite writes and external HTTP/MQ actions are not atomic. No service-level transaction wraps multi-record writes or provider calls. The HTTP server executes sequentially per process, but separate API/worker processes can still contend on SQLite. There is no reservation concurrency control or durable background publication dispatcher.

GET returns only `stock` records; other logical kinds are internal. Unknown records produce JSON 404. See [API contracts](api-contracts.md) for exact public response shapes and error behavior.
