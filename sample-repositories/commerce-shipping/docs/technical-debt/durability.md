# SHIPPING-TD-002: durability

- Status: open
- Components: src/commerce_shipping/service.py
- Implementation estimate hours: 5
- Testing estimate hours: 1
- Estimate basis: illustrative generated estimate; requires team review
- Relevant tests: tests/test_service.py

## Problem
Introduce transaction boundaries and durable event publication appropriate to this service; current storage and events are separate writes.

## Proposed change
Implement the improvement in the existing service and preserve its public contracts.

## Acceptance criteria
Add focused regression coverage and retain the current success and rejection behavior.
