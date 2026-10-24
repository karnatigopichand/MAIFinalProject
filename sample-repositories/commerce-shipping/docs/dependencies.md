# commerce-shipping: dependency contracts

Reviewed against [consume](../src/commerce_shipping/service.py), [HTTP handler and worker](../src/commerce_shipping/app.py), [transport/storage](../src/commerce_shipping/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Incoming callers and publishers

`commerce-orders` → `/queue/commerce.shipping.order-confirmed.v1` → `Service.consume`. HTTP has no business write route.

## Outbound HTTP

### HTTP → `carrier-provider-api`

`POST http://carrier-provider-api:9001/shipments` (development config), timeout 5 seconds. Implemented by `Service.consume` using `HTTPClient.post`.

Request:

```json
{
  "reference": "demo-1",
  "address": "10 Main St"
}
```

Expected success response:

```json
{
  "tracking_number": "TRACK-1"
}
```

No explicit carrier business-error schema is recognized; HTTP errors propagate and missing tracking_number becomes a consumer failure. This is an expected external contract, not an included provider implementation.

All calls send JSON and a new X-Request-ID; no inbound headers or provider authentication are forwarded. HTTP 4xx maps to downstream failure, network/timeout errors to downstream unavailability. API and worker error presentation differ: API returns mapped JSON statuses, worker NACKs. Successful dependency JSON is not fully schema-validated.

## MQ dependencies

Publisher destinations:

```json
{
  "shipment.created.v1": [
    "/queue/commerce.notifications.shipment-created.v1"
  ]
}
```

Consumer bindings:

```json
{
  "/queue/commerce.shipping.order-confirmed.v1": "order.confirmed.v1"
}
```

Full message bodies and delivery semantics: [events.md](events.md). Absence of queue bindings means no business MQ dependency for that direction.

## Internal storage and graph evidence

SQLite is owned by this service; there is no cross-repository SQL access. `contracts.json` is maintained metadata, while executable call sites and environment configuration establish actual targets. The same host name can be replaced for deployment without changing repository ownership. Link HTTP target names to repository/API nodes, event names to queue publishers/consumers, and the field mappings to their source symbols. Do not infer a dependency merely from a shared runtime helper or unused broker configuration.
