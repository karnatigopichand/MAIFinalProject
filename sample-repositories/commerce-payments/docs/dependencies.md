# commerce-payments: dependency contracts

Reviewed against [authorize](../src/commerce_payments/service.py), [HTTP handler and worker](../src/commerce_payments/app.py), [transport/storage](../src/commerce_payments/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Incoming callers and publishers

`commerce-orders` → `POST /authorizations`, forwarding total_cents as amount_cents.

## Outbound HTTP

### HTTP → `payment-provider-api`

`POST http://payment-provider-api:9000/charges` (development config), timeout 5 seconds. Implemented by `Service.authorize` using `HTTPClient.post`.

Request:

```json
{
  "amount": 2500,
  "currency": "USD",
  "token": "demo-token"
}
```

Expected success response:

```json
{
  "status": "authorized",
  "authorization_id": "AUTH-1"
}
```

Declined response: `{"status":"declined"}`; authorization_id is not read on decline. HTTP authentication is not sent. This is an expected external contract, not an included provider implementation.

All calls send JSON and a new X-Request-ID; no inbound headers or provider authentication are forwarded. HTTP 4xx maps to downstream failure, network/timeout errors to downstream unavailability. API and worker error presentation differ: API returns mapped JSON statuses, worker NACKs. Successful dependency JSON is not fully schema-validated.

## MQ dependencies

Publisher destinations:

```json
{}
```

Consumer bindings:

```json
{}
```

Full message bodies and delivery semantics: [events.md](events.md). Absence of queue bindings means no business MQ dependency for that direction.

## Internal storage and graph evidence

SQLite is owned by this service; there is no cross-repository SQL access. `contracts.json` is maintained metadata, while executable call sites and environment configuration establish actual targets. The same host name can be replaced for deployment without changing repository ownership. Link HTTP target names to repository/API nodes, event names to queue publishers/consumers, and the field mappings to their source symbols. Do not infer a dependency merely from a shared runtime helper or unused broker configuration.
