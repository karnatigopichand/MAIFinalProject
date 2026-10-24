# commerce-orders: field lineage

Reviewed against [create_order](../src/commerce_orders/service.py), [HTTP handler and worker](../src/commerce_orders/app.py), [transport/storage](../src/commerce_orders/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

| Source | Destination | Implementing method | Behavior |
|---|---|---|---|
| `request.order_id, items` | `inventory order_id, items` | `Service.create_order` | Reservation first |
| `request.total_cents` | `payments.amount_cents` | `Service.create_order` | No price recomputation |
| `request.currency, payment_token` | `payments.currency, payment_token` | `Service.create_order` | Forwarded unchanged |
| `request.delivery_address` | `orders payload / order event delivery_address` | `Service.create_order` | Required after upstream calls |
| `order_id` | `event_id = order:{order_id}` | `Service.create_order` | Stable logical event identity |

Delivery instructions are absent from the implemented request mapping and event payloads. An extra request field is not automatically propagated; adding one requires tracing explicit mappings and consumer contracts. Schemas in [openapi.json](openapi.json) describe supported payload shapes; [events.md](events.md) describes MQ payloads.
