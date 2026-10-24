# INVENTORY-TD-003: log-correlation

- Status: open
- Components: src/commerce_inventory/runtime.py; src/commerce_inventory/app.py
- Implementation estimate hours: 1
- Testing estimate hours: 1
- Estimate basis: illustrative estimate; requires team review
- Relevant tests: tests/test_transport.py

## Problem
Propagate the same request/correlation ID through inbound HTTP, downstream HTTP, MQ headers and structured logs. Current outbound IDs are independent; preserve JSON log formatting.

## Proposed change
Improve the existing JSON logging implementation without logging request bodies or credentials.

## Acceptance criteria
JSON remains parseable and service/env/status/timestamp fields remain available for Datadog ingestion.
