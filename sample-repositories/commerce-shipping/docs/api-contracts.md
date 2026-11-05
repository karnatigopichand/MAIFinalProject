# commerce-shipping: HTTP API specification

Reviewed against [consume](../src/commerce_shipping/service.py), [HTTP handler and worker](../src/commerce_shipping/app.py), [transport/storage](../src/commerce_shipping/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Hosts and ports

| Environment | Client base URL | Listener binding | Status |
|---|---|---|---|
| Local | `http://127.0.0.1:8004` | `127.0.0.1:8004` | Configured; available only when the process is started |
| Development | `http://commerce-shipping:8004` | `0.0.0.0:8004` | Configured dummy DNS name; deployment/DNS not provisioned |

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
  "service": "commerce-shipping",
  "status": "up",
  "dependency_check": false
}
```
This is process liveness only; it does not open SQLite or check HTTP/MQ providers.

## GET `/shipments/{id}`

Reads record kind `shipments` using order_id as the key. No request body or query parameters are required. Unknown IDs return **404** with `{"error":"not_found"}`. No list, update, delete, or pagination API exists.

### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `order_id` | string |  Order identity from the originating request/event. |
| `tracking_number` | string |  Returned by carrier. |

```json
{
  "order_id": "demo-1",
  "tracking_number": "TRACK-1"
}
```
```bash
curl -i 'http://127.0.0.1:8004/shipments/demo-1'
```


## Business behavior and retries

1. Require the consumed logical topic `order.confirmed.v1`.
2. Read shipment by order_id; a redelivery retries pending publication then returns stored tracking.
3. Map event order_id to carrier reference and delivery_address to carrier address.
4. Persist carrier tracking_number, then publish `shipment.created.v1`.

There is no business POST endpoint; messages drive creation. A carrier success followed by a storage failure can create another shipment on redelivery. Receipt timeout after storage leaves a shipment readable but publication incomplete. Carrier output is not schema-validated.

## Error and transport behavior

| HTTP status | JSON response | Actual condition |
|---|---|---|
| 404 | `{"error":"not_found"}` | Unknown GET path, missing resource, or any POST (no write routes). |

There is no POST business endpoint, so POST body-validation and downstream-error mappings are unreachable over HTTP in this service. Worker failures are NACKed, not represented by HTTP responses. GET resource-storage failures can close the connection without a JSON response.

Unsupported methods (PUT, DELETE, PATCH, HEAD, OPTIONS) use the Python server's **501 HTML** response, outside the JSON error contract. GET storage/service-construction failures are not caught by the handler and can close the connection without a JSON error; no reliable GET 500/503 body is implemented. Empty headers/body at the HTTP parser level may also be handled by Python rather than the application.

Schemas define the supported client shapes, not exhaustive accepted inputs. There is no runtime OpenAPI/JSON Schema validator. Unknown fields are generally ignored, and many string types/nonempty checks are not enforced. New-request required fields may be bypassed on a stored-ID retry. Do not infer that every schema violation receives a specific status.

Machine-readable supported contracts: [openapi.json](openapi.json). Format: [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html).
