import json
from pathlib import Path

from tools.import_openapi_markdown import convert


def test_convert_widdershins_markdown_to_business_rules(tmp_path: Path):
    source = tmp_path / "openapi.md"
    target = tmp_path / "knowledge.json"
    source.write_text(
        "## 告警任务\n\nGET /api/tasks\n\n返回任务列表。\n\n"
        "## 创建任务\n\nPOST /api/tasks\n\n创建一个任务。\n",
        encoding="utf-8",
    )

    assert convert(source, target) == 2
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["source_format"] == "widdershins-markdown"
    assert payload["statistics"]["endpoint_count"] == 2
    assert payload["business_rules"][0]["method"] == "GET"
    assert payload["business_rules"][0]["path"] == "/api/tasks"
    assert payload["business_rules"][1]["method"] == "POST"
