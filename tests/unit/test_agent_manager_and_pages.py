import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.auto_test.pages import base_page as base_page_module
from modules.auto_test.pages.base_page import BasePage
from modules.auto_test.pages.export_page import ExportPage
from modules.auto_test.pages.inventory_export_page import InventoryExportPage
from modules.auto_test.pages.login_page import LoginPage
from modules.trae_test.orchestrator.agent_manager import AgentContext, AgentManager, DomainMetadata


pytestmark = pytest.mark.unit


class FakeRetriever:
    def __init__(self, fail=False):
        self.fail = fail

    def search_by_inverted_index(self, domain_id, top_k=50):
        if self.fail:
            raise RuntimeError("search failed")
        return [{"chunk_id": f"{domain_id}-1"}]


def _manager(tmp_path):
    manager = AgentManager.__new__(AgentManager)
    manager.knowledge_base_dir = str(tmp_path / "kb")
    manager.agents_config_dir = str(tmp_path / "kb" / "agents")
    manager.domains_dir = str(tmp_path / "kb" / "domains")
    manager.domains_metadata_path = str(Path(manager.domains_dir) / "domain_metadata.json")
    manager.retriever = FakeRetriever()
    manager._agent_contexts = {}
    manager._domain_metadata = {}
    manager._domain_cache = {}
    Path(manager.agents_config_dir).mkdir(parents=True, exist_ok=True)
    Path(manager.domains_dir).mkdir(parents=True, exist_ok=True)
    return manager


class TestAgentManagerLowRisk:
    def test_context_and_domain_metadata_to_dict(self):
        context = AgentContext("agent-1")
        context.loaded_domains = ["sales"]
        context.last_access_time = datetime(2026, 7, 27, 1, 2, 3)
        domain = DomainMetadata("sales", description="desc", chunks=["c1"], priority="high", refresh_strategy="hourly")
        domain.access_count = 2
        domain.hit_count = 1

        assert context.to_dict()["last_access_time"] == "2026-07-27T01:02:03"
        assert domain.to_dict()["domain_id"] == "sales"
        assert domain.to_dict()["hit_count"] == 1

    def test_load_and_save_domain_metadata(self, tmp_path):
        manager = _manager(tmp_path)
        payload = {
            "domains": {
                "sales": {
                    "description": "Sales rules",
                    "chunks": ["c1"],
                    "priority": "high",
                    "refresh_strategy": "daily",
                    "access_count": 3,
                    "hit_count": 2,
                }
            }
        }
        Path(manager.domains_metadata_path).write_text(json.dumps(payload), encoding="utf-8")

        manager._load_domain_metadata()
        manager._save_domain_metadata()

        saved = json.loads(Path(manager.domains_metadata_path).read_text(encoding="utf-8"))
        assert manager._domain_metadata["sales"].access_count == 3
        assert saved["domains"]["sales"]["hit_count"] == 2

    def test_load_agent_domains_from_json_and_agents_md(self, tmp_path):
        manager = _manager(tmp_path)
        Path(manager.agents_config_dir, "agent-json.json").write_text(
            json.dumps({"knowledge_domains": ["json-domain"]}), encoding="utf-8"
        )
        Path(manager.agents_config_dir, "agents.md").write_text(
            """
## Agent
agent_id: agent-md
knowledge_domains:
  - domain_id: md-domain
  - domain_id: second-domain
## Next
agent_id: other
""",
            encoding="utf-8",
        )

        assert manager.load_agent_knowledge_domains("agent-json") == ["json-domain"]
        assert manager.load_agent_knowledge_domains("agent-md") == ["md-domain", "second-domain"]
        assert manager.load_agent_knowledge_domains("missing") == []

    def test_add_remove_record_stats_and_initialize(self, tmp_path):
        manager = _manager(tmp_path)
        Path(manager.agents_config_dir, "agent-1.json").write_text(
            json.dumps({"knowledge_domains": ["sales", "missing"]}), encoding="utf-8"
        )

        assert manager.add_domain("sales", description="desc", chunks=["c1"], priority="high")
        assert not manager.add_domain("sales")
        assert manager.preload_domain_knowledge("sales")
        assert "sales" in manager._domain_cache
        manager.record_domain_access("sales", hit=True)
        assert manager.get_domain_stats("sales")["hit_count"] >= 1
        assert manager.initialize_agent("agent-1")
        assert manager.get_agent_context("agent-1").loaded_domains == ["sales"]
        assert manager.remove_domain("sales")
        assert not manager.remove_domain("sales")
        assert manager.get_domain_stats("sales") == {}

    def test_preload_failure_and_unload_unused_domains(self, tmp_path):
        manager = _manager(tmp_path)
        manager._domain_metadata["sales"] = DomainMetadata("sales")
        manager.retriever = FakeRetriever(fail=True)
        assert not manager.preload_domain_knowledge("sales")
        assert not manager.preload_domain_knowledge("missing")

        context = manager.get_agent_context("agent-1")
        context.loaded_domains = ["old", "new"]
        manager._domain_cache["old"] = {"loaded_at": (datetime.now() - timedelta(seconds=20)).isoformat()}
        manager._domain_cache["new"] = {"loaded_at": datetime.now()}

        manager.unload_unused_domains("agent-1", ttl=1)
        manager.unload_unused_domains("missing", ttl=1)

        assert "old" not in manager._domain_cache
        assert context.loaded_domains == ["new"]


class FakeLocator:
    def __init__(self, name="locator", count=1):
        self.name = name
        self._count = count
        self.first = self
        self.calls = []

    def click(self):
        self.calls.append("click")

    def fill(self, value):
        self.calls.append(("fill", value))

    def press_sequentially(self, value, delay=0):
        self.calls.append(("type", value, delay))

    def select_option(self, value):
        self.calls.append(("select", value))

    def wait_for(self, timeout=0):
        self.calls.append(("wait", timeout))

    def text_content(self):
        return "text"

    def get_attribute(self, attribute):
        return f"{attribute}-value"

    def scroll_into_view_if_needed(self):
        self.calls.append("scroll")

    def hover(self):
        self.calls.append("hover")

    def count(self):
        return self._count


class FakePage:
    def __init__(self):
        self.url = "https://example.test/export?sku=1"
        self.locators = {}
        self.calls = []

    def locator(self, selector):
        locator = self.locators.setdefault(selector, FakeLocator(selector))
        self.calls.append(("locator", selector))
        return locator

    def get_by_role(self, role, name=None):
        self.calls.append(("role", role, name))
        return FakeLocator(f"{role}:{name}")

    def get_by_text(self, text):
        self.calls.append(("text", text))
        return FakeLocator(text)

    def get_by_test_id(self, test_id):
        self.calls.append(("test_id", test_id))
        return FakeLocator(test_id)

    def goto(self, url):
        self.calls.append(("goto", url))
        self.url = url

    def wait_for_load_state(self, state):
        self.calls.append(("load", state))

    def wait_for_url(self, pattern, timeout=0):
        self.calls.append(("wait_url", pattern, timeout))

    def wait_for_timeout(self, timeout):
        self.calls.append(("timeout", timeout))

    def screenshot(self, path, full_page=True):
        self.calls.append(("screenshot", path, full_page))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"png")

    def title(self):
        return "Page Title"


class FakeEvaluatePage(FakePage):
    def __init__(self):
        super().__init__()
        self.evaluated_scripts = []

    def evaluate(self, script, *args):
        self.evaluated_scripts.append((script, args))
        return True


class TestBaseAndExportPage:
    def test_base_page_wrappers_and_navigation(self, monkeypatch):
        monkeypatch.setattr(base_page_module, "get_config", lambda: SimpleNamespace(base_url="https://example.test/index"))
        monkeypatch.setattr(base_page_module.allure.attach, "file", lambda *args, **kwargs: None)
        page = FakePage()
        base = BasePage(page)

        base.navigate_to("/orders")
        base.click("#btn")
        base.fill("#input", "value")
        base.type_text("#input", "abc", delay=2)
        base.select_option("#select", "x")
        base.wait_for_element("#btn", timeout=5)
        base.wait_for_load_state("networkidle")
        base.scroll_to("#btn")
        base.hover("#btn")
        base.take_screenshot("unit-shot")

        assert ("goto", "https://example.test/orders") in page.calls
        assert base.get_text("#btn") == "text"
        assert base.get_attribute("#btn", "data-id") == "data-id-value"
        assert base.current_url == "https://example.test/orders"
        assert base.title == "Page Title"

    def test_base_page_try_helpers_success_and_failure(self, monkeypatch):
        monkeypatch.setattr(base_page_module, "get_config", lambda: SimpleNamespace(base_url="https://example.test"))
        page = FakePage()
        base = BasePage(page)

        assert base.try_click(["#ok"])
        assert base.try_fill(["#ok"], "value")
        assert base.try_click_by_role("button", ["Save"])

        base.wait_for_element = lambda selector, timeout=0: (_ for _ in ()).throw(RuntimeError("missing"))
        assert not base.try_click(["#bad"])
        assert not base.try_fill(["#bad"], "value")
        base.get_by_role = lambda role, name=None: (_ for _ in ()).throw(RuntimeError("missing"))
        assert not base.try_click_by_role("button", ["Missing"])

    def test_base_page_relative_navigation_requires_base_url(self, monkeypatch):
        monkeypatch.setattr(base_page_module, "get_config", lambda: SimpleNamespace(base_url=""))

        with pytest.raises(ValueError):
            BasePage(FakePage()).navigate_to("/orders")

    def test_login_page_verification_waits_for_spa_form(self, monkeypatch):
        monkeypatch.setattr(base_page_module, "get_config", lambda: SimpleNamespace(base_url="https://example.test"))
        page = FakePage()
        page.url = "https://example.test/"
        login_page = LoginPage(page)
        monkeypatch.setattr(login_page, "has_username_input", lambda timeout=5000: True)

        login_page.verify_login_page()

    def test_inventory_field_group_script_has_valid_selector_literals(self):
        page = FakeEvaluatePage()
        export_page = InventoryExportPage(page)

        assert export_page._activate_field_group("产品名称")
        script, args = page.evaluated_scripts[-1]

        assert args == ("商品信息",)
        assert "el-collapse-item__header, .el-checkbox, label, .tag_item" in script
        assert "[aria-expanded], .el-icon-arrow-right, .el-icon-arrow-down" in script

    def test_export_page_success_and_fallback_paths(self, monkeypatch, tmp_path):
        monkeypatch.setattr(base_page_module, "get_config", lambda: SimpleNamespace(base_url="https://example.test"))
        page = FakePage()
        export_page = ExportPage(page)

        assert export_page.wait_for_export_page(timeout=10)
        assert export_page.verify_url_has_sku_param()
        assert export_page.get_current_url() == page.url

        page.locator = lambda selector: page.calls.append(("locator", selector)) or FakeLocator(count=0)
        export_page.click_real_time_export()
        assert ("locator", 'button:has-text("实时导出")') in page.calls

        page.wait_for_url = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("timeout"))
        assert not export_page.wait_for_export_page()

    def test_inventory_export_api_fallback_respects_requested_timeout(self, monkeypatch, tmp_path):
        monkeypatch.setattr(base_page_module, "get_config", lambda: SimpleNamespace(base_url="https://example.test"))
        timeouts = []

        class FakeAPIResponse:
            ok = True
            status = 200
            url = "https://example.test/oms-api/oms-admin/base/inventory/inventoryExport"
            headers = {
                "content-type": "application/octet-stream",
                "content-disposition": 'attachment; filename="x.xlsx"',
            }

            def json(self):
                return {"data": {"OmsInventory": [{"label": "SKU", "prop": "sku"}], "OmsLocation": []}}

            def body(self):
                return b"excel-bytes"

        class FakeRequest:
            def get(self, *args, **kwargs):
                timeouts.append(("get", kwargs.get("timeout")))
                return FakeAPIResponse()

            def post(self, *args, **kwargs):
                timeouts.append(("post", kwargs.get("timeout")))
                return FakeAPIResponse()

        class FakeInventoryPage(FakePage):
            def __init__(self):
                super().__init__()
                self.url = "https://example.test/product/productCenter/exportPage"
                self.context = SimpleNamespace(request=FakeRequest())
                self._evaluate_calls = 0

            def evaluate(self, script):
                self._evaluate_calls += 1
                if self._evaluate_calls == 1:
                    return ["SKU-1"]
                if self._evaluate_calls == 2:
                    return "token"
                return ["SKU"]

        page = FakeInventoryPage()
        export_page = InventoryExportPage(page)
        result = export_page._download_inventory_export_via_api(str(tmp_path / "inventory.xlsx"), timeout=180000)

        assert result["success"]
        assert ("get", 180000) in timeouts
        assert ("post", 180000) in timeouts
