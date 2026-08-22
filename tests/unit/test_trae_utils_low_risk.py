import json
from pathlib import Path

import pytest

from modules.trae_test.utils import dir_validator
from modules.trae_test.utils.business_rule_parser import BusinessRuleParser, parse_knowledge
from modules.trae_test.utils.excel_generator import ExcelGenerator
from modules.trae_test.utils.metadata_manager import MetadataManager
from modules.trae_test.utils.template_builder import ALL_FIELDS, ensure_template, get_default_template_path
from modules.trae_test.utils.test_case_generator import TestCaseGenerator
from modules.trae_test.utils.workspace_manager import WorkspaceManager


pytestmark = pytest.mark.unit


def _case(**overrides):
    case = ExcelGenerator.create_empty_case(case_name="case name")
    case.update(overrides)
    return case


def test_directory_matching_uses_leaf_menu_to_resolve_full_hierarchy():
    hierarchy = {"产品": {"产品中心": ["主SKU", "库存SKU"]}}
    assert TestCaseGenerator._match_case_directory("库存SKU 批量加入采购计划", hierarchy) == "产品 - 产品中心 - 库存SKU"


class TestBusinessRuleParser:
    def test_parse_dict_extracts_pages_constraints_operations_and_flows(self):
        parser = BusinessRuleParser()
        knowledge = {
            "module": "Sales",
            "pages": [
                {
                    "path": "/sales/orders",
                    "test_points": ["create order"],
                    "business_rules": ["create order requires customer"],
                }
            ],
            "core_constraints": [{"name": "amount", "rule": "amount > 0", "description": "positive", "impact": "order"}],
            "batch_operations": {"pending": ["approve", "ignore"]},
            "forward_sales_flow": {
                "step_1": {
                    "name": "create",
                    "core_operations": [{"operation": "submit", "path": "/sales/submit", "description": "submit order"}],
                }
            },
            "reverse_return_flow": {"steps": ["return"], "constraints": ["paid"], "prerequisite": "shipped"},
            "refund_flow": {"steps": ["refund"], "prerequisites": ["approved"]},
            "stages": [{"name": "stage one", "steps": [{"module": "sales", "action": "check"}], "verification": []}],
            "learned_requirements": [{"id": "REQ-1", "title": "learned title", "description": "learned desc"}],
        }

        scenarios = parser.parse_knowledge(knowledge)

        sources = {scenario.source for scenario in scenarios}
        assert {
            "test_points",
            "business_rules",
            "core_constraints",
            "batch_operations",
            "forward_sales_flow",
            "reverse_return_flow",
            "refund_flow",
            "stages",
            "learned_requirements",
        }.issubset(sources)
        assert any(s.operation == "submit" and s.page_path == "/sales/submit" for s in scenarios)
        assert sum(1 for s in scenarios if s.source == "core_constraints") == 3

    def test_parse_list_supports_rule_title_snippet_content_and_skips_non_dict(self):
        parser = BusinessRuleParser()

        scenarios = parser.parse_knowledge(
            [
                {"module": "M1", "rule": "must be approved"},
                {"file_title": "M2", "title": "title", "description": "description"},
                {"source_file": "M3", "snippet": "snippet"},
                {"module": "M4", "content": {"key": "value"}},
                "ignored",
                {"module": "empty"},
            ]
        )

        assert [s.test_point for s in scenarios[:3]] == ["must be approved", "title", "snippet"]
        assert scenarios[0].business_rule == "must be approved"
        assert scenarios[1].business_rule == "description"
        assert scenarios[3].source == "list_result"
        assert len(scenarios) == 5

    def test_parse_knowledge_convenience_function_resets_default_parser(self):
        first = parse_knowledge({"pages": [{"path": "a", "test_points": ["one"]}]})
        second = parse_knowledge({"pages": [{"path": "b", "test_points": ["two"]}]})

        assert len(first) == 1
        assert len(second) == 1
        assert second[0].test_point == "two"


class TestMetadataManager:
    def test_scan_registers_json_and_md_files_with_declared_tags_and_chunks(self, tmp_path):
        kb_dir = tmp_path / "kb"
        original = kb_dir / "data" / "original"
        chunks = kb_dir / "data" / "chunks"
        original.mkdir(parents=True)
        chunks.mkdir(parents=True)
        (original / "Alpha File.json").write_text(json.dumps({"tags": ["tag-a", "tag-b"]}), encoding="utf-8")
        (original / "Notes.md").write_text("# notes", encoding="utf-8")
        (chunks / "alpha_file_chunk_001.json").write_text("{}", encoding="utf-8")

        manager = MetadataManager(str(kb_dir))
        result = manager.scan_and_register_all(str(original))
        registry = manager.load_registry()

        assert result["success"] is True
        assert result["registered_files"] == 2
        assert registry["files"]["alpha_file"]["chunk_count"] == 1
        assert set(registry["files"]["alpha_file"]["tags"]) == {"tag-a", "tag-b"}
        assert registry["tags"]["tag-a"] == ["alpha_file"]

    def test_get_and_update_file_keep_reverse_tag_index_in_sync(self, tmp_path):
        manager = MetadataManager(str(tmp_path / "kb"))
        registry = {
            "version": "3.0",
            "generated_at": "now",
            "files": {"file1": {"file_id": "file1", "tags": ["old"]}},
            "tags": {"old": ["file1"]},
        }
        Path(manager.registry_path).write_text(json.dumps(registry), encoding="utf-8")

        assert manager.get_file_by_id("file1")["tags"] == ["old"]
        assert manager.update_file("file1", {"tags": ["new", "old"]}) is True

        assert manager.get_files_by_tag("new")[0]["file_id"] == "file1"
        assert manager.get_files_by_tag("missing") == []
        assert manager.update_file("missing", {"tags": []}) is False

    def test_declared_tags_ignore_invalid_json_and_non_list_tags(self, tmp_path):
        invalid = tmp_path / "bad.json"
        invalid.write_text("{not json", encoding="utf-8")
        wrong_shape = tmp_path / "wrong.json"
        wrong_shape.write_text(json.dumps({"tags": "not-list"}), encoding="utf-8")

        assert MetadataManager._extract_declared_tags(str(invalid)) == []
        assert MetadataManager._extract_declared_tags(str(wrong_shape)) == []
        assert MetadataManager._extract_declared_tags(str(tmp_path / "note.md")) == []


class TestDirValidator:
    def test_validate_directory_accepts_allowed_hierarchy_and_lists_top_levels(self, monkeypatch):
        hierarchy = {"Top": {"Second": ["Third"]}}
        monkeypatch.setattr(dir_validator, "_load_module_hierarchy", lambda: hierarchy)

        assert dir_validator.list_allowed_top_levels() == ["Top"]
        assert dir_validator.validate_directory("Top - Second - Third") == (True, "")

    def test_validate_directory_strict_and_non_strict_failures(self, monkeypatch):
        monkeypatch.setattr(dir_validator, "_load_module_hierarchy", lambda: {"Top": {"Second": ["Third"]}})

        assert dir_validator.validate_directory(None, strict=True)[0] is False
        assert dir_validator.validate_directory("", strict=False)[0] is True
        assert dir_validator.validate_directory("Top-Second", strict=True)[0] is False
        assert dir_validator.validate_directory("Bad - Second - Third", strict=False)[0] is True

        with pytest.raises(ValueError):
            dir_validator.assert_directory("Bad - Second - Third")

    def test_fix_directory_normalizes_separators_and_uses_closest_match(self, monkeypatch):
        monkeypatch.setattr(dir_validator, "_load_module_hierarchy", lambda: {"SalesModule": {"OrderManage": ["ListPage"]}})

        fixed, fixes = dir_validator.fix_directory("Sales - Order - List")

        assert fixed == "SalesModule - OrderManage - ListPage"
        assert fixes

    def test_find_closest_directory_returns_none_for_invalid_shape_or_missing_hierarchy(self, monkeypatch):
        monkeypatch.setattr(dir_validator, "_load_module_hierarchy", lambda: {})
        assert dir_validator.find_closest_directory("Top - Second - Third") is None

        monkeypatch.setattr(dir_validator, "_load_module_hierarchy", lambda: {"Top": {"Second": ["Third"]}})
        assert dir_validator.find_closest_directory("Top - Second") is None


class TestWorkspaceManager:
    def test_generate_filename_sanitizes_and_truncates(self, tmp_path):
        manager = WorkspaceManager(str(tmp_path))

        filename = manager.generate_filename(" name/with:bad*chars ", "REQ/1")
        long_name = manager.generate_filename("x" * 300)

        assert filename.endswith(".xlsx")
        assert "/" not in filename
        assert ":" not in filename
        assert len(long_name) <= 205

    def test_generate_file_path_ignores_deprecated_sub_directory(self, tmp_path):
        manager = WorkspaceManager(str(tmp_path))

        path = manager.generate_file_path("demo", requirement_id="REQ-1", date_str="20260727", sub_dir="draft")

        assert path.parent == tmp_path / "workspace" / "20260727"
        assert path.parent.exists()
        assert path.name.endswith(".xlsx")

    def test_validate_file_path_and_listing_helpers(self, tmp_path):
        manager = WorkspaceManager(str(tmp_path))
        valid_path = manager.generate_file_path("demo", date_str="20260727")
        valid_path.write_text("placeholder", encoding="utf-8")
        invalid_ext = manager.get_date_dir("20260727") / "bad.txt"
        invalid_ext.write_text("bad", encoding="utf-8")
        outside = tmp_path / "outside.xlsx"
        outside.write_text("outside", encoding="utf-8")

        assert manager.validate_file_path(str(valid_path))[0] is True
        assert manager.validate_file_path(str(invalid_ext))[0] is False
        assert manager.validate_file_path(str(outside))[0] is False
        assert manager.list_date_dirs() == ["20260727"]
        assert manager.list_files_in_date_dir("20260727") == [valid_path]

    def test_find_project_root_prefers_agents_marker(self, tmp_path):
        root = tmp_path / "project"
        nested = root / "a" / "b"
        nested.mkdir(parents=True)
        (root / "AGENTS.md").write_text("rules", encoding="utf-8")
        marker_file = nested / "module.py"
        marker_file.write_text("", encoding="utf-8")

        assert WorkspaceManager._find_project_root(str(marker_file)) == str(root)


class TestTemplateBuilderAndExcelGenerator:
    def test_fixed_redacted_samples_cover_login_query_export_cleanup_and_schema(self):
        samples_dir = Path(get_default_template_path()).parent / "samples"
        expected = {"login_case.json", "query_case.json", "export_case.json", "cleanup_case.json", "schema_boundary_cases.json"}
        assert {path.name for path in samples_dir.glob("*.json")} >= expected

        for name in sorted(expected - {"schema_boundary_cases.json"}):
            case = json.loads((samples_dir / name).read_text(encoding="utf-8"))
            ExcelGenerator._validate_test_cases([case])
            assert set(case).issuperset(ALL_FIELDS)
            assert "REQ-FIXTURE-" in json.dumps(case, ensure_ascii=False)

        schema = json.loads((samples_dir.parent / "schema" / "test_case_schema.json").read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False
        assert schema["required"] == ALL_FIELDS

    def test_schema_boundary_samples_reject_flat_runtime_and_unknown_fields(self):
        samples_path = Path(get_default_template_path()).parent / "samples" / "schema_boundary_cases.json"
        samples = json.loads(samples_path.read_text(encoding="utf-8"))
        valid = samples["valid_runtime_case"]
        ExcelGenerator._validate_test_cases([valid])

        flat_runtime = _case(**{"最终评分": 101})
        with pytest.raises(ValueError, match="未定义字段"):
            ExcelGenerator._validate_test_cases([flat_runtime])

        unknown_runtime = dict(valid)
        unknown_runtime["_runtime_unknown"] = True
        with pytest.raises(ValueError, match="未定义字段"):
            ExcelGenerator._validate_test_cases([unknown_runtime])

    def test_export_refuses_to_write_under_fixtures(self):
        fixture_output = Path(get_default_template_path()).parent / "samples" / "must-not-overwrite.xlsx"
        with pytest.raises(ValueError, match="fixtures目录"):
            ExcelGenerator.generate_excel([_case()], requirement_name="fixture", output_path=fixture_output)

    def test_ensure_template_reads_fixed_workbook_without_creating_files(self, tmp_path):
        template_path = tmp_path / "template.xlsx"

        with pytest.raises(ValueError, match="唯一来源"):
            ensure_template(str(template_path))
        assert not template_path.exists()
        from openpyxl import load_workbook

        result = ensure_template()
        wb = load_workbook(result, read_only=True)
        assert [cell.value for cell in wb["测试用例"][1]] == ALL_FIELDS
        wb.close()
        assert ExcelGenerator.validate_excel(result) == (False, "Excel文件没有数据行")

    def test_default_template_path_is_project_fixture(self):
        path = Path(get_default_template_path())
        assert path.parent.parent.name == "fixtures"
        assert path.name == "测试用例模板.xlsx"

    def test_generate_from_fixed_template_writes_only_standard_fields_and_validation_passes(self, tmp_path):
        output = tmp_path / "cases.xlsx"
        cases = [_case(**{"质量评分": 91})]

        path = ExcelGenerator.generate_excel(cases, requirement_name="demo", output_path=output)

        assert path == str(output)
        assert ExcelGenerator.validate_excel(path) == (True, "")
        rows = ExcelGenerator.read_excel_worksheet(path)
        assert rows[0]["case_name"] == "case name"

    def test_generate_excel_defaults_to_date_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.trae_test.utils.excel_generator.workspace_manager", WorkspaceManager(str(tmp_path)))

        path = Path(ExcelGenerator.generate_excel([_case()], requirement_name="demo", date_str="20260727"))

        assert path.parent == tmp_path / "workspace" / "20260727"
        assert path.name == "需求demo.xlsx"
        assert ExcelGenerator.validate_excel(str(path)) == (True, "")

    def test_execute_accepts_json_string_and_data_wrapper(self, tmp_path, monkeypatch):
        output = tmp_path / "execute.xlsx"
        monkeypatch.setattr(ExcelGenerator, "generate_excel", lambda test_cases, **kwargs: str(output))
        payload = json.dumps({"data": [_case()]}, ensure_ascii=False)

        assert ExcelGenerator.execute(payload, requirement_name="demo") == str(output)

    def test_validate_test_cases_rejects_implicit_defaults_and_extra_fields(self):
        case = _case()
        case.pop("质量评分")

        with pytest.raises(ValueError, match="质量评分"):
            ExcelGenerator._validate_test_cases([case])

        with pytest.raises(ValueError, match="不允许"):
            ExcelGenerator._validate_test_cases([_case()], extra_fields=["custom"])

    def test_validate_test_cases_rejects_unknown_fields_and_types(self):
        unknown = _case(unknown_field="value")
        with pytest.raises(ValueError, match="未定义字段"):
            ExcelGenerator._validate_test_cases([unknown])

        wrong_score = _case(**{"质量评分": "91"})
        with pytest.raises(ValueError, match="质量评分"):
            ExcelGenerator._validate_test_cases([wrong_score])

        legacy_runtime = _case(**{"最终评分": 91})
        with pytest.raises(ValueError, match="未定义字段"):
            ExcelGenerator._validate_test_cases([legacy_runtime])

    def test_runtime_fields_are_nested_and_never_exported_as_columns(self):
        case = _case(**{
            "_runtime_quality": {
                "final_score": 90,
                "score_threshold": 85.0,
                "needs_human_review": False,
                "final_audit_passed": True,
            },
            "_runtime_quality_version": "1.0",
        })
        ExcelGenerator._validate_test_cases([case])
        assert list(case)[:15] == ALL_FIELDS

    def test_validate_test_cases_rejects_empty_missing_field_and_empty_name(self):
        with pytest.raises(ValueError):
            ExcelGenerator._validate_test_cases([])

        missing = _case()
        missing.pop(ExcelGenerator.STANDARD_FIELDS[0])
        with pytest.raises(ValueError):
            ExcelGenerator._validate_test_cases([missing])

        empty_name = _case()
        empty_name[ExcelGenerator.STANDARD_FIELDS[1]] = " "
        with pytest.raises(ValueError):
            ExcelGenerator._validate_test_cases([empty_name])

    def test_export_cases_handles_empty_success_file_size_failure_and_single_case(self, tmp_path, monkeypatch):
        assert ExcelGenerator.export_cases([], str(tmp_path / "empty.xlsx"))["success"] is False

        output = tmp_path / "export.xlsx"
        result = ExcelGenerator.export_cases([_case()], str(output))
        assert result["success"] is True
        assert result["case_count"] == 1

        monkeypatch.setattr(ExcelGenerator, "MAX_FILE_SIZE", 1)
        too_large = ExcelGenerator.export_single_case(_case(), str(tmp_path / "too_large.xlsx"))
        assert too_large["success"] is False

    def test_batch_export_splits_cases(self, tmp_path):
        results = ExcelGenerator.batch_export([_case(**{"用例名称": f"case {i}"}) for i in range(3)], str(tmp_path), batch_size=2)

        assert [result["cases_in_batch"] for result in results] == [2, 1]
        assert all(result["success"] for result in results)
