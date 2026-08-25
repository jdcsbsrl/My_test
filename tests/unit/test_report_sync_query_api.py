import pytest

from modules.auto_test.api.report_sync_query_api import (
    CursorPaginationLimitExceeded,
    CursorPaginationStalled,
    ReportSyncQueryAPI,
)


class FakeSession:
    def __init__(self, bodies):
        self.bodies = iter(bodies)
        self.payloads = []

    def post(self, url, json, timeout):
        self.payloads.append(json)
        return FakeResponse(next(self.bodies))


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def _page(rows, *, has_more, cursor=None):
    return {"code": 0, "data": rows, "hasMore": has_more, "nextCursor": cursor}


def test_query_all_accepts_a_bounded_page_budget():
    session = FakeSession(
        [
            _page([{"id": 1}], has_more=True, cursor="c1"),
            _page([{"id": 2}], has_more=False),
        ]
    )

    result = ReportSyncQueryAPI(session, "https://example.test").query_all({"updateAfter": "x"}, max_pages=2)

    assert [row["id"] for row in result] == [1, 2]
    assert session.payloads[1]["cursor"] == "c1"


def test_query_all_raises_limit_error_for_dense_window():
    session = FakeSession([_page([{"id": index}], has_more=True, cursor=f"c{index}") for index in range(3)])

    with pytest.raises(CursorPaginationLimitExceeded, match="budget"):
        ReportSyncQueryAPI(session, "https://example.test").query_all({}, max_pages=3)


def test_query_all_rejects_repeated_page_even_when_cursor_changes():
    repeated = [{"id": 1, "orderNo": "SO-1"}]
    session = FakeSession(
        [
            _page(repeated, has_more=True, cursor="c1"),
            _page(repeated, has_more=True, cursor="c2"),
        ]
    )

    with pytest.raises(CursorPaginationStalled, match="duplicate page"):
        ReportSyncQueryAPI(session, "https://example.test").query_all({})
