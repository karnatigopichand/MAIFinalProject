# commerce-checkout: persistence and state transitions

Reviewed against [checkout](../src/commerce_checkout/service.py), [HTTP handler and worker](../src/commerce_checkout/app.py), [transport/storage](../src/commerce_checkout/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Physical schema

Database: `data/checkout.sqlite`. Runtime uses this single physical table:

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

### `checkouts`

Key example: `demo-1`. Payload:

```json
{
  "order_id": "demo-1",
  "status": "confirmed",
  "delivery_address": "10 Main St"
}
```

## State changes and failure boundaries

1. Look up `checkouts` by `checkout_id`; an existing result returns immediately, even if the new body differs.
2. Require a nonempty `cart.items`, then map to the orders API.
3. Forward `checkout_id → order_id`, `cart.items → items`, `delivery.address → delivery_address`, `total_cents`, `payment_token`, and currency (default USD only when omitted).
4. Call orders synchronously. Persist its response only after HTTP succeeds.

No price calculation, sum validation, address validation, currency normalization, or request-payload conflict check is implemented. The service trusts the orders response rather than validating its schema. If orders confirms but its event publish fails, checkout may return an error while the order is already stored upstream.

SQLite writes and external HTTP/MQ actions are not atomic. No service-level transaction wraps multi-record writes or provider calls. The HTTP server executes sequentially per process, but separate API/worker processes can still contend on SQLite. There is no reservation concurrency control or durable background publication dispatcher.

GET returns only `checkouts` records; other logical kinds are internal. Unknown records produce JSON 404. See [API contracts](api-contracts.md) for exact public response shapes and error behavior.
