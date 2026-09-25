# Debugging and Self-Repair Strategy

When a test fails after an implementation change, do not immediately make another edit.

## 1. Read the failure

Read the complete relevant failure output.

Identify:
- failing test
- exception
- assertion
- stack trace
- expected value
- actual value
- relevant command
- environment information when provided

## 2. Classify the failure

Determine whether it is:
- caused by the new change
- caused by an incorrect assumption
- exposing an existing issue
- caused by unrelated repository behavior
- caused by an environment or dependency problem

## 3. Inspect implementation

Read the implementation involved in the failure and compare it with the issue,
repository conventions, callers, and related implementations.

## 4. Inspect the test

Read the relevant test and determine what behavior it actually establishes.

## 5. Compare expected and actual behavior

Identify the smallest concrete difference between expected and actual behavior.

## 6. Correct the root cause

If the implementation is responsible:
- make the smallest corrective change
- preserve unrelated behavior
- avoid test-specific hacks

## 7. Rerun relevant validation

Run the directly affected test again.

## 8. Iterate deliberately

Only perform another repair cycle when the previous result provides useful new evidence.

## Forbidden debugging strategies

Never:
- delete failing tests
- weaken assertions
- change expected values without evidence
- skip tests to hide failures
- disable validation
- hard-code outputs for a specific test
- modify unrelated code to make a failure disappear

Stop when the relevant behavior is validated, the remaining failure is reasonably
identified as environmental/unrelated, or further changes would be speculative.
