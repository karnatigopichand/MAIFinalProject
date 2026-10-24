# INVENTORY-TD-001: mapping-validation

- Status: open
- Components: src/commerce_inventory/service.py
- Implementation estimate hours: 1
- Testing estimate hours: 1
- Estimate basis: illustrative generated estimate; requires team review
- Relevant tests: tests/test_service.py

## Problem
Add stricter input/schema validation for the implemented field mappings without changing their names.

## Proposed change
Implement the improvement in the existing service and preserve its public contracts.

## Acceptance criteria
Add focused regression coverage and retain the current success and rejection behavior.
