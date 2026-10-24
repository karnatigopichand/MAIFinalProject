# commerce-inventory: runtime configuration and security

Reviewed against [reserve](../src/commerce_inventory/service.py), [HTTP handler and worker](../src/commerce_inventory/app.py), [transport/storage](../src/commerce_inventory/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Server addresses

| Environment | Client base URL | Listener binding | Status |
|---|---|---|---|
| Local | `http://127.0.0.1:8002` | `127.0.0.1:8002` | Configured; available only when the process is started |
| Development | `http://commerce-inventory:8002` | `0.0.0.0:8002` | Configured dummy DNS name; deployment/DNS not provisioned |

`0.0.0.0` is a bind address, not a client hostname. No public URL, TLS termination, or deployed environment is established by this repository. Query parameters are ignored; paths are case-sensitive and trailing slashes are not normalized. Use simple identifiers such as `demo-1`, `book`, and `shipment:demo-1`; the handler does not URL-decode encoded path identifiers.

## Launch

Run from the repository root so relative config/database paths resolve correctly:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m commerce_inventory.app --config config/local.json
```

Configuration selection: explicit `--config`, otherwise `COMMERCE_CONFIG`, otherwise `config/local.json`. Files are JSON. Development API binds all interfaces; local binds loopback. Change config values and restart processes to apply changes. There is no hot reload.

This service has no subscriptions; `--worker` is rejected.

## Outbound HTTP destinations

| Dependency | Local configured URL | Development configured URL | Timeout |
|---|---|---|---|
| None | — | — | — |

`HTTPClient.post` looks up the configured target, requires the code-supplied path to appear in `endpoints`, and constructs scheme/host/port/path. Changing a configured path alone is insufficient if the call site still uses the old path. No retries, authorization header, connection pool, or inbound correlation propagation are implemented. URL redirects follow urllib defaults. HTTPS for an outbound dependency uses the Python default certificate trust; no custom HTTP TLS credentials are configured.

## Database

Path: `data/inventory.sqlite` for both checked-in environments, relative to the current directory. Set distinct paths when running environments together. The directory is created automatically. Workers and API processes for one service must use the same file. Each operation opens its own SQLite connection, with a 10-second lock timeout.

## Broker

| Setting | Local | Development |
|---|---|---|
| Host | `127.0.0.1` | `activemq` |
| STOMP port | `61613` | `61613` |
| TLS | `False` | `False` |
| Username environment variable | `ACTIVEMQ_USERNAME` | `ACTIVEMQ_USERNAME` |
| Password environment variable | `ACTIVEMQ_PASSWORD` | `ACTIVEMQ_PASSWORD` |
| Receipt timeout | 5 seconds | 5 seconds |

Connection timeout defaults to 5 seconds (`connect_timeout_seconds` can override); heartbeats are configured at 10 seconds. Enable `tls` and provide `ca_certs` for verified broker TLS. Publishers connect on demand; API startup and health do not prove broker connectivity. Workers subscribe at startup and exit on disconnection; automatic reconnect is not implemented. Redelivery limits, dead-letter policy, queue authorization, and broker provisioning are external responsibilities.

## Security contract

HTTP authentication and authorization are **not implemented**. The OpenAPI document uses `security: []` and defines no security schemes. There is no JWT, OAuth2, Basic authentication, API-key validation, role check, rate limit, or automatic 401/403 response. The listener serves plain HTTP; HTTPS requires an external proxy. CORS/OPTIONS support is absent. Payment tokens are business payload fields, not API authentication credentials.

ActiveMQ uses STOMP login/passcode read from `ACTIVEMQ_USERNAME` and `ACTIVEMQ_PASSWORD`; missing variables become empty strings, and broker policy decides whether login succeeds. Config defaults to `tls: false`; when enabled, `ca_certs` supplies broker CA verification. There is no implemented client-certificate/mTLS configuration. Do not confuse broker credentials with HTTP security.

## JSON logs / Datadog

Application and configured library logs go to stdout as one JSON object per line. Fields: timestamp (UTC), status, service, env, event; HTTP events include method/path/status or target/duration; MQ events include queue/topic and sometimes event_id. Request bodies, payment tokens, addresses, and upstream response bodies are not intentionally logged by application log calls. Library log text is not a general-purpose secret-redaction system.

```json
{"timestamp":"2026-10-24T12:00:00+00:00","status":"INFO","service":"commerce-inventory","env":"local","event":"server.started","port":8002}
```

Configure a Datadog collector to ingest stdout; no Datadog agent/API key or exporter is included. The main process sets COMMERCE_ENV from config. IDs are not correlated end-to-end yet. See the logging debt documents. Interpreter/parser failures outside configured application logging may still produce native output.
