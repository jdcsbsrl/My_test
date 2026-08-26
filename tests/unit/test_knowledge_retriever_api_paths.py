import gzip
import json
import time
from types import SimpleNamespace

import pytest

from modules.trae_test.utils import knowledge_retriever
from modules.trae_test.utils.knowledge_retriever import API_VERSION, KnowledgeRetriever

pytestmark = pytest.mark.unit


class FakeMetadataRepository:
    def __init__(self):
        self.files_by_tag = {}
        self.rule_files = []
        self.registry = {"files": {}}
        self.cleared = False

    def load_registry(self):
        return None

    def get_registry(self):
        return self.registry

    def ensure_rules_loaded(self):
        return None

    def get_rule_file_index(self):
        return self.rule_files

    def get_file_by_id(self, file_id):
        return self.registry.get("files", {}).get(file_id)

    def get_files_by_tag(self, tag):
        return self.files_by_tag.get(tag, [])

    def search_by_tags(self, *tags):
        results = []
        for tag in tags:
            results.extend(self.files_by_tag.get(tag, []))
        return results

    def list_available_files(self):
        return [info["title"] for info in self.registry.get("files", {}).values()]

    def get_registry_stats(self):
        return {"total_files": len(self.registry.get("files", {}))}

    def clear_rule_index(self):
        self.cleared = True


class FakeFileRepository:
    def __init__(self):
        self.contents = {}
        self.chunks = {}
        self.chunk_by_id = {}
        self.aggregated = {}
        self.cleared = False

    def load_file(self, file_info):
        return self.contents.get(file_info["file_id"])

    def get_all_chunks(self, file_title):
        return self.chunks.get(file_title, [])

    def get_chunk_by_id(self, file_title, chunk_index):
        return self.chunk_by_id.get((file_title, chunk_index))

    def load_aggregated_data(self, file_title):
        return self.aggregated.get(file_title)

    def clear_cache(self):
        self.cleared = True

    def get_file_cache_size(self):
        return len(self.contents)


class FakeRuleExtractor:
    def extract_rules(self, content):
        return content.get("rules", [])

    def match_keyword_in_rule(self, rule, keyword):
        haystack = json.dumps(rule, ensure_ascii=False).lower()
        return keyword.lower() in haystack


class FakeFileManager:
    def add_file(self, file_path, auto_process, clear_caches_callback, load_registry_callback):
        clear_caches_callback()
        load_registry_callback()
        return {"success": True, "op": "add", "file_path": file_path, "auto_process": auto_process}

    def update_file(self, file_path, auto_process, clear_caches_callback, load_registry_callback):
        clear_caches_callback()
        load_registry_callback()
        return {"success": True, "op": "update", "file_path": file_path, "auto_process": auto_process}


def _retriever(tmp_path):
    kb_dir = tmp_path / "kb"
    for directory in (
        kb_dir / "data" / "original",
        kb_dir / "data" / "chunks",
        kb_dir / "index" / "global",
        kb_dir / "index" / "inverted",
        kb_dir / "metadata",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    retriever = KnowledgeRetriever.__new__(KnowledgeRetriever)
    retriever.knowledge_base_dir = str(kb_dir)
    retriever.data_dir = str(kb_dir / "data")
    retriever.original_dir = str(kb_dir / "data" / "original")
    retriever.chunks_dir = str(kb_dir / "data" / "chunks")
    retriever.index_dir = str(kb_dir / "index")
    retriever.metadata_dir = str(kb_dir / "metadata")
    retriever.registry_path = str(kb_dir / "metadata" / "file_registry.json")
    retriever._file_repository = FakeFileRepository()
    retriever._metadata_repository = FakeMetadataRepository()
    retriever._rule_extractor = FakeRuleExtractor()
    retriever._file_manager = FakeFileManager()
    retriever._registry = {"files": {}}
    retriever._file_cache = {"old": "value"}
    retriever._index_cache = {}
    retriever._rule_file_index = []
    retriever._rules_loaded = False
    retriever._db_enabled = False
    retriever._inverted_index_loaded = False
    retriever._prefix_index = {}
    retriever._pages_cache = None
    retriever._registry_last_loaded = time.time()
    return retriever, kb_dir


def test_single_and_multiple_file_search_helpers(tmp_path):
    retriever, _ = _retriever(tmp_path)
    file_info = {"file_id": "file1", "title": "Wanted Spec", "classification": "docs"}
    retriever._metadata_repository.files_by_tag = {"tag-a": [file_info], "tag-b": [file_info]}
    retriever._file_repository.contents["file1"] = {"payload": 1}

    assert retriever._get_files_by_tag("tag-a") == [file_info]
    assert retriever._get_file_by_id("missing") is None
    assert retriever._search_single_file("tag-a", title_filter=lambda title: "Wanted" in title) == {"payload": 1}
    assert retriever._search_single_file("tag-a", title_filter=lambda title: "Nope" in title) == {}
    assert retriever._search_multiple_files([{"tags": ["tag-a"], "result_key": "one"}]) == {"one": {"payload": 1}}


def test_search_module_pages_rules_and_requirements(tmp_path, monkeypatch):
    retriever, _ = _retriever(tmp_path)
    module_info = {"file_id": "module", "title": "Module", "classification": "sales"}
    rule_info = {"file_id": "rules", "title": "Order Rules", "classification": "sales"}
    req_info = {"file_id": "requirements", "title": "需求 file", "classification": "rules"}
    retriever._metadata_repository.files_by_tag = {
        "custom-module": [module_info],
        "需求清单": [req_info],
        "业务规则": [req_info],
    }
    retriever._metadata_repository.rule_files = [rule_info]
    retriever._file_repository.contents.update(
        {
            "module": {"pages": [{"path": "/orders", "name": "Order List"}]},
            "rules": {"rules": [{"rule": "order must be approved"}, "fallback order rule"]},
            "requirements": {
                "requirements_by_module": {
                    "sales": {
                        "items": [
                            {"title": "order export", "description": "download", "comments": ""},
                            {"title": "inventory", "description": "stock", "comments": ""},
                        ]
                    }
                }
            },
        }
    )
    monkeypatch.setattr(knowledge_retriever, "MODULE_TAG_MAP", {"custom-module": ["custom-module"]})
    monkeypatch.setattr(knowledge_retriever, "MODULE_NAMES", ["custom-module"])

    assert retriever.search_module("custom-module")["pages"][0]["name"] == "Order List"
    assert retriever.search_page_info("order")[0]["path"] == "/orders"
    rules = retriever.search_business_rules("order")
    assert [rule["file_id"] for rule in rules] == ["rules", "rules"]
    requirements = retriever.search_requirements(keyword="order", module="sales")
    assert len(requirements) == 1
    assert requirements[0]["title"] == "order export"
    assert retriever.search_requirements(keyword="missing") == []


def test_specialized_search_methods_use_single_and_multiple_file_helpers(tmp_path, monkeypatch):
    retriever, _ = _retriever(tmp_path)
    calls = []

    def fake_single(*tags, title_filter=None):
        calls.append(("single", tags, title_filter))
        return {"tags": tags}

    def fake_multiple(configs):
        calls.append(("multiple", configs))
        return {"combined": True}

    monkeypatch.setattr(retriever, "_search_single_file", fake_single)
    monkeypatch.setattr(retriever, "_search_multiple_files", fake_multiple)

    assert retriever.search_cross_module_flows()
    assert retriever.search_test_template()
    assert retriever.search_defect_spec()
    assert retriever.search_navigation()
    assert retriever.search_automation_spec() == {"combined": True}
    assert len(calls) == 5


def test_index_chunk_cache_file_management_and_stats(tmp_path):
    retriever, kb_dir = _retriever(tmp_path)
    global_index = {"version": "3.0", "files": [{"file_id": "a"}]}
    (kb_dir / "index" / "global" / "global_index.json").write_text(json.dumps(global_index), encoding="utf-8")
    retriever._metadata_repository.registry = {"files": {"a": {"title": "A"}}}
    retriever._file_repository.chunks["A"] = [{"chunk_index": 0}, {"chunk_index": 1}, {"chunk_index": 2}]
    retriever._file_repository.chunk_by_id[("A", 1)] = {"chunk_index": 1}
    retriever._file_repository.aggregated["A"] = {"all": True}

    loaded_index = retriever.get_index()
    assert loaded_index["version"] == global_index["version"]
    assert loaded_index["files"] == global_index["files"]
    assert loaded_index["index_status"] == {
        "valid": False,
        "missing_files": ["A"],
        "stale_files": ["a"],
    }
    assert retriever.list_available_files() == ["A"]
    assert retriever.get_all_chunks("A", max_chunks=2) == [{"chunk_index": 0}, {"chunk_index": 1}]
    assert retriever.get_chunk_by_id("A", 1) == {"chunk_index": 1}
    assert retriever.load_aggregated_data("A") == {"all": True}
    assert retriever.add_file("new.json", auto_process=False)["op"] == "add"
    assert retriever.update_file("new.json", auto_process=True)["op"] == "update"
    stats = retriever.get_retrieval_stats()
    assert stats["api_version"] == API_VERSION
    assert stats["registry_loaded"] is True


def test_get_index_falls_back_to_legacy_and_compatibility_info(tmp_path):
    retriever, kb_dir = _retriever(tmp_path)
    legacy = {"legacy": True}
    (kb_dir / "index.json").write_text(json.dumps(legacy), encoding="utf-8")
    (kb_dir / "data" / "original" / "one.json").write_text("{}", encoding="utf-8")
    retriever._metadata_repository.registry = {"files": {"one": {"title": "One"}}}

    assert retriever.get_index() == legacy
    info = retriever.get_compatibility_info()
    assert info["api_version"] == API_VERSION
    assert info["file_counts"] == {"original_files": 1, "registered_files": 1}
    assert retriever.ensure_compatibility() == info


def test_retrieve_modes_cache_db_fallback_and_batch(tmp_path, monkeypatch):
    retriever, _ = _retriever(tmp_path)
    calls = []
    monkeypatch.setattr(retriever, "search_module", lambda keyword: {"module": keyword})
    monkeypatch.setattr(
        retriever, "search_business_rules", lambda keyword: [] if keyword == "needs-index" else [{"rule": keyword}]
    )
    monkeypatch.setattr(retriever, "search_requirements", lambda keyword="": [])
    monkeypatch.setattr(retriever, "search_by_inverted_index", lambda keyword: [{"chunk_id": keyword}])
    monkeypatch.setattr(
        retriever, "_search_cache", lambda keyword, mode="auto": {"cached": True} if keyword == "cached" else None
    )
    monkeypatch.setattr(retriever, "_search_db", lambda keyword: [{"db": True}] if keyword == "db" else None)
    monkeypatch.setattr(
        retriever, "_set_search_cache", lambda keyword, result, mode="auto": calls.append((keyword, result))
    )
    monkeypatch.setattr(knowledge_retriever, "MODULE_NAMES", ["module"])

    assert retriever.retrieve("") is None
    assert retriever.retrieve("module", mode="module") == {"module": "module"}
    assert retriever.retrieve("unknown", mode="module") is None
    assert retriever.retrieve("abc", mode="rules") == [{"rule": "abc"}]
    assert retriever.retrieve("abc", mode="requirements") == []
    assert retriever.retrieve("cached") == {"cached": True}
    assert retriever.retrieve("db") == [{"db": True}]
    assert retriever.retrieve("needs-index") == [{"chunk_id": "needs-index"}]
    assert retriever.batch_retrieve(["a", "b"], mode="rules") == {"a": [{"rule": "a"}], "b": [{"rule": "b"}]}
    assert ("db", [{"db": True}]) in calls


def test_retrieve_refreshes_stale_registry(tmp_path, monkeypatch):
    retriever, _ = _retriever(tmp_path)
    retriever._registry_last_loaded = 0
    refreshed = []
    monkeypatch.setattr(retriever, "refresh_registry", lambda: refreshed.append(True))
    monkeypatch.setattr(retriever, "search_business_rules", lambda keyword: [{"rule": keyword}])
    monkeypatch.setattr(retriever, "search_requirements", lambda keyword="": [])
    monkeypatch.setattr(retriever, "search_by_inverted_index", lambda keyword: [])
    monkeypatch.setattr(retriever, "_search_cache", lambda keyword, mode="auto": None)
    monkeypatch.setattr(retriever, "_search_db", lambda keyword: None)

    assert retriever.retrieve("abc") == [{"rule": "abc"}]
    assert refreshed == [True]


def test_inverted_index_loads_json_and_compressed_indexes(tmp_path, monkeypatch):
    retriever, kb_dir = _retriever(tmp_path)
    chunk = {
        "metadata": {"module": "sales"},
        "content": {"rule_name": "Order Rule", "rule_description": "A" * 200},
    }
    (kb_dir / "data" / "chunks" / "chunk_file.json").write_text(json.dumps(chunk), encoding="utf-8")
    index = {
        "total_keywords": 2,
        "index": {
            "ORDER": [{"chunk_id": "c1", "weight": 0.9, "field": "content", "source_file": "chunk_file.json"}],
            "OR": [{"chunk_id": "c2", "weight": 0.1, "field": "content", "source_file": "missing.json"}],
        },
    }
    (kb_dir / "index" / "inverted" / "inverted_index.json").write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(
        knowledge_retriever.PathManager, "get_chunks_dir", classmethod(lambda cls: str(kb_dir / "data" / "chunks"))
    )

    results = retriever.search_by_inverted_index("ORDER", top_k=5)

    assert results[0]["chunk_id"] == "c1"
    assert results[0]["metadata"] == {"module": "sales"}
    assert results[0]["snippet"].endswith("...")

    (kb_dir / "index" / "inverted" / "inverted_index.json").unlink()
    retriever._index_cache.clear()
    retriever._inverted_index_loaded = False
    retriever._prefix_index.clear()
    with gzip.open(kb_dir / "index" / "inverted" / "inverted_index.json.gz", "wt", encoding="utf-8") as f:
        json.dump(index, f)
    assert retriever.search_by_inverted_index("ORDER", top_k=1)[0]["chunk_id"] == "c1"


def test_historical_cases_uses_knowledge_base_then_workspace_fallback(tmp_path, monkeypatch):
    retriever, _ = _retriever(tmp_path)
    kb_cases = {
        "requirements": [
            {
                "cases": [
                    {"用例名称": "order case", "用例步骤": "open order", "预期结果": "done"},
                    {"用例名称": "skip", "用例步骤": "none", "预期结果": "none"},
                ]
            }
        ]
    }
    monkeypatch.setattr(retriever, "_search_single_file", lambda *args, **kwargs: kb_cases)
    monkeypatch.setattr(retriever, "_search_workspace_excel", lambda keyword, top_k: [{"case_name": "workspace"}])

    results = retriever.search_historical_cases("order", top_k=2)

    assert results[0]["source"] == "knowledge_base"
    assert results[1]["case_name"] == "workspace"


def test_search_workspace_excel_reads_recent_date_workbooks(tmp_path, monkeypatch):
    from modules.trae_test.utils.excel_generator import ExcelGenerator

    retriever, _ = _retriever(tmp_path)
    date_dir = tmp_path / "workspace" / "20260727"
    date_dir.mkdir(parents=True)
    workbook = date_dir / "cases.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(knowledge_retriever, "find_project_root", lambda start: str(tmp_path))
    monkeypatch.setattr(
        ExcelGenerator,
        "read_excel_worksheet",
        lambda path: [{"case_name": "order case", "steps": "open order", "expected_result": "done"}],
    )

    assert retriever._search_workspace_excel("order", top_k=1)[0]["source"] == "workspace:cases.xlsx"


def test_search_workspace_excel_ignores_legacy_formal_directory(tmp_path, monkeypatch):
    from modules.trae_test.utils.excel_generator import ExcelGenerator

    retriever, _ = _retriever(tmp_path)
    legacy_formal = tmp_path / "workspace" / "20260727" / "formal"
    legacy_formal.mkdir(parents=True)
    workbook = legacy_formal / "legacy.xlsx"
    workbook.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(knowledge_retriever, "find_project_root", lambda start: str(tmp_path))
    monkeypatch.setattr(
        ExcelGenerator,
        "read_excel_worksheet",
        lambda path: [{"case_name": "order legacy", "steps": "open order", "expected_result": "done"}],
    )

    assert retriever._search_workspace_excel("order", top_k=1) == []


def test_search_db_disabled_and_enabled_session_paths(tmp_path, monkeypatch):
    retriever, _ = _retriever(tmp_path)
    assert retriever._search_db("anything") is None

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def options(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.closed = False

        def query(self, model):
            if model is knowledge_retriever.KBRequirement:
                return FakeQuery(
                    [SimpleNamespace(file=SimpleNamespace(title="file"), module="sales", title="req", data={"x": 1})]
                )
            return FakeQuery([])

        def close(self):
            self.closed = True

    monkeypatch.setattr(knowledge_retriever, "get_session", lambda: FakeSession())
    retriever._db_enabled = True

    results = retriever._search_db("req")

    assert results[0]["type"] == "requirement"
