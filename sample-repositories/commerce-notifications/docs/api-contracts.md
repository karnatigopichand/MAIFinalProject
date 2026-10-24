# commerce-notifications: HTTP API specification

Reviewed against [consume](../src/commerce_notifications/service.py), [HTTP handler and worker](../src/commerce_notifications/app.py), [transport/storage](../src/commerce_notifications/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Hosts and ports

| Environment | Client base URL | Listener binding | Status |
|---|---|---|---|
| Local | `http://127.0.0.1:8005` | `127.0.0.1:8005` | Configured; available only when the process is started |
| Development | `http://commerce-notifications:8005` | `0.0.0.0:8005` | Configured dummy DNS name; deployment/DNS not provisioned |

`0.0.0.0` is a bind address, not a client hostname. No public URL, TLS termination, or deployed environment is established by this repository. Query parameters are ignored; paths are case-sensitive and trailing slashes are not normalized. Use simple identifiers such as `demo-1`, `book`, and `shipment:demo-1`; the handler does not URL-decode encoded path identifiers.

## Security contract

HTTP authentication and authorization are **not implemented**. The OpenAPI document uses `security: []` and defines no security schemes. There is no JWT, OAuth2, Basic authentication, API-key validation, role check, rate limit, or automatic 401/403 response. The listener serves plain HTTP; HTTPS requires an external proxy. CORS/OPTIONS support is absent. Payment tokens are business payload fields, not API authentication credentials.

ActiveMQ uses STOMP login/passcode read from `ACTIVEMQ_USERNAME` and `ACTIVEMQ_PASSWORD`; missing variables become empty strings, and broker policy decides whether login succeeds. Config defaults to `tls: false`; when enabled, `ca_certs` supplies broker CA verification. There is no implemented client-certificate/mTLS configuration. Do not confuse broker credentials with HTTP security.

## Headers and media types

| Header | Request behavior | Response behavior |
|---|---|---|
| `Content-Type` | Send `application/json` for POST. The handler parses JSON regardless of this header and does not return 415 for another value. | Application GET/POST responses use `application/json`. |
| `Content-Length` | POST requires declared length from 1 through 1,048,576 bytes. Most HTTP clients calculate it. Chunked bodies are not supported. GET does not inspect a body. | Set to the encoded JSON byte length. |
| `Accept` | Optional and ignored; no content negotiation. | No negotiated representation. |
| `Authorization`, API-key headers, cookies | Not checked; do not confer authentication. | No token/cookie issued. |
| `X-Request-ID` | Accepted as an arbitrary header but not read, propagated, or echoed. | Not returned. |
| Other headers | No application-specific processing. | Python HTTP server also adds `Server` and `Date`; no CORS headers. |

Each outbound HTTP call sends `Content-Type: application/json` and a newly generated `X-Request-ID`. It does not forward inbound authorization, cookies, or request IDs. Provider credentials are not configured by HTTPClient.

## GET `/health`

No body or authentication. Returns **200**:

```json
{
  "service": "commerce-notifications",
  "status": "up",
  "dependency_check": false
}
```
This is process liveness only; it does not open SQLite or check HTTP/MQ providers.

## GET `/notifications/{id}`

Reads record kind `outbox` using event_id as the key. No request body or query parameters are required. Unknown IDs return **404** with `{"error":"not_found"}`. No list, update, delete, or pagination API exists.

### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `event_id` | string |  Message deduplication identity. |
| `topic` | string | Allowed: `order.confirmed.v1`, `shipment.created.v1`. See schema and business behavior. |
| `body` | string |  Rendered text; no email is sent. |

```json
{
  "event_id": "shipment:demo-1",
  "topic": "shipment.created.v1",
  "body": "Order demo-1 shipped: TRACK-1"
}
```
```bash
curl -i 'http://127.0.0.1:8005/notifications/shipment:demo-1'
```


## Business behavior and retries

1. Accept only `order.confirmed.v1` and `shipment.created.v1`.
2. Deduplicate using event_id, irrespective of topic or body changes.
3. Render `Order {order_id} confirmed` or `Order {order_id} shipped: {tracking_number}`.
4. Store event_id, topic, and body under the outbox kind.

There is no business POST endpoint, recipient directory, email delivery, or SMS delivery. Duplicate event IDs across unrelated messages will suppress the later message. The order and shipment queues can be processed in either order; notifications do not establish global event ordering.

## Error and transport behavior

| HTTP status | JSON response | Actual condition |
|---|---|---|
| 404 | `{"error":"not_found"}` | Unknown GET path, missing resource, or any POST (no write routes). |

There is no POST business endpoint, so POST body-validation and downstream-error mappings are unreachable over HTTP in this service. Worker failures are NACKed, not represented by HTTP responses. GET resource-storage failures can close the connection without a JSON response.

Unsupported methods (PUT, DELETE, PATCH, HEAD, OPTIONS) use the Python server's **501 HTML** response, outside the JSON error contract. GET storage/service-construction failures are not caught by the handler and can close the connection without a JSON error; no reliable GET 500/503 body is implemented. Empty headers/body at the HTTP parser level may also be handled by Python rather than the application.

Schemas define the supported client shapes, not exhaustive accepted inputs. There is no runtime OpenAPI/JSON Schema validator. Unknown fields are generally ignored, and many string types/nonempty checks are not enforced. New-request required fields may be bypassed on a stored-ID retry. Do not infer that every schema violation receives a specific status.

Machine-readable supported contracts: [openapi.json](openapi.json). Format: [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html).
