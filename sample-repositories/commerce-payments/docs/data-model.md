# commerce-payments: persistence and state transitions

Reviewed against [authorize](../src/commerce_payments/service.py), [HTTP handler and worker](../src/commerce_payments/app.py), [transport/storage](../src/commerce_payments/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Physical schema

Database: `data/payments.sqlite`. Runtime uses this single physical table:

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

### `authorizations`

Key example: `demo-1`. Payload:

```json
{
  "order_id": "demo-1",
  "authorization_id": "AUTH-1",
  "status": "authorized"
}
```

## State changes and failure boundaries

1. Return stored authorization for an existing `order_id`, without comparing the token, amount, or currency in a retry.
2. Require `amount_cents` to be a strict positive integer and currency exactly `USD`.
3. Map amount to provider `amount`, retain currency, map payment_token to provider `token`.
4. Require provider response status `authorized`; otherwise raise business rejection.
5. Store order_id, authorization_id, and status. No token is persisted.

There is no capture, refund, cancellation, or provider idempotency key. A provider success followed by a local storage failure can lead to another authorization on retry. Provider responses are not schema-validated; missing fields can surface as 422.

SQLite writes and external HTTP/MQ actions are not atomic. No service-level transaction wraps multi-record writes or provider calls. The HTTP server executes sequentially per process, but separate API/worker processes can still contend on SQLite. There is no reservation concurrency control or durable background publication dispatcher.

GET returns only `authorizations` records; other logical kinds are internal. Unknown records produce JSON 404. See [API contracts](api-contracts.md) for exact public response shapes and error behavior.
