# commerce-notifications

Runnable Python HTTP API with real external HTTP dependencies, ActiveMQ STOMP integration, SQLite storage and JSON stdout logging. Dependencies and fields are explicit in `contracts.json` and source comments.

## Setup and execution

From this repository directory (Python 3.11+):

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
export ACTIVEMQ_USERNAME=your-broker-user
export ACTIVEMQ_PASSWORD=your-broker-password
.venv/bin/python -m commerce_notifications.app --config config/local.json
```

For shipping and notifications, start a separate consumer process in another terminal using the same virtual environment and config:

```bash
.venv/bin/python -m commerce_notifications.app --config config/local.json --worker
```

Other services have no subscriptions and do not need workers. Run tests with `PYTHONPATH=src python3 -m unittest discover -s tests -v` (real loopback sockets required). Runtime has no stub fallback; test doubles exist only in tests.

## Configuration

`config/local.json` uses loopback hosts; `config/development.json` uses explicit dummy DNS names matching the external API names. Configure DNS/container aliases or replace these hosts. Each HTTP target specifies scheme, host, port, endpoints, and timeout. Each queue binding specifies a concrete `/queue/...` destination. Config is JSON rather than YAML to avoid an additional runtime dependency. MQ credentials come from environment variables, never committed config values.

The API exposes `/health` and a resource GET endpoint; write routes, port, and queue bindings are documented in `contracts.json` and generated docs. Event-only resources expose read/health APIs but receive business updates through ActiveMQ. Inventory `/stock` is a demo setup endpoint.

## Dependencies and limits

ActiveMQ Classic must expose STOMP on port 61613. Payment/carrier provider APIs are separate real HTTP targets; their documented payload contracts must be fulfilled by your environment. No provider simulator is included at runtime. API health is liveness, not dependency readiness. Server is sequential and has no authentication: use a controlled demo network.

SQLite and broker publication are not one transaction. Pending order/shipment publication retries on request/event redelivery; there is no background outbox dispatcher. Partial queue fan-out can redeliver duplicates; consumers deduplicate sequential deliveries. Inventory is not compensated after payment failure. See `docs/data-model.md` and technical debt.

Logs are newline-delimited JSON suitable for collection by a Datadog agent; no collector is bundled. Request bodies and secrets are not intentionally logged. Correlation propagation remains documented technical debt.

## Implementation-reviewed documentation

Start with [the complete API specification](docs/api-contracts.md) or import [openapi.json](docs/openapi.json) into an OpenAPI viewer. Documentation includes configured addresses (not deployment claims), security, headers, payloads, exact error mapping, message contracts, data records and field lineage. Maintain these documents alongside code changes; do not regenerate summary templates over them. Run `python3 scripts/validate_sample_docs.py` from the workspace to check route/config/source alignment.
