# commerce-orders: message contracts

Reviewed against [create_order](../src/commerce_orders/service.py), [HTTP handler and worker](../src/commerce_orders/app.py), [transport/storage](../src/commerce_orders/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Queue bindings and payloads

### Publishes `order.confirmed.v1`

Destinations: `/queue/commerce.shipping.order-confirmed.v1`, `/queue/commerce.notifications.order-confirmed.v1`.

```json
{
  "event_id": "order:demo-1",
  "order_id": "demo-1",
  "status": "confirmed",
  "delivery_address": "10 Main St"
}
```


## Protocol and security

ActiveMQ Classic, STOMP 1.2; local broker `127.0.0.1:61613`, development `activemq:61613`. Login/passcode come from ACTIVEMQ_USERNAME/PASSWORD. TLS is disabled in checked-in config. See [configuration](configuration.md) for TLS and broker policy boundaries.

Publishing uses JSON text with headers `content-type: application/json`, `persistent: true`, `event-type: <logical topic>`, and a generated `receipt` ID. Publishers wait up to five seconds per destination for matching receipts. The worker determines logical topic from the destination-to-topic config, not from `event-type`.

Consumers subscribe with `ack=client-individual` and `activemq.prefetchSize=1`; `on_message` parses frame.body as JSON, invokes Service.consume, then ACKs the STOMP ack token. Exceptions log an error type and NACK. Broker redelivery limits/dead-letter handling must be configured externally. There is no schema validator, retry count, or application-managed dead-letter queue.

Orders publishes one event to two separate queues so shipping and notifications each receive a copy. Sharing one queue between those services would load-balance rather than broadcast. Partial fan-out can duplicate messages when retried. No global ordering is promised between notification queues.

## Idempotency and failures

1. Read `orders` by `order_id`. On a retry, attempt any pending publication, then return the stored result without rechecking the new request body.
2. Require nonempty items and a strict positive Python integer `total_cents` (booleans rejected).
3. POST reservation to inventory. If rejected, payment is not attempted.
4. POST authorization to payments. If rejected, stock is not released automatically.
5. Store `{order_id,status:"confirmed",delivery_address}`.
6. Publish `order.confirmed.v1` to shipping and notifications queues and record publication completion.

The order result can exist even when POST returned 503 due to publication failure. Retry the same ID to retry publication. A partially successful fan-out can duplicate a delivery. Downstream HTTP response payloads for reservation/payment are not inspected; success is determined by HTTP success and parseable JSON. The caller supplies the total; there is no pricing engine.

Event fields are ordinary JSON values with supported string IDs/addresses/tracking values; no schema registry is running. Unsupported topics raise ValueError in consumers. Unknown additional fields are ignored. The sample event examples include all publisher fields, while the consumed-required-key list reflects actual reads on a new record. Stored-record retries may read fewer keys.
