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
├── docs/                   architecture and workflow documentation
└── .trae/                  agent rules and configuration
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
python tools/case_generator_cli.py generate --module "基础资料" --function "物料新增" --priority P1
```

Generated cases follow the project's 15-field standard and pass through the AuditAgent gateway before delivery.

## Knowledge base

Agents must access business knowledge through `KnowledgeRetriever`; do not read raw knowledge JSON files directly. See `docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md` and `docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md`.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Workflow](docs/WORKFLOW.md)
- [Test-case workflow](docs/TRAE_TEST_WORKFLOW.md)
- [Automation workflow](docs/AUTO_TEST_WORKFLOW.md)
- [Local knowledge-base guide](docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md)
- [Agent workspace instructions](AGENTS.md)

## Safety boundaries

Run automated tests only in approved UAT or internal test environments. Keep credentials, tokens, raw business knowledge, and environment-specific test data out of Git.
