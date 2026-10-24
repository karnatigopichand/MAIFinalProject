# commerce-checkout: message contracts

Reviewed against [checkout](../src/commerce_checkout/service.py), [HTTP handler and worker](../src/commerce_checkout/app.py), [transport/storage](../src/commerce_checkout/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Queue bindings and payloads

This service neither publishes nor consumes MQ messages. It does not need an ActiveMQ connection for its business methods. Broker config is shared configuration structure, not evidence of a runtime queue dependency.

## Protocol and security

ActiveMQ Classic, STOMP 1.2; local broker `127.0.0.1:61613`, development `activemq:61613`. Login/passcode come from ACTIVEMQ_USERNAME/PASSWORD. TLS is disabled in checked-in config. See [configuration](configuration.md) for TLS and broker policy boundaries.

Publishing uses JSON text with headers `content-type: application/json`, `persistent: true`, `event-type: <logical topic>`, and a generated `receipt` ID. Publishers wait up to five seconds per destination for matching receipts. The worker determines logical topic from the destination-to-topic config, not from `event-type`.

Consumers subscribe with `ack=client-individual` and `activemq.prefetchSize=1`; `on_message` parses frame.body as JSON, invokes Service.consume, then ACKs the STOMP ack token. Exceptions log an error type and NACK. Broker redelivery limits/dead-letter handling must be configured externally. There is no schema validator, retry count, or application-managed dead-letter queue.

Orders publishes one event to two separate queues so shipping and notifications each receive a copy. Sharing one queue between those services would load-balance rather than broadcast. Partial fan-out can duplicate messages when retried. No global ordering is promised between notification queues.

## Idempotency and failures

1. Look up `checkouts` by `checkout_id`; an existing result returns immediately, even if the new body differs.
2. Require a nonempty `cart.items`, then map to the orders API.
3. Forward `checkout_id → order_id`, `cart.items → items`, `delivery.address → delivery_address`, `total_cents`, `payment_token`, and currency (default USD only when omitted).
4. Call orders synchronously. Persist its response only after HTTP succeeds.

No price calculation, sum validation, address validation, currency normalization, or request-payload conflict check is implemented. The service trusts the orders response rather than validating its schema. If orders confirms but its event publish fails, checkout may return an error while the order is already stored upstream.

Event fields are ordinary JSON values with supported string IDs/addresses/tracking values; no schema registry is running. Unsupported topics raise ValueError in consumers. Unknown additional fields are ignored. The sample event examples include all publisher fields, while the consumed-required-key list reflects actual reads on a new record. Stored-record retries may read fewer keys.
