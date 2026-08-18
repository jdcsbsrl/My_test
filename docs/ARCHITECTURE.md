---
title: Test ERP Architecture
purpose: 项目模块、运行时路径和 Agent 编排架构
version: 3.0.0
updated: 2026-08-18
authority: 参考架构
---

# Test ERP Architecture

## Overview

Test ERP separates test-case generation from test execution. The orchestration layer coordinates generation, audit, workflow state, reporting, and recovery.

## Main modules

### `modules/trae_test`

Generates and manages standardized 15-field test cases.

- `utils/test_case_generator.py`: test-case generation.
- `utils/test_case_strategy.py`: scoring, optimization, and regeneration.
- `utils/knowledge_retriever.py`: the only agent-facing knowledge-base API.
- `utils/file_splitter.py` and `utils/index_builder_v3.py`: chunking and index construction.
- `orchestrator/`: workflow coordination and audit gateway.
- `orchestrator/audit_agent_enhanced.py`: blocking quality and policy audit.

### `modules/auto_test`

Executes automated tests in approved UAT or internal test environments.

- `core/`: environment, logging, authentication, data factory, and lifecycle management.
- `drivers/`: browser and HTTP drivers.
- `pages/`: UI page objects.
- `api/`: API clients and resources.
- `facades/`: business-level test operations.
- `tests/`: unit, integration, regression, and UI tests.

## Knowledge-base architecture

Agents access knowledge through `KnowledgeRetriever`. The physical knowledge base is local and should not be committed with business-sensitive source data. Runtime artifacts use `modules/trae_test/utils/runtime_paths.py` and `runtime_dir()`.

```text
assets/knowledge_base/
├── data/original/   source documents
├── data/chunks/     semantic chunks for large documents
├── index/global/    global metadata index
├── index/inverted/  keyword index
└── metadata/        file registry and retrieval metadata
```

## Workflow

```text
requirement
  -> scenario analysis
  -> 15-field test-case generation
  -> AuditAgent gateway
  -> workflow state transition
  -> automated execution
  -> result collection and report
```

Audit failures block delivery. Test data is created through `TestDataFactory` and cleaned up through `TestDataLifecycleManager`, including dependency-aware cascading cleanup.

## Quality and recovery

- `AuditAgent` validates test cases, code, environment, and deliverables before handoff.
- `TestCaseScoreEngine` evaluates generated cases across five dimensions.
- `TestCaseRegenerationLoop` retries low-quality cases with a circuit breaker.
- Self-healing and locator recovery belong in the execution layer and must remain observable through reports and logs.

## CI boundaries

CI runs unit, integration, and selected UI/regression suites separately. Test collection is configured in `pytest.ini`; CI commands must remain explicit so script-style E2E checks are not mistaken for pytest tests. Deployment is currently represented by `deploy-test-stub` until a real test-environment deployment is configured.

## Data and security boundaries

- Run automation only against approved UAT/internal test environments.
- Keep credentials, tokens, raw business knowledge, and test data outside Git.
- Use relative workspace output paths or `WORKSPACE_OUTPUT_DIR`; never hard-code a developer machine path.
