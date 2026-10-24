# commerce-inventory: HTTP API specification

Reviewed against [reserve](../src/commerce_inventory/service.py), [HTTP handler and worker](../src/commerce_inventory/app.py), [transport/storage](../src/commerce_inventory/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Hosts and ports

| Environment | Client base URL | Listener binding | Status |
|---|---|---|---|
| Local | `http://127.0.0.1:8002` | `127.0.0.1:8002` | Configured; available only when the process is started |
| Development | `http://commerce-inventory:8002` | `0.0.0.0:8002` | Configured dummy DNS name; deployment/DNS not provisioned |

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
  "service": "commerce-inventory",
  "status": "up",
  "dependency_check": false
}
```
This is process liveness only; it does not open SQLite or check HTTP/MQ providers.

## GET `/stock/{id}`

Reads record kind `stock` using SKU as the key. No request body or query parameters are required. Unknown IDs return **404** with `{"error":"not_found"}`. No list, update, delete, or pagination API exists.

### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `quantity` | integer | Minimum 0. Current stock quantity, or seeded quantity for POST /stock. |

```json
{
  "quantity": 5
}
```
```bash
curl -i 'http://127.0.0.1:8002/stock/book'
```

## POST `/reservations`

Implementation: `Service.reserve`. Success status is **200**, including creation (not 201). Seeds absolute stock levels, aggregates duplicate SKU lines, checks all availability before decrementing, and stores a reservation.

### Request body

| Field | Type | Required for a new resource | Meaning |
|---|---|---|---|
| `order_id` | string | Yes |   |
| `items` | array | Yes | See schema and behavior below.  |
| `items[].sku` | string | Yes per item | Stock key. |
| `items[].quantity` | integer | Yes per item | Positive whole number; inventory rejects booleans. |

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
### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `order_id` | string |  Order identity from the originating request/event. |
| `status` | string | Always `reserved`. See schema and business behavior. |
| `items` | object |  SKU to summed quantity; duplicate input lines are aggregated. |

```json
{
  "order_id": "demo-1",
  "status": "reserved",
  "items": {
    "book": 1
  }
}
```
Complete supported schema: `components.schemas.WriteResult` in [openapi.json](openapi.json). The response is a JSON object, not a wrapper with `data` or `success`.

### Example call

```bash
curl -i -X POST 'http://127.0.0.1:8002/reservations' \
  -H 'Content-Type: application/json' \
  --data '{"order_id":"demo-1","items":[{"sku":"book","quantity":1}]}'
```

## POST `/stock`

Implementation: `Service.seed_stock`. Success status is **200**, including creation (not 201). Sets stock to an absolute number; no inventory HTTP dependency.

### Request body

| Field | Type | Required for a new resource | Meaning |
|---|---|---|---|
| `sku` | string | Yes |   |
| `quantity` | integer | Yes | Absolute replacement quantity, not an increment.  |

```json
{
  "sku": "book",
  "quantity": 5
}
```
### Response body — 200


| Response field | Type | Meaning |
|---|---|---|
| `sku` | string |  Stock key. |
| `quantity` | integer | Minimum 0. Current stock quantity, or seeded quantity for POST /stock. |

```json
{
  "sku": "book",
  "quantity": 5
}
```
Complete supported schema: `components.schemas.StockWriteResult` in [openapi.json](openapi.json). The response is a JSON object, not a wrapper with `data` or `success`.

### Example call

```bash
curl -i -X POST 'http://127.0.0.1:8002/stock' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"book","quantity":5}'
```

## Business behavior and retries

1. Return an existing reservation for the same `order_id` without comparing the new request body.
2. Require strictly positive integer quantities (booleans rejected); aggregate repeated SKU lines.
3. Treat missing stock as zero and check every requested SKU before any decrement.
4. Decrement each SKU and store the reservation.

Writes commit separately: a storage failure during updates can leave partial changes. Stock is not automatically released when payment later fails. `POST /stock` sets the absolute quantity (including zero), so repeated seeding can overwrite available stock irrespective of existing reservations. There is no list endpoint or HTTP reservation lookup endpoint.

## Error and transport behavior

| HTTP status | JSON response | Actual condition |
|---|---|---|
| 400 | `{"error":"invalid_body_size"}` | POST length absent, zero, negative, or over 1 MiB. |
| 404 | `{"error":"not_found"}` | Unknown GET/POST path or missing GET resource. |
| 422 | `{"error":"invalid_request_or_business_rejection"}` | POST JSON/parsing/key/type/value error or business rejection. Error details are deliberately collapsed. |
| 503 | `{"error":"dependency_or_storage_failure"}` | POST broker, storage, or other uncaught exception. |

Only configured POST routes reach body validation. Malformed JSON and a nonnumeric Content-Length map to 422, not 400. Inventory has no outbound HTTP/MQ business calls. A failed POST is not proof that no side effect occurred.

Unsupported methods (PUT, DELETE, PATCH, HEAD, OPTIONS) use the Python server's **501 HTML** response, outside the JSON error contract. GET storage/service-construction failures are not caught by the handler and can close the connection without a JSON error; no reliable GET 500/503 body is implemented. Empty headers/body at the HTTP parser level may also be handled by Python rather than the application.

Schemas define the supported client shapes, not exhaustive accepted inputs. There is no runtime OpenAPI/JSON Schema validator. Unknown fields are generally ignored, and many string types/nonempty checks are not enforced. New-request required fields may be bypassed on a stored-ID retry. Do not infer that every schema violation receives a specific status.

Machine-readable supported contracts: [openapi.json](openapi.json). Format: [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html).
