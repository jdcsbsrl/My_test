"""Unit tests for bounded retry behavior in the inventory SKU API client."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from modules.auto_test.api.inventory_sku_api import InventorySKUAPI


def test_list_page_retries_timeout_then_returns_response(monkeypatch) -> None:
    session = Mock()
    response = Mock()
    response.json.return_value = {"code": 0, "data": {"tableDataInfo": {"total": 0, "rows": []}}}
    session.post.side_effect = [requests.exceptions.ReadTimeout("slow"), response]
    sleep = Mock()
    monkeypatch.setattr("modules.auto_test.api.inventory_sku_api.time.sleep", sleep)
    client = InventorySKUAPI(session, "https://example.test")

    body = client.list_page({"itemId": "DWOYX-LD007"})

    assert body == response.json.return_value
    assert session.post.call_count == 2
    assert sleep.call_count == 1
    assert sleep.call_args.args == (client.RETRY_BACKOFF_SECONDS,)
    assert session.post.call_args.kwargs["timeout"] == client.REQUEST_TIMEOUT


def test_list_page_raises_diagnostic_timeout_after_bounded_attempts(monkeypatch) -> None:
    session = Mock()
    session.post.side_effect = requests.exceptions.ReadTimeout("slow")
    sleep = Mock()
    monkeypatch.setattr("modules.auto_test.api.inventory_sku_api.time.sleep", sleep)
    client = InventorySKUAPI(session, "https://example.test")

    with pytest.raises(requests.exceptions.Timeout, match="itemId=DWOYX-LD007"):
        client.list_page({"itemId": "DWOYX-LD007"})

    assert session.post.call_count == client.MAX_TIMEOUT_ATTEMPTS
    assert sleep.call_count == client.MAX_TIMEOUT_ATTEMPTS - 1
