"""Allure steps and HTTP response attachments."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import allure
import requests


@contextmanager
def step(title: str) -> Generator[None, None, None]:
    with allure.step(title):
        yield


def attach_request_info(response: requests.Response) -> None:
    allure.attach(
        response.request.method + " " + response.request.url,
        name="Request",
        attachment_type=allure.attachment_type.TEXT,
    )
    if response.request.body:
        body = response.request.body
        allure.attach(
            body.decode() if isinstance(body, bytes) else str(body),
            name="Request Body",
            attachment_type=allure.attachment_type.JSON,
        )
    allure.attach(
        str(response.status_code),
        name="Response Status",
        attachment_type=allure.attachment_type.TEXT,
    )
    try:
        allure.attach(
            response.text,
            name="Response Body",
            attachment_type=allure.attachment_type.JSON,
        )
    except Exception:
        allure.attach(
            response.text,
            name="Response Body",
            attachment_type=allure.attachment_type.TEXT,
        )
