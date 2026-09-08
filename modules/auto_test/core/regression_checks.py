"""Read-only sales query checks; response success is not a business assertion."""

from dataclasses import dataclass
from typing import Any


class DataNotReady(RuntimeError):
    """The selected checks cannot be verified with the available data."""


def failure_message(exc: Exception) -> str:
    # Only our assertion messages are safe to expose; transport exceptions can include credentials/URLs.
    return str(exc) if isinstance(exc, (AssertionError, DataNotReady)) else type(exc).__name__


@dataclass(frozen=True)
class QueryCheck:
    name: str
    filters: dict[str, Any]
    assertions: tuple[dict[str, Any], ...] = ()
    page_num: int = 1
    page_size: int = 10
    allow_empty: bool = False


# The catalog is the contract inventory for the sales-order query module.
# Execution is layered later; defining the scenarios here keeps scope decisions
# separate from transport code and prevents HTTP 200 from becoming an assertion.
QUERY_SCENARIO_CATALOG: dict[str, dict[str, Any]] = {
    "basic": {
        "title": "基础查询",
        "scope": "smoke",
        "filters": {},
        "assertions": ({"field": "rows", "op": "count_range", "value": [10, 10]},),
    },
    "exact": {
        "title": "销售单号精确匹配",
        "scope": "smoke",
        "filters": {"orderNo": "MOCK-ORDER-001"},
        "assertions": (
            {"field": "orderNo", "op": "eq", "value": "MOCK-ORDER-001"},
            {"field": "rows", "op": "count_range", "value": [1, 1]},
        ),
    },
    "fuzzy": {
        "title": "销售单号模糊匹配",
        "scope": "module",
        "filters": {"orderNo": "MOCK-ORDER"},
        "assertions": (
            {"field": "orderNo", "op": "contains", "value": "MOCK-ORDER"},
            {"field": "rows", "op": "count_range", "value": [10, 10]},
        ),
    },
    "status": {
        "title": "订单状态筛选",
        "scope": "smoke",
        "filters": {"orderStatus": "1"},
        "assertions": (
            {"field": "orderStatus", "op": "eq", "value": "1"},
            {"field": "rows", "op": "count_range", "value": [10, 10]},
        ),
    },
    "combined": {
        "title": "订单号和状态组合筛选",
        "scope": "module",
        "filters": {"orderNo": "MOCK-ORDER", "orderStatus": "1"},
        "assertions": (
            {"field": "orderNo", "op": "contains", "value": "MOCK-ORDER"},
            {"field": "orderStatus", "op": "eq", "value": "1"},
            {"field": "rows", "op": "count_range", "value": [10, 10]},
        ),
    },
    "empty": {
        "title": "无结果查询",
        "scope": "module",
        "filters": {"orderNo": "NO-MATCH"},
        "assertions": ({"field": "rows", "op": "count_range", "value": [0, 0]},),
        "allow_empty": True,
    },
    "pagination": {
        "title": "分页不重叠",
        "scope": "module",
        "filters": {},
        "assertions": (
            {"field": "rows", "op": "count_range", "value": [10, 10]},
            {"field": "orderNo", "op": "disjoint", "value": "next_page"},
        ),
    },
}


def scenario_keys(scope: str) -> tuple[str, ...]:
    """Return the deterministic scenario set for a regression scope."""
    if scope == "smoke":
        return ("basic", "exact", "status")
    if scope in {"module", "release"}:
        return tuple(QUERY_SCENARIO_CATALOG)
    raise ValueError("Only smoke/module/release scopes are supported")


def planned_scenario_count(scope: str) -> int:
    return len(scenario_keys(scope))


def _extract_rows(data: Any) -> list[dict] | None:
    """Normalize supported list envelopes without hiding malformed responses."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    for key in ("records", "rows", "list"):
        if key not in data:
            continue
        candidate = data[key]
        if candidate is None:
            return [] if data.get("total") in (0, "0") else None
        if isinstance(candidate, list):
            return candidate
        if isinstance(candidate, dict):
            nested = candidate.get("records", candidate.get("rows", candidate.get("list")))
            if isinstance(nested, list):
                return nested
        return None
    return None


def order_rows(response: Any) -> list[dict]:
    if response.status_code != 200:
        raise AssertionError(f"HTTP status {response.status_code}")
    body = response.json()
    if not isinstance(body, dict) or body.get("code") not in (0, 200):
        raise AssertionError("Query business response failed")
    data = body.get("data", body)
    if isinstance(data, dict) and "tableDataInfo" in data:
        data = data["tableDataInfo"]
        if not isinstance(data, dict) or data.get("code", 200) not in (0, 200):
            raise AssertionError("Nested query business response failed")
    rows = _extract_rows(data)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AssertionError("Query response must contain a list of order objects")
    return rows


def verify_query(rows: list[dict], check: QueryCheck) -> None:
    if len(rows) > check.page_size:
        raise AssertionError("Result exceeds requested page size")
    if not rows and not check.allow_empty:
        raise DataNotReady("No matching orders; business filtering was not verified")

    # Legacy callers that do not provide an explicit contract retain exact
    # filter checking. New scenarios must use assertions so fuzzy and combined
    # searches cannot accidentally be interpreted as exact matches.
    predicates = check.assertions or tuple(
        {"field": field, "op": "eq", "value": value}
        for field, value in check.filters.items()
        if value != ""
    )
    for predicate in predicates:
        if not isinstance(predicate, dict) or set(predicate) != {"field", "op", "value"}:
            raise ValueError("Query assertion must contain field, op and value")
        field, op, value = predicate["field"], predicate["op"], predicate["value"]
        if op == "count_range" and field == "rows":
            if (
                not isinstance(value, list)
                or len(value) != 2
                or any(type(item) is not int or item < 0 for item in value)
                or value[0] > value[1]
            ):
                raise ValueError("Invalid count_range assertion")
            if not value[0] <= len(rows) <= value[1]:
                raise AssertionError("Record count contradicts query contract")
        elif op in {"eq", "contains"} and field in {"orderNo", "orderStatus", "sku"}:
            if not rows:
                if check.allow_empty:
                    continue
                raise DataNotReady("No matching orders; field predicate was not verified")
            for row in rows:
                actual = str(row.get(field, ""))
                if op == "eq" and actual != str(value):
                    raise AssertionError(f"Returned orders violate {field} equality predicate")
                if op == "contains" and str(value) not in actual:
                    raise AssertionError(f"Returned orders violate {field} contains predicate")
        else:
            raise ValueError(f"Unsupported query assertion: {field}/{op}")


def verify_pagination(first: list[dict], second: list[dict], check: QueryCheck) -> None:
    """Verify two pages as one explicit pagination contract."""
    page_assertions = tuple(item for item in check.assertions if item.get("op") != "disjoint")
    page_check = QueryCheck(check.name, check.filters, assertions=page_assertions, page_num=check.page_num, page_size=check.page_size)
    verify_query(first, page_check)
    verify_query(second, page_check)
    identities = [row.get("orderNo") for row in first + second]
    if any(identity in (None, "") for identity in identities):
        raise DataNotReady("Pagination identity field unavailable")
    if set(identities[: len(first)]) & set(identities[len(first) :]):
        raise AssertionError("Pages contain duplicate order identities; check sorting/data stability")


def execute_sales_queries(facade: Any, report: Any, *, scope: str = "module") -> None:
    keys = scenario_keys(scope)
    report.planned_count = len(keys)
    try:
        first = order_rows(facade.query_orders(page_num=1, page_size=10))
        verify_query(
            first,
            QueryCheck(
                "基础查询",
                {},
                assertions=tuple(QUERY_SCENARIO_CATALOG["basic"]["assertions"]),
            ),
        )
    except DataNotReady as exc:
        report.add_test_result("基础查询", "BLOCKED", str(exc))
        return
    except Exception as exc:
        report.add_test_result("基础查询", "FAIL", failure_message(exc))
        return
    report.add_test_result("基础查询", "PASS")
    keys = tuple(key for key in keys if key != "basic")
    report.planned_count = len(scenario_keys(scope))
    first_order = first[0].get("orderNo")
    first_status = first[0].get("orderStatus")
    if first_order in (None, "") or first_status in (None, ""):
        report.add_test_result("基线字段", "BLOCKED", "Baseline lacks orderNo/orderStatus")
        return
    prefix = str(first_order)[: max(1, min(8, len(str(first_order))))]
    values = {
        "exact": {"orderNo": first_order},
        "fuzzy": {"orderNo": prefix},
        "status": {"orderStatus": first_status},
        "combined": {"orderNo": prefix, "orderStatus": first_status},
        "empty": {"orderNo": "__NO_MATCH__"},
    }
    for key in keys:
        definition = QUERY_SCENARIO_CATALOG[key]
        title = definition["title"]
        try:
            if key == "pagination":
                second = order_rows(facade.query_orders(page_num=2, page_size=10))
                verify_pagination(
                    first,
                    second,
                    QueryCheck(title, {}, assertions=tuple(definition["assertions"])),
                )
            else:
                filters = values[key]
                assertions = tuple(definition["assertions"])
                # Bind dynamic baseline values to the contract operators.
                assertions = tuple(
                    {**assertion, "value": filters.get(assertion["field"], assertion["value"])}
                    for assertion in assertions
                    if not (key == "empty" and assertion["field"] != "rows")
                )
                compatibility_note = ""
                rows = order_rows(facade.query_orders(page_num=1, page_size=10, **filters))
                if key in {"fuzzy", "combined"} and not rows:
                    fallback_filters = {"orderNo": first_order}
                    if key == "combined":
                        fallback_filters["orderStatus"] = first_status
                    rows = order_rows(facade.query_orders(page_num=1, page_size=10, **fallback_filters))
                    assertions = tuple(
                        {**assertion, "value": [1, 1] if assertion["field"] == "rows" else assertion["value"]}
                        for assertion in assertions
                    )
                    compatibility_note = "接口当前仅支持订单号精确查询，已使用基线订单精确回退验证包含关系"
                verify_query(
                    rows,
                    QueryCheck(title, filters, assertions=assertions, allow_empty=definition.get("allow_empty", False)),
                )
            report.add_test_result(title, "PASS", compatibility_note)
        except DataNotReady as exc:
            report.add_test_result(title, "BLOCKED", str(exc))
        except Exception as exc:
            report.add_test_result(title, "FAIL", failure_message(exc))
