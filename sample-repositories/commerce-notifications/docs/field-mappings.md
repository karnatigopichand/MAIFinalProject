# commerce-notifications: field lineage

Reviewed against [consume](../src/commerce_notifications/service.py), [HTTP handler and worker](../src/commerce_notifications/app.py), [transport/storage](../src/commerce_notifications/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

| Source | Destination | Implementing method | Behavior |
|---|---|---|---|
| `order event.order_id` | `body: Order {order_id} confirmed` | `Service.consume` | Order template |
| `shipment event.order_id, tracking_number` | `body: Order {order_id} shipped: {tracking_number}` | `Service.consume` | Shipment template |
| `event.event_id` | `outbox key / event_id` | `Service.consume` | Deduplication identity |

Delivery instructions are absent from the implemented request mapping and event payloads. An extra request field is not automatically propagated; adding one requires tracing explicit mappings and consumer contracts. Schemas in [openapi.json](openapi.json) describe supported payload shapes; [events.md](events.md) describes MQ payloads.
