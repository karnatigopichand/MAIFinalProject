# commerce-notifications: message contracts

Reviewed against [consume](../src/commerce_notifications/service.py), [HTTP handler and worker](../src/commerce_notifications/app.py), [transport/storage](../src/commerce_notifications/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Queue bindings and payloads

### Consumes `order.confirmed.v1`

Queue: `/queue/commerce.notifications.order-confirmed.v1`. Required keys for a new record: `event_id`, `order_id`.

```json
{
  "event_id": "order:demo-1",
  "order_id": "demo-1",
  "status": "confirmed",
  "delivery_address": "10 Main St"
}
```

### Consumes `shipment.created.v1`

Queue: `/queue/commerce.notifications.shipment-created.v1`. Required keys for a new record: `event_id`, `order_id`, `tracking_number`.

```json
{
  "event_id": "shipment:demo-1",
  "order_id": "demo-1",
  "tracking_number": "TRACK-1"
}
```


## Protocol and security

ActiveMQ Classic, STOMP 1.2; local broker `127.0.0.1:61613`, development `activemq:61613`. Login/passcode come from ACTIVEMQ_USERNAME/PASSWORD. TLS is disabled in checked-in config. See [configuration](configuration.md) for TLS and broker policy boundaries.

Publishing uses JSON text with headers `content-type: application/json`, `persistent: true`, `event-type: <logical topic>`, and a generated `receipt` ID. Publishers wait up to five seconds per destination for matching receipts. The worker determines logical topic from the destination-to-topic config, not from `event-type`.

Consumers subscribe with `ack=client-individual` and `activemq.prefetchSize=1`; `on_message` parses frame.body as JSON, invokes Service.consume, then ACKs the STOMP ack token. Exceptions log an error type and NACK. Broker redelivery limits/dead-letter handling must be configured externally. There is no schema validator, retry count, or application-managed dead-letter queue.

Orders publishes one event to two separate queues so shipping and notifications each receive a copy. Sharing one queue between those services would load-balance rather than broadcast. Partial fan-out can duplicate messages when retried. No global ordering is promised between notification queues.

## Idempotency and failures

1. Accept only `order.confirmed.v1` and `shipment.created.v1`.
2. Deduplicate using event_id, irrespective of topic or body changes.
3. Render `Order {order_id} confirmed` or `Order {order_id} shipped: {tracking_number}`.
4. Store event_id, topic, and body under the outbox kind.

There is no business POST endpoint, recipient directory, email delivery, or SMS delivery. Duplicate event IDs across unrelated messages will suppress the later message. The order and shipment queues can be processed in either order; notifications do not establish global event ordering.

Event fields are ordinary JSON values with supported string IDs/addresses/tracking values; no schema registry is running. Unsupported topics raise ValueError in consumers. Unknown additional fields are ignored. The sample event examples include all publisher fields, while the consumed-required-key list reflects actual reads on a new record. Stored-record retries may read fewer keys.
