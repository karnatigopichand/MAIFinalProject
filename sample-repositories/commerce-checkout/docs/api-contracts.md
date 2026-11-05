# commerce-checkout: HTTP API specification

Reviewed against [checkout](../src/commerce_checkout/service.py), [HTTP handler and worker](../src/commerce_checkout/app.py), [transport/storage](../src/commerce_checkout/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Hosts and ports

| Environment | Client base URL | Listener binding | Status |
|---|---|---|---|
| Local | `http://127.0.0.1:8000` | `127.0.0.1:8000` | Configured; available only when the process is started |
| Development | `http://commerce-checkout:8000` | `0.0.0.0:8000` | Configured dummy DNS name; deployment/DNS not provisioned |

`0.0.0.0` is a bind address, not a client hostname. No public URL, TLS termination, or deployed environment is established by this repository. Query parameters are ignored; paths are case-sensitive and trailing slashes are not normalized. Use simple identifiers such as `demo-1`, `book`, and `shipment:demo-1`; the handler does not URL-decode encoded path identifiers.

## Security contract

The HTTP API accepts a shared bearer token from `COMMERCE_API_TOKEN`. Set the variable to require `Authorization: Bearer <token>` on every application route; `/health` stays unauthenticated for liveness. Non-local environments and non-loopback listeners refuse startup when the token is missing. Local loopback mode may run without a token. This is authentication only: there are no per-service identities, authorization scopes, rate limits, or built-in HTTPS; terminate TLS at a trusted proxy. CORS/OPTIONS support is absent. Payment tokens are business payload fields, not API authentication credentials.

ActiveMQ uses STOMP login/passcode read from `ACTIVEMQ_USERNAME` and `ACTIVEMQ_PASSWORD`; missing variables become empty strings, and broker policy decides whether login succeeds. Config defaults to `tls: false`; when enabled, `ca_certs` supplies broker CA verification. There is no implemented client-certificate/mTLS configuration. Do not confuse broker credentials with HTTP security.

## Headers and media types

| Header | Request behavior | Response behavior |
|---|---|---|
| `Content-Type` | Send `application/json` for POST. The handler parses JSON regardless of this header and does not return 415 for another value. | Application GET/POST responses use `application/json`. |
| `Content-Length` | POST requires declared length from 1 through 1,048,576 bytes. Most HTTP clients calculate it. Chunked bodies are not supported. GET does not inspect a body. | Set to the encoded JSON byte length. |
| `Accept` | Optional and ignored; no content negotiation. | No negotiated representation. |
| `Authorization` | Optional in local loopback mode; when `COMMERCE_API_TOKEN` is set, application routes require a constant-time checked bearer token. | No token issued. `/health` remains public. |
| `X-Request-ID` | Accepted as an arbitrary header but not read, propagated, or echoed. | Not returned. |
| Other headers | No application-specific processing. | Python HTTP server also adds `Server` and `Date`; no CORS headers. |

Each outbound HTTP call sends `Content-Type: application/json` and a newly generated `X-Request-ID`. When configured, service calls forward `COMMERCE_API_TOKEN`; provider calls use `PAYMENT_PROVIDER_API_TOKEN` or `CARRIER_PROVIDER_API_TOKEN`. Inbound user tokens and cookies are not forwarded.

## GET `/health`

No body or authentication. Returns **200**:

```json
{
  "service": "commerce-checkout",
  "status": "up",
  "dependency_check": false
}
```
This is process liveness only; it does not open SQLite or check HTTP/MQ providers.

## GET `/checkouts/{id}`

Reads record kind `checkouts` using checkout_id as the key. No request body or query parameters are required. Unknown IDs return **404** with `{"error":"not_found"}`. No list, update, delete, or pagination API exists.

### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `order_id` | string |  Order identity; checkout_id forwarded unchanged. |
| `status` | string | Always `confirmed`. See schema and business behavior. |
| `delivery_address` | string |  Address forwarded to shipping; no formatting validation. |

```json
{
  "order_id": "demo-1",
  "status": "confirmed",
  "delivery_address": "10 Main St"
}
```
```bash
curl -i 'http://127.0.0.1:8000/checkouts/demo-1'
```

## POST `/checkout`

Implementation: `Service.checkout`. Success status is **200**, including creation (not 201). Accepts a cart, forwards an order request, then stores the confirmed response. It does not price items or directly reserve stock.

### Request body

| Field | Type | Required for a new resource | Meaning |
|---|---|---|---|
| `checkout_id` | string | Yes | Required idempotency identity; safe identifier recommended.  |
| `cart` | object | Yes | See schema and behavior below.  |
| `cart.items` | array | Yes | See schema and behavior below.  |
| `cart.items[].sku` | string | Yes per item | Stock key. |
| `cart.items[].quantity` | integer | Yes per item | Positive whole number; inventory rejects booleans. |
| `total_cents` | integer | Yes | Caller-supplied positive total; no catalog repricing.  |
| `currency` | string | No | Optional here; downstream payments supports only USD. Default: USD |
| `delivery` | object | Yes | See schema and behavior below.  |
| `delivery.address` | string | Yes | Forwarded unchanged; no validation of address format.  |
| `payment_token` | string | Yes | Opaque external provider token; never use real payment details in sample.  |

```json
{
  "checkout_id": "demo-1",
  "cart": {
    "items": [
      {
        "sku": "book",
        "quantity": 1
      }
    ]
  },
  "total_cents": 2500,
  "delivery": {
    "address": "10 Main St"
  },
  "payment_token": "demo-token"
}
```
### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `order_id` | string |  Order identity; checkout_id forwarded unchanged. |
| `status` | string | Always `confirmed`. See schema and business behavior. |
| `delivery_address` | string |  Address forwarded to shipping; no formatting validation. |

```json
{
  "order_id": "demo-1",
  "status": "confirmed",
  "delivery_address": "10 Main St"
}
```
Complete supported schema: `components.schemas.WriteResult` in [openapi.json](openapi.json). The response is a JSON object, not a wrapper with `data` or `success`.

### Example call

```bash
curl -i -X POST 'http://127.0.0.1:8000/checkout' \
  -H 'Content-Type: application/json' \
  --data '{"checkout_id":"demo-1","cart":{"items":[{"sku":"book","quantity":1}]},"total_cents":2500,"delivery":{"address":"10 Main St"},"payment_token":"demo-token"}'
```

## Business behavior and retries

1. Look up `checkouts` by `checkout_id`; an existing result returns immediately, even if the new body differs.
2. Require a nonempty `cart.items`, then map to the orders API.
3. Forward `checkout_id → order_id`, `cart.items → items`, `delivery.address → delivery_address`, `total_cents`, `payment_token`, and currency (default USD only when omitted).
4. Call orders synchronously. Persist its response only after HTTP succeeds.

No price calculation, sum validation, address validation, currency normalization, or request-payload conflict check is implemented. The service trusts the orders response rather than validating its schema. If orders confirms but its event publish fails, checkout may return an error while the order is already stored upstream.

## Error and transport behavior

| HTTP status | JSON response | Actual condition |
|---|---|---|
| 400 | `{"error":"invalid_body_size"}` | POST length absent, zero, negative, or over 1 MiB. |
| 404 | `{"error":"not_found"}` | Unknown GET/POST path or missing GET resource. |
| 422 | `{"error":"invalid_request_or_business_rejection"}` | POST JSON/parsing/key/type/value error or business rejection. Error details are deliberately collapsed. |
| 422 | `{"error":"downstream_failure"}` | POST downstream HTTP 4xx. |
| 502 | `{"error":"downstream_failure"}` | POST downstream connection/timeout failure or upstream non-4xx HTTP error. |
| 503 | `{"error":"dependency_or_storage_failure"}` | POST broker, storage, or other uncaught exception. |

Only configured POST routes reach body validation. Malformed JSON and a nonnumeric Content-Length map to 422, not 400. A failed POST is not proof that no side effect occurred.

Unsupported methods (PUT, DELETE, PATCH, HEAD, OPTIONS) use the Python server's **501 HTML** response, outside the JSON error contract. GET storage/service-construction failures are not caught by the handler and can close the connection without a JSON error; no reliable GET 500/503 body is implemented. Empty headers/body at the HTTP parser level may also be handled by Python rather than the application.

Schemas define the supported client shapes, not exhaustive accepted inputs. There is no runtime OpenAPI/JSON Schema validator. Unknown fields are generally ignored, and many string types/nonempty checks are not enforced. New-request required fields may be bypassed on a stored-ID retry. Do not infer that every schema violation receives a specific status.

Machine-readable supported contracts: [openapi.json](openapi.json). Format: [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html).
