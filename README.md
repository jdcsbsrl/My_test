# Test ERP

An integrated ERP test platform with test-case generation (`trae_test`) and automated execution (`auto_test`).

## Project layout

```text
test_erp/
├── modules/
│   ├── trae_test/          test-case generation, knowledge retrieval, orchestration
│   └── auto_test/          browser/API automation and regression tests
├── tests/
│   ├── unit/               unit tests
│   └── integration/        integration tests
├── assets/knowledge_base/  local knowledge base; business data stays out of Git
├── configs/                environment and test configuration examples
├── tools/                  project utilities and CLIs
└── docs/                   architecture, workflow, and project rules
```

## Quick start

```bash
pip install -e .
cp .env.example .env
python tools/project_structure_auditor.py
```

Run the default test collection or a focused suite:

```bash
pytest --collect-only
pytest tests/unit tests/integration
```

## Test-case generation

```bash
python tools/case_generator_cli.py list-templates
python tools/case_generator_cli.py generate --module "基础资料" --function "物料新增" --priority P1 --requirement-file data/private/requirement.txt
```

Generated cases follow the project's 15-field standard and pass through the AuditAgent gateway before delivery.

## Knowledge base

Agents must access business knowledge through `KnowledgeRetriever`; do not read raw knowledge JSON files directly. See `docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md` and `docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md`.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Workflow](docs/WORKFLOW.md)
- [Test-case workflow](docs/TRAE_TEST_WORKFLOW.md)
- [Automation workflow](docs/AUTO_TEST_WORKFLOW.md)
- [Project rules](docs/PROJECT_RULES.md)
- [Sales-volume regression (1003420)](docs/SALES_VOLUME_REGRESSION_1003420.md)
- [Local knowledge-base guide](docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md)
- [Agent workspace instructions](AGENTS.md)

## Safety boundaries

Run routine automated regression only against approved TEST/UAT endpoints. Production access is denied by default; a production data check requires an explicit request in the current task and must use an approved dedicated read-only workflow, not the regular regression entry. The regression entry accepts only `test` and `uat`; see [project rules](docs/PROJECT_RULES.md). Keep credentials, tokens, raw business knowledge, and environment-specific test data out of Git.
