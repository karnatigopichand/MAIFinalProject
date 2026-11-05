# commerce-payments: HTTP API specification

Reviewed against [authorize](../src/commerce_payments/service.py), [HTTP handler and worker](../src/commerce_payments/app.py), [transport/storage](../src/commerce_payments/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Hosts and ports

| Environment | Client base URL | Listener binding | Status |
|---|---|---|---|
| Local | `http://127.0.0.1:8003` | `127.0.0.1:8003` | Configured; available only when the process is started |
| Development | `http://commerce-payments:8003` | `0.0.0.0:8003` | Configured dummy DNS name; deployment/DNS not provisioned |

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
  "service": "commerce-payments",
  "status": "up",
  "dependency_check": false
}
```
This is process liveness only; it does not open SQLite or check HTTP/MQ providers.

## GET `/authorizations/{id}`

Reads record kind `authorizations` using order_id as the key. No request body or query parameters are required. Unknown IDs return **404** with `{"error":"not_found"}`. No list, update, delete, or pagination API exists.

### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `order_id` | string |  Order identity from the originating request/event. |
| `authorization_id` | string |  Returned by external provider. |
| `status` | string | Always `authorized`. See schema and business behavior. |

```json
{
  "order_id": "demo-1",
  "authorization_id": "AUTH-1",
  "status": "authorized"
}
```
```bash
curl -i 'http://127.0.0.1:8003/authorizations/demo-1'
```

## POST `/authorizations`

Implementation: `Service.authorize`. Success status is **200**, including creation (not 201). Checks positive integer cents and USD, calls an external provider, and stores successful authorization metadata without the token.

### Request body

| Field | Type | Required for a new resource | Meaning |
|---|---|---|---|
| `order_id` | string | Yes |   |
| `amount_cents` | integer | Yes | Strict positive integer.  |
| `currency` | string | Yes | See schema and behavior below.  |
| `payment_token` | string | Yes |   |

```json
{
  "order_id": "demo-1",
  "amount_cents": 2500,
  "currency": "USD",
  "payment_token": "demo-token"
}
```
### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `order_id` | string |  Order identity from the originating request/event. |
| `authorization_id` | string |  Returned by external provider. |
| `status` | string | Always `authorized`. See schema and business behavior. |

```json
{
  "order_id": "demo-1",
  "authorization_id": "AUTH-1",
  "status": "authorized"
}
```
Complete supported schema: `components.schemas.WriteResult` in [openapi.json](openapi.json). The response is a JSON object, not a wrapper with `data` or `success`.

### Example call

```bash
curl -i -X POST 'http://127.0.0.1:8003/authorizations' \
  -H 'Content-Type: application/json' \
  --data '{"order_id":"demo-1","amount_cents":2500,"currency":"USD","payment_token":"demo-token"}'
```

## Business behavior and retries

1. Return stored authorization for an existing `order_id`, without comparing the token, amount, or currency in a retry.
2. Require `amount_cents` to be a strict positive integer and currency exactly `USD`.
3. Map amount to provider `amount`, retain currency, map payment_token to provider `token`.
4. Require provider response status `authorized`; otherwise raise business rejection.
5. Store order_id, authorization_id, and status. No token is persisted.

There is no capture, refund, cancellation, or provider idempotency key. A provider success followed by a local storage failure can lead to another authorization on retry. Provider responses are not schema-validated; missing fields can surface as 422.

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
