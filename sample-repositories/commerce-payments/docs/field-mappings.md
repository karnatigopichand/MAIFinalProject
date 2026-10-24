# commerce-payments: field lineage

Reviewed against [authorize](../src/commerce_payments/service.py), [HTTP handler and worker](../src/commerce_payments/app.py), [transport/storage](../src/commerce_payments/runtime.py), and [local](../config/local.json)/[development](../config/development.json) configuration. Review date: October 24, 2026. These are implementation-reviewed documents, not output from a documentation-summary generator. See [source-review.json](source-review.json) for reviewed file hashes; updates require code review.

| Source | Destination | Implementing method | Behavior |
|---|---|---|---|
| `amount_cents` | `provider.amount` | `Service.authorize` | Integer cents; no division |
| `currency` | `provider.currency` | `Service.authorize` | Exactly USD required |
| `payment_token` | `provider.token` | `Service.authorize` | Not persisted |
| `provider.authorization_id` | `authorizations.authorization_id` | `Service.authorize` | Required on authorized response |

Delivery instructions are absent from the implemented request mapping and event payloads. An extra request field is not automatically propagated; adding one requires tracing explicit mappings and consumer contracts. Schemas in [openapi.json](openapi.json) describe supported payload shapes; [events.md](events.md) describes MQ payloads.
