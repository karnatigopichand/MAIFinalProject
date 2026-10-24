# INVENTORY-TD-004: log-observability

- Status: open
- Components: src/commerce_inventory/runtime.py; src/commerce_inventory/app.py
- Implementation estimate hours: 1
- Testing estimate hours: 1
- Estimate basis: illustrative estimate; requires team review
- Relevant tests: tests/test_transport.py

## Problem
Add duration/error metrics and configurable JSON log levels with regression tests for sensitive-field redaction. Do not introduce plaintext logging.

## Proposed change
Improve the existing JSON logging implementation without logging request bodies or credentials.

## Acceptance criteria
JSON remains parseable and service/env/status/timestamp fields remain available for Datadog ingestion.
