# TASK-999: Test Re-Review Loop

## Objective
Test the orchestrator's re-review loop by implementing a deliberately imperfect feature.

## Requirements
1. Add a new function in `src/utils/test_helpers.py` that:
   - Has no type hints
   - Has no docstring
   - Uses global variables
   - Has no tests

This should trigger Qwen to return `CHANGES REQUIRED` with specific findings.

## Acceptance Criteria
- Function exists but needs improvement
- Review identifies quality issues
- Orchestrator enters fix loop
- Fixes are applied in round 2
- Final review passes as APPROVED

## Notes
This is a test task - do not merge to main. Use for testing the re-review workflow only.
