# E-commerce network services

Six standalone Python packages implement the sample corpus used by the three-agent final project. They live in this workspace for now; no separate GitHub repositories have been created.

| Repository/API hostname | Port | Write endpoint | Read endpoint | Message responsibilities |
|---|---|---|---|---|
| commerce-checkout | 8000 | POST /checkout | GET /checkouts/{id} | None |
| commerce-orders | 8001 | POST /orders | GET /orders/{id} | Publish order confirmation |
| commerce-inventory | 8002 | POST /reservations, POST /stock | GET /stock/{sku} | None |
| commerce-payments | 8003 | POST /authorizations | GET /authorizations/{id} | None |
| commerce-shipping | 8004 | Headless business consumer | GET /shipments/{id} | Consume order; publish shipment |
| commerce-notifications | 8005 | Headless business consumer | GET /notifications/{event_id} | Consume order and shipment |

All six serve `GET /health` (liveness only). Paths use identifiers without embedded `/` characters. Inventory `/stock` is an administrative demo seed endpoint, not a production public interface.

## Environment configuration

Every repository contains `config/local.json` and `config/development.json`. Local uses `127.0.0.1` with different ports. Development uses API names as dummy DNS hostnames: `commerce-orders`, `commerce-inventory`, and so on. Supply DNS/container aliases or replace the hostname with an actual external deployment. Endpoints, scheme, port, and timeout are explicit per dependency. Config files are JSON to keep configuration parsing dependency-free.

`COMMERCE_CONFIG` or `--config` selects a file. Database file paths are relative to the process working directory; start each process from its repository root. API and worker for the same service must use the same database file. Do not expose this unauthenticated demo on a public network.

External prerequisites:

- ActiveMQ Classic with STOMP enabled on port 61613. Development hostname: `activemq`.
- `payment-provider-api:9000` implements `POST /charges`: request `amount`, `currency`, `token`; response `status` (`authorized` or `declined`) and `authorization_id` on success.
- `carrier-provider-api:9001` implements `POST /shipments`: request `reference`, `address`; response `tracking_number`.

These provider URLs are placeholders for actual external APIs, not included simulators. Replace hosts/endpoints and adapt mappings to your real provider contract. There is no runtime fallback to stubs. Full fulfillment requires the broker and both external providers.

## Run APIs and workers

For each repository, in its own terminal:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
export ACTIVEMQ_USERNAME=your-user
export ACTIVEMQ_PASSWORD=your-password
.venv/bin/python -m commerce_orders.app --config config/local.json
```

Replace `commerce_orders` with the package for that repository. For shipping and notifications, also start their workers in separate terminals:

```bash
.venv/bin/python -m commerce_shipping.app --config config/local.json --worker
.venv/bin/python -m commerce_notifications.app --config config/local.json --worker
```

Run each command from the matching repository directory with its matching virtual environment. Restart a worker after broker disconnection; automatic reconnect/backoff is not implemented.

Seed inventory, then send checkout (from the workspace root):

```bash
curl -X POST http://127.0.0.1:8002/stock -H 'Content-Type: application/json' -d '{"sku":"book","quantity":5}'
python3 scripts/demo_commerce.py --order-id demo-1
curl http://127.0.0.1:8004/shipments/demo-1
curl http://127.0.0.1:8005/notifications/shipment:demo-1
```

The demo uses a synthetic payment token; replace the request appropriately for the configured provider. Never use real payment data in a demonstration.

## ActiveMQ queue contracts

| Event | Publisher | Destination | Consumer |
|---|---|---|---|
| order.confirmed.v1 | orders | /queue/commerce.shipping.order-confirmed.v1 | shipping |
| order.confirmed.v1 | orders | /queue/commerce.notifications.order-confirmed.v1 | notifications |
| shipment.created.v1 | shipping | /queue/commerce.notifications.shipment-created.v1 | notifications |

Orders sends to two distinct queues: two consumers on one queue would compete rather than both receiving each event. Publishers request persistent delivery and wait for STOMP receipts. Workers ACK after processing and NACK on failure. Set broker redelivery/dead-letter policies to bound poison-message retries. Receipt acknowledgment does not make SQLite writes and broker sends atomic.

## Logging and technical debt

Application logs are newline-delimited JSON on stdout, with `timestamp`, `status`, `service`, `env`, `event`, and context such as target, queue, and duration. Collect stdout with a Datadog agent configured for JSON; no collector, credentials, or Datadog transport is bundled. Logs avoid request bodies, tokens, addresses, and upstream error bodies. Python startup failures may still produce interpreter tracebacks.

Each service has four authored debt documents: mapping validation, transactional durability, log correlation, and log observability. Estimates are illustrative. Correlation currently does not propagate end-to-end; this is intentionally identified as debt rather than claimed as implemented.

## Testing and implementation-reviewed documentation

```bash
python3 scripts/test_samples.py
python3 scripts/validate_sample_docs.py
```

Tests use actual loopback HTTP servers. External providers and MQ are replaced only in test fixtures. Broker receipt/fan-out and worker ACK/NACK have isolated tests; opt into actual ActiveMQ verification separately:

```bash
ACTIVEMQ_TEST_HOST=127.0.0.1 .venv/bin/python -m unittest discover -s tests -p test_activemq_live.py -v
```

Run that command from the workspace using an environment containing `stomp.py`. The live check uses the named `commerce.integration.shipping` and `commerce.integration.notifications` queues, which may remain on the broker afterward.

Each service has seven implementation-reviewed guides, an OpenAPI 3.1 specification, reviewed source hashes, and multiple authored debt documents. The old summary generator has been removed. Documentation is maintained alongside code; the validator checks source freshness, routes, configured servers, and references without overwriting prose. Pinecone/Neo4j ingestion and AI agents remain separate workstreams.

## Reliability boundaries

Sequential API execution, no authentication, no inventory compensation after failed payment, no concurrent reservation isolation, no idempotency conflict detection, and no atomic database/broker transaction. Orders/shipping retry unfinished publication on a later request/event delivery; no background dispatcher exists. Partial fan-out or a crash before recording publication may duplicate messages. Successful sequential consumer redelivery is deduplicated. Health endpoints do not verify dependencies. These are demo services, not production-ready commerce infrastructure.

## Protocol references

Queue destinations and persistent STOMP sends follow the [ActiveMQ Classic STOMP documentation](https://activemq.apache.org/components/classic/documentation/stomp). Listener subscriptions and acknowledgment APIs use [stomp.py](https://stomppy.readthedocs.io/en/latest/quickstart.html).

## API specification index

| Service | Human-readable specification | Machine-readable specification |
|---|---|---|
| Checkout | [API contract](commerce-checkout/docs/api-contracts.md) | [OpenAPI](commerce-checkout/docs/openapi.json) |
| Orders | [API contract](commerce-orders/docs/api-contracts.md) | [OpenAPI](commerce-orders/docs/openapi.json) |
| Inventory | [API contract](commerce-inventory/docs/api-contracts.md) | [OpenAPI](commerce-inventory/docs/openapi.json) |
| Payments | [API contract](commerce-payments/docs/api-contracts.md) | [OpenAPI](commerce-payments/docs/openapi.json) |
| Shipping | [API contract](commerce-shipping/docs/api-contracts.md) | [OpenAPI](commerce-shipping/docs/openapi.json) |
| Notifications | [API contract](commerce-notifications/docs/api-contracts.md) | [OpenAPI](commerce-notifications/docs/openapi.json) |

OpenAPI describes supported client payloads, not runtime schema enforcement. Security is explicitly empty because HTTP authentication is absent. Documented development URLs are configured hostnames, not confirmed deployed endpoints.

For full OpenAPI structure and request/response example validation, use a development environment with `pip install -r scripts/requirements-docs.txt`, then run `python3 scripts/validate_sample_docs.py --openapi`. This dependency is documentation tooling, not a service runtime requirement.
