from types import SimpleNamespace

import pytest

from modules.auto_test.reporting import allure_http


pytestmark = pytest.mark.unit


def test_step_delegates_to_allure_step(monkeypatch):
    events = []

    class DummyStep:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, exc_type, exc, tb):
            events.append("exit")

    def fake_step(title):
        events.append(title)
        return DummyStep()

    monkeypatch.setattr(allure_http.allure, "step", fake_step)

    with allure_http.step("HTTP request"):
        events.append("body")

    assert events == ["HTTP request", "enter", "body", "exit"]


def test_attach_request_info_attaches_request_and_response(monkeypatch):
    attachments = []

    def fake_attach(body, name, attachment_type):
        attachments.append((body, name, attachment_type))

    monkeypatch.setattr(allure_http.allure, "attach", fake_attach)

    response = SimpleNamespace(
        request=SimpleNamespace(method="POST", url="https://example.test/api", body=b'{"sku":"A1"}'),
        status_code=201,
        text='{"ok":true}',
    )

    allure_http.attach_request_info(response)

    assert [name for _, name, _ in attachments] == [
        "Request",
        "Request Body",
        "Response Status",
        "Response Body",
    ]
    assert attachments[0][0] == "POST https://example.test/api"
    assert '"sku": "A1"' in attachments[1][0]
    assert attachments[2][0] == "201"
    assert '"ok": true' in attachments[3][0]


def test_attach_request_info_skips_empty_request_body(monkeypatch):
    attachments = []
    monkeypatch.setattr(
        allure_http.allure,
        "attach",
        lambda body, name, attachment_type: attachments.append((body, name, attachment_type)),
    )

    response = SimpleNamespace(
        request=SimpleNamespace(method="GET", url="https://example.test/api", body=None),
        status_code=204,
        text="",
    )

    allure_http.attach_request_info(response)

    assert [name for _, name, _ in attachments] == ["Request", "Response Status", "Response Body"]


def test_attach_request_info_redacts_credentials_and_tokens(monkeypatch):
    attachments = []
    monkeypatch.setattr(
        allure_http.allure,
        "attach",
        lambda body, name, attachment_type: attachments.append((body, name, attachment_type)),
    )

    response = SimpleNamespace(
        request=SimpleNamespace(
            method="POST",
            url="https://example.test/api?appKey=visible-secret",
            body=b'{"username":"alice","password":"pw","access_token":"jwt"}',
        ),
        status_code=200,
        text='{"token":"jwt","appSecret":"secret","ok":true}',
    )

    allure_http.attach_request_info(response)

    rendered = " ".join(str(body) for body, _, _ in attachments)
    assert "pw" not in rendered
    assert "jwt" not in rendered
    assert "secret" not in rendered
    assert "appKey=visible-secret" not in rendered
    assert "[REDACTED]" in rendered
