# commerce-payments: message contracts

Reviewed against [authorize](../src/commerce_payments/service.py), [HTTP handler and worker](../src/commerce_payments/app.py), [transport/storage](../src/commerce_payments/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

## Queue bindings and payloads

This service neither publishes nor consumes MQ messages. It does not need an ActiveMQ connection for its business methods. Broker config is shared configuration structure, not evidence of a runtime queue dependency.

## Protocol and security

ActiveMQ Classic, STOMP 1.2; local broker `127.0.0.1:61613`, development `activemq:61613`. Login/passcode come from ACTIVEMQ_USERNAME/PASSWORD. TLS is disabled in checked-in config. See [configuration](configuration.md) for TLS and broker policy boundaries.

Publishing uses JSON text with headers `content-type: application/json`, `persistent: true`, `event-type: <logical topic>`, and a generated `receipt` ID. Publishers wait up to five seconds per destination for matching receipts. The worker determines logical topic from the destination-to-topic config, not from `event-type`.

Consumers subscribe with `ack=client-individual` and `activemq.prefetchSize=1`; `on_message` parses frame.body as JSON, invokes Service.consume, then ACKs the STOMP ack token. Exceptions log an error type and NACK. Broker redelivery limits/dead-letter handling must be configured externally. There is no schema validator, retry count, or application-managed dead-letter queue.

Orders publishes one event to two separate queues so shipping and notifications each receive a copy. Sharing one queue between those services would load-balance rather than broadcast. Partial fan-out can duplicate messages when retried. No global ordering is promised between notification queues.

## Idempotency and failures

1. Return stored authorization for an existing `order_id`, without comparing the token, amount, or currency in a retry.
2. Require `amount_cents` to be a strict positive integer and currency exactly `USD`.
3. Map amount to provider `amount`, retain currency, map payment_token to provider `token`.
4. Require provider response status `authorized`; otherwise raise business rejection.
5. Store order_id, authorization_id, and status. No token is persisted.

There is no capture, refund, cancellation, or provider idempotency key. A provider success followed by a local storage failure can lead to another authorization on retry. Provider responses are not schema-validated; missing fields can surface as 422.

Event fields are ordinary JSON values with supported string IDs/addresses/tracking values; no schema registry is running. Unsupported topics raise ValueError in consumers. Unknown additional fields are ignored. The sample event examples include all publisher fields, while the consumed-required-key list reflects actual reads on a new record. Stored-record retries may read fewer keys.
