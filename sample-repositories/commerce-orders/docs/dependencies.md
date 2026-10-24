# commerce-orders: dependency contracts

Reviewed against [create_order](../src/commerce_orders/service.py), [HTTP handler and worker](../src/commerce_orders/app.py), [transport/storage](../src/commerce_orders/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Incoming callers and publishers

`commerce-checkout` → `POST /orders`, forwarding checkout_id as order_id.

## Outbound HTTP

### HTTP → `commerce-inventory`

`POST http://commerce-inventory:8002/reservations` (development config), timeout 5 seconds. Implemented by `Service.create_order` using `HTTPClient.post`.

Request:

```json
{
  "order_id": "demo-1",
  "items": [
    {
      "sku": "book",
      "quantity": 1
    }
  ]
}
```

Expected success response:

```json
{
  "order_id": "demo-1",
  "status": "reserved",
  "items": {
    "book": 1
  }
}
```

### HTTP → `commerce-payments`

`POST http://commerce-payments:8003/authorizations` (development config), timeout 5 seconds. Implemented by `Service.create_order` using `HTTPClient.post`.

Request:

```json
{
  "order_id": "demo-1",
  "amount_cents": 2500,
  "currency": "USD",
  "payment_token": "demo-token"
}
```

Expected success response:

```json
{
  "order_id": "demo-1",
  "authorization_id": "AUTH-1",
  "status": "authorized"
}
```

All calls send JSON and a new X-Request-ID; no inbound headers or provider authentication are forwarded. HTTP 4xx maps to downstream failure, network/timeout errors to downstream unavailability. API and worker error presentation differ: API returns mapped JSON statuses, worker NACKs. Successful dependency JSON is not fully schema-validated.

## MQ dependencies

Publisher destinations:

```json
{
  "order.confirmed.v1": [
    "/queue/commerce.shipping.order-confirmed.v1",
    "/queue/commerce.notifications.order-confirmed.v1"
  ]
}
```

Consumer bindings:

```json
{}
```

Full message bodies and delivery semantics: [events.md](events.md). Absence of queue bindings means no business MQ dependency for that direction.

## Internal storage and graph evidence

SQLite is owned by this service; there is no cross-repository SQL access. `contracts.json` is maintained metadata, while executable call sites and environment configuration establish actual targets. The same host name can be replaced for deployment without changing repository ownership. Link HTTP target names to repository/API nodes, event names to queue publishers/consumers, and the field mappings to their source symbols. Do not infer a dependency merely from a shared runtime helper or unused broker configuration.
