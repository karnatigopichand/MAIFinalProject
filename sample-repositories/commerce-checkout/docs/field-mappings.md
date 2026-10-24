# commerce-checkout: field lineage

Reviewed against [checkout](../src/commerce_checkout/service.py), [HTTP handler and worker](../src/commerce_checkout/app.py), [transport/storage](../src/commerce_checkout/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

| Source | Destination | Implementing method | Behavior |
|---|---|---|---|
| `request.checkout_id` | `orders.order_id` | `Service.checkout` | Identity reused for downstream retries |
| `request.cart.items` | `orders.items` | `Service.checkout` | Array forwarded unchanged |
| `request.delivery.address` | `orders.delivery_address` | `Service.checkout` | No address transformation |
| `request.currency (absent)` | `orders.currency = USD` | `Service.checkout` | Default on missing key only |
| `orders HTTP response` | `checkouts payload / HTTP response` | `Service.checkout` | Stored/returned unchanged |

Delivery instructions are absent from the implemented request mapping and event payloads. An extra request field is not automatically propagated; adding one requires tracing explicit mappings and consumer contracts. Schemas in [openapi.json](openapi.json) describe supported payload shapes; [events.md](events.md) describes MQ payloads.
