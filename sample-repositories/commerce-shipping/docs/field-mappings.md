# commerce-shipping: field lineage

Reviewed against [consume](../src/commerce_shipping/service.py), [HTTP handler and worker](../src/commerce_shipping/app.py), [transport/storage](../src/commerce_shipping/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

| Source | Destination | Implementing method | Behavior |
|---|---|---|---|
| `event.order_id` | `carrier.reference` | `Service.consume` | Carrier request correlation |
| `event.delivery_address` | `carrier.address` | `Service.consume` | No format conversion |
| `carrier.tracking_number` | `shipments.tracking_number / shipment event tracking_number` | `Service.consume` | Forwarded unchanged |
| `event.order_id` | `shipment event_id = shipment:{order_id}` | `Service.consume` | Stable publisher event identity |

Delivery instructions are absent from the implemented request mapping and event payloads. An extra request field is not automatically propagated; adding one requires tracing explicit mappings and consumer contracts. Schemas in [openapi.json](openapi.json) describe supported payload shapes; [events.md](events.md) describes MQ payloads.
