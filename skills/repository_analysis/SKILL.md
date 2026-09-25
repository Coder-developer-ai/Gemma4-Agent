---
name: repository_analysis
description: Evidence-based localization of software-engineering issues in unfamiliar repositories.
---

# Repository Analysis Skill

Use this skill to localize the implementation relevant to an issue before editing.

## Workflow

1. Parse the issue.
2. Extract distinctive search terms.
3. Search the repository.
4. Identify candidate files and symbols.
5. Inspect callers, callees, and dependencies.
6. Inspect a broader subgraph only when necessary.
7. Read the smallest useful source context.
8. Inspect relevant tests.
9. Produce a concise implementation hypothesis.

## Principles

- Evidence-based localization.
- Minimal context gathering.
- Avoid unnecessary repository-wide exploration.
- Identify callers and dependencies.
- Check tests before editing.

This skill does not perform the actual patch.
