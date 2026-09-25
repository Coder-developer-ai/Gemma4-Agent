# Gemma 4 Developer Agent — Submission 1

Submission 1 is a minimal experimental baseline for autonomous software engineering
with Gemma 4.

## Objective

The agent follows:

ISSUE → UNDERSTAND → LOCALIZE → INSPECT → PLAN → EDIT → TEST →
ANALYZE FAILURE → REPAIR IF NECESSARY → VERIFY → SUBMIT PATCH

The target output is a repository patch.

## Model

gemma-4-31b-it-qat-w4a16-ct

## Architecture

- `agent.yaml`: root agent configuration.
- `prompts/system.md`: overall coding workflow.
- `prompts/localization.md`: repository localization strategy.
- `prompts/debugging.md`: test-failure diagnosis and repair.
- `configs/sampling.yaml`: deliberately minimal sampling configuration.
- `sub_agents/analyzer.yaml`: optional schema-gated analyzer placeholder.
- `skills/repository_analysis/SKILL.md`: evidence-based localization skill.
- `skills/repository_analysis/resources/analysis_checklist.md`: lightweight checklist.

## Directory structure

submission/
├── agent.yaml
├── prompts/
│   ├── system.md
│   ├── localization.md
│   └── debugging.md
├── configs/
│   └── sampling.yaml
├── sub_agents/
│   └── analyzer.yaml
├── skills/
│   └── repository_analysis/
│       ├── SKILL.md
│       ├── scripts/
│       └── resources/
│           └── analysis_checklist.md
└── README.md

## Design principles

This baseline avoids:
- custom servers
- databases
- vector stores
- FAISS
- custom embeddings
- custom semantic search
- custom code graphs
- repository-specific paths
- benchmark-specific hard-coded solutions
- credentials

The competition already provides repository-navigation capabilities.

## Testing and debugging

The agent should inspect existing tests, make the smallest required change, run
relevant tests, diagnose failures, repair root causes, verify the final diff, and
submit the patch.

Tests must not be weakened, deleted, disabled, or changed merely to hide failures.

## Known limitations

The exact current generation-parameter schema and optional sub-agent schema should
be validated against the competition-provided `HARNESS_README.md` before adding
fields. Submission 1 intentionally avoids guessing those fields.

This is a baseline experiment, not the final architecture.
