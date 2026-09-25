# Repository Localization Strategy

Use this procedure whenever the issue requires finding unfamiliar code.

## Step 1 — Extract issue signals

Extract:
- error messages
- class names
- function names
- filenames
- API names
- configuration names
- domain concepts
- expected behavior
- observed behavior

Separate explicit evidence from assumptions.

## Step 2 — Semantic search

Use the competition-provided semantic code search capability when the exact
implementation location is unknown.

## Step 3 — Identify candidates

Identify candidate:
- files
- classes
- functions
- tests

Do not assume the first search result is correct.

## Step 4 — Inspect neighbors

Use code-neighbor information to understand callers, callees, dependencies,
and related symbols.

## Step 5 — Inspect subgraph when necessary

Use code-subgraph information only when broader relationships are necessary.

## Step 6 — Read minimal context

Read only the files and regions required to understand the candidate.

## Step 7 — Inspect tests

Find and inspect tests related to the candidate implementation.

## Step 8 — Form an implementation hypothesis

Determine:
1. Where the problem originates.
2. Why the current implementation produces the observed behavior.
3. What behavior should change.
4. Which files should change.
5. Which tests should validate the change.

Prioritize precision over exhaustive repository exploration.
