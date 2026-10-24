# commerce-inventory: field lineage

Reviewed against [reserve](../src/commerce_inventory/service.py), [HTTP handler and worker](../src/commerce_inventory/app.py), [transport/storage](../src/commerce_inventory/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

| Source | Destination | Implementing method | Behavior |
|---|---|---|---|
| `items[].sku` | `stock key / reservation.items keys` | `Service.reserve` | Duplicate lines grouped by SKU |
| `sum(items[].quantity)` | `stock.quantity subtraction` | `Service.reserve` | All availability checked before writes |
| `request.quantity` | `stock.quantity` | `Service.seed_stock` | Absolute replacement, not increment |

Delivery instructions are absent from the implemented request mapping and event payloads. An extra request field is not automatically propagated; adding one requires tracing explicit mappings and consumer contracts. Schemas in [openapi.json](openapi.json) describe supported payload shapes; [events.md](events.md) describes MQ payloads.
