"""End-to-end security exploit regression and benign control tests via POST /search.

Drives every test through FastAPI TestClient against an ephemeral local
PostgreSQL 17 instance with zero imports from services.sql_guard so the exact
same suite proves RED on unpatched main and GREEN after hardening.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

EXPECTED_UI_KEYS = {"productDisplayName", "link", "unitPrice", "discount", "finalPrice", "rating"}


def _mock_nla_response(generated_query: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = {"generatedQuery": generated_query}
    resp.text = str(resp.json.return_value)
    return resp


def _decision(
    mode: str, *, params: dict[str, Any] | None = None, sql_query: str | None = None
) -> dict[str, Any]:
    inner: dict[str, Any] = {"selected_strategy": mode, "reasoning": "test strategy", "parameters": params or {}}
    if sql_query is not None:
        inner["sql_query"] = sql_query
    return {"mode": mode, "reason": "test strategy", "decision": inner}


def _post_search(
    client: TestClient, question: str, filters: dict[str, Any], decision: dict[str, Any], *, nla_sql: str | None = None
) -> Any:
    p_router = patch("services.search_case.IdentifySearchType.get_search_type", return_value=decision)
    if nla_sql is None:
        with p_router:
            return client.post("/search", json={"question": question, "filters": filters})
    with (
        p_router,
        patch("services.search_case.AlloyDbSearchTypes.get_access_token", return_value="fake-token"),
        patch("services.search_case.requests.post", return_value=_mock_nla_response(nla_sql)),
    ):
        return client.post("/search", json={"question": question, "filters": filters})


def _check_response_shape(resp: Any, violations: list[str]) -> dict[str, Any]:
    """Validate SearchResponse JSON shape without asserting a specific search_type."""
    try:
        parsed = resp.json()
    except Exception as exc:
        violations.append(f"Response is not valid JSON: {exc}")
        return {}
    if not isinstance(parsed, dict):
        violations.append(f"Expected JSON object, got {type(parsed).__name__}")
        return {}
    st = parsed.get("search_type")
    if not isinstance(st, str) or not st.strip():
        violations.append(f"Expected non-empty str search_type, got {st!r}")
    if not isinstance(parsed.get("reason"), str):
        violations.append(f"Expected str reason, got {parsed.get('reason')!r}")

    answer = parsed.get("answer")
    if not isinstance(answer, dict):
        violations.append(f"Expected dict answer, got {type(answer).__name__}: {answer!r}")
        return parsed
    if "error" in answer:
        violations.append("Raw 'error' key present in answer dict")
    if "traceback" in answer:
        violations.append("Raw 'traceback' key present in answer dict")

    details = answer.get("details")
    if not isinstance(details, list):
        violations.append(f"Expected list answer['details'], got {type(details).__name__}")
        return parsed
    for row in details:
        if isinstance(row, dict) and row.get("finalPrice") is not None and Decimal(str(row["finalPrice"])) == Decimal("0"):
            violations.append(f"Mutated RETURNING row with finalPrice=0 leaked: {row!r}")
    return parsed


def _assert_security_invariants(
    resp: Any,
    *,
    canary_secret: str,
    seq_before: int | None,
    seq_last_value: Callable[[], int | None],
    product_final_price: Callable[[int], Decimal],
) -> dict[str, Any]:
    """Assert universal security invariants (CWE-89, CWE-94, CWE-209)."""
    violations: list[str] = []
    if resp.status_code != 200:
        violations.append(f"Expected HTTP 200, got {resp.status_code}: {resp.text[:300]}")
    if canary_secret in resp.text:
        violations.append(f"Canary secret {canary_secret!r} leaked in HTTP response body")
    for header_name, header_val in resp.headers.items():
        if canary_secret in header_val:
            violations.append(f"Canary secret leaked in response header {header_name!r}")

    seq_after = seq_last_value()
    if seq_after != seq_before:
        violations.append(f"public.security_canary_seq advanced from {seq_before!r} to {seq_after!r}")

    db_price = product_final_price(1)
    if db_price != Decimal("60.00"):
        violations.append(f"DB row fashion_products id=1 finalPrice mutated to {db_price}")

    lowered = resp.text.lower()
    for needle, msg in (
        ("traceback (most recent call last)", "Raw Python traceback leaked"),
        ("invalid input syntax", "Raw PostgreSQL error ('invalid input syntax') leaked"),
        ("pg8000", "Raw DB driver ('pg8000') reference leaked"),
        ("sqlalchemy", "Raw SQLAlchemy reference leaked"),
        ("error occured during", "Raw internal error message leaked"),
    ):
        if needle in lowered:
            violations.append(msg)

    body = _check_response_shape(resp, violations)
    assert not violations, "Security invariant violation(s):\n- " + "\n- ".join(violations)
    return body


# =============================================================================
# 8 Live SQLi / Filter-Bypass Exploits (RED on main -> GREEN after fix)
# =============================================================================


@pytest.fixture()
def check_invariants(
    canary_secret: str, seq_last_value: Callable[[], int | None], product_final_price: Callable[[int], Decimal]
) -> Callable[[Any, int | None], dict[str, Any]]:
    def _check(resp: Any, seq_before: int | None) -> dict[str, Any]:
        return _assert_security_invariants(
            resp, canary_secret=canary_secret, seq_before=seq_before,
            seq_last_value=seq_last_value, product_final_price=product_final_price,
        )
    return _check


def test_exploit_ai_if_update_returning_write(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """1. ai.if must ignore LLM sql_query and never execute UPDATE ... RETURNING."""
    seq_before = seq_last_value()
    assert seq_before is None
    sql = (
        "UPDATE alloydb_usecase.fashion_products SET finalPrice = 0 WHERE id = 1 "
        "RETURNING productDisplayName, link, unitPrice, discount, finalPrice, rating"
    )
    resp = _post_search(client, "red shoes", {}, _decision("ai.if", params={"question_template": "Is this a red shoe?", "sql_constraints": None}, sql_query=sql))
    check_invariants(resp, seq_before)


def test_exploit_ai_if_cross_table_canary_and_sequence(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """2. ai.if must not read non-catalog tables or execute nextval() side-effects."""
    seq_before = seq_last_value()
    assert seq_before is None
    sql = (
        "SELECT secret AS productDisplayName, NULL AS link, NULL AS unitPrice, NULL AS discount, "
        "NULL AS finalPrice, nextval('public.security_canary_seq') AS rating FROM public.security_canary"
    )
    resp = _post_search(client, "casual shoes", {}, _decision("ai.if", params={"question_template": "Is this a shoe?", "sql_constraints": None}, sql_query=sql))
    check_invariants(resp, seq_before)


def test_exploit_nl_to_sql_update_returning_without_from(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """3. nl_to_sql must reject UPDATE ... RETURNING statements lacking a FROM clause."""
    seq_before = seq_last_value()
    assert seq_before is None
    sql = (
        "UPDATE alloydb_usecase.fashion_products SET finalPrice = 0 WHERE id = 1 "
        "RETURNING productDisplayName, link, unitPrice, discount, finalPrice, rating"
    )
    resp = _post_search(client, "discount shoes", {}, _decision("nl_to_sql", params={"semantic_text": "running shoes", "sql_constraints": None}), nla_sql=sql)
    check_invariants(resp, seq_before)


def test_exploit_nl_to_sql_derived_table_canary_and_sequence(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """4. nl_to_sql must reject derived-table exfiltration and nextval() calls."""
    seq_before = seq_last_value()
    assert seq_before is None
    sql = (
        "SELECT * FROM (SELECT secret AS productDisplayName, NULL AS link, NULL AS unitPrice, "
        "NULL AS discount, NULL AS finalPrice, nextval('public.security_canary_seq') AS rating FROM public.security_canary) x"
    )
    resp = _post_search(client, "list items", {}, _decision("nl_to_sql", params={"semantic_text": "running shoes", "sql_constraints": None}), nla_sql=sql)
    check_invariants(resp, seq_before)


def test_exploit_vector_error_based_sql_constraints_canary_and_traceback(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """5. vector search must reject unsafe sql_constraints and never leak DB errors/tracebacks."""
    seq_before = seq_last_value()
    assert seq_before is None
    payload = "1=CAST((SELECT secret FROM public.security_canary LIMIT 1) AS INTEGER)"
    resp = _post_search(client, "running shoes", {}, _decision("vector", params={"semantic_text": "running shoes", "sql_constraints": payload}))
    check_invariants(resp, seq_before)


def test_exploit_hybrid_error_based_sql_constraints_canary_and_traceback(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """6. hybrid search must reject unsafe sql_constraints and never leak DB errors/tracebacks."""
    seq_before = seq_last_value()
    assert seq_before is None
    payload = "1=CAST((SELECT secret FROM public.security_canary LIMIT 1) AS INTEGER)"
    resp = _post_search(client, "nike shoes", {}, _decision("hybrid", params={"semantic_text": "nike shoes", "sql_constraints": payload}))
    check_invariants(resp, seq_before)


def test_exploit_vector_ui_filter_or_bypass(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """7. vector sql_constraints must not bypass UI filters via OR precedence."""
    seq_before = seq_last_value()
    assert seq_before is None
    resp = _post_search(
        client, "nike shoes for men or women", {"brand": "Nike"},
        _decision("vector", params={"semantic_text": "shoes", "sql_constraints": "gender = 'Men' OR gender = 'Women'"}),
    )
    details = check_invariants(resp, seq_before)["answer"]["details"]
    assert len(details) >= 1
    non_nike = [r["productDisplayName"] for r in details if "nike" not in str(r.get("productDisplayName", "")).lower()]
    assert non_nike == [], f"UI brand='Nike' bypassed via OR sql_constraints: {non_nike}"


def test_exploit_vector_ui_filter_bind_clobber(
    client: TestClient, seq_last_value: Callable[[], int | None], check_invariants: Callable[[Any, int | None], dict[str, Any]]
) -> None:
    """8. vector sql_constraints bind tokens must not clobber UI filters or leak 500s.

    On unpatched main, injecting `:brand` clobbers the UI WHERE clause and triggers
    an unhandled HTTP 500 leaking raw DB/SQLAlchemy error details (CWE-209); after
    the fix, the unsafe bind token is blocked cleanly and UI filters stay enforced.
    """
    seq_before = seq_last_value()
    assert seq_before is None
    resp = _post_search(
        client, "cheap nike shoes", {"brand": "Nike", "price": {"max": 20}},
        _decision("vector", params={"semantic_text": "shoes", "sql_constraints": "brand = :brand"}),
    )
    details = check_invariants(resp, seq_before)["answer"]["details"]
    assert len(details) >= 1
    for row in details:
        assert "nike" in str(row.get("productDisplayName", "")).lower()
        assert Decimal(str(row["finalPrice"])) <= Decimal("20")


# =============================================================================
# 5 Benign E2E Controls (PASS on unmodified main AND after fix)
# =============================================================================


def _assert_benign_details(
    resp: Any, expected_mode: str, expected_names: set[str], seq_before: int | None, seq_last_value: Callable[[], int | None]
) -> None:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["search_type"] == expected_mode and "error" not in body["answer"]
    details = body["answer"]["details"]
    assert {row["productDisplayName"] for row in details} == expected_names
    for row in details:
        assert EXPECTED_UI_KEYS.issubset(row.keys())
    assert seq_last_value() == seq_before


def test_benign_vector_search(client: TestClient, seq_last_value: Callable[[], int | None]) -> None:
    seq_before = seq_last_value()
    resp = _post_search(
        client, "Men Nike running shoes under 100", {"brand": "Nike"},
        _decision("vector", params={"semantic_text": "running shoes", "sql_constraints": "gender = 'Men' AND finalPrice <= 100"}),
    )
    _assert_benign_details(resp, "vector", {"Nike Men Black Running Shoes"}, seq_before, seq_last_value)


def test_benign_hybrid_search(client: TestClient, seq_last_value: Callable[[], int | None]) -> None:
    seq_before = seq_last_value()
    resp = _post_search(
        client, "black nike running shoes", {"category": "Footwear"},
        _decision("hybrid", params={"semantic_text": "Nike running shoes", "sql_constraints": "baseColour ILIKE '%Black%' AND rating >= 4"}),
    )
    _assert_benign_details(resp, "hybrid", {"Nike Men Black Running Shoes"}, seq_before, seq_last_value)


def test_benign_nl_to_sql_simple_filter(client: TestClient, seq_last_value: Callable[[], int | None]) -> None:
    seq_before = seq_last_value()
    resp = _post_search(
        client, "Nike footwear under 50", {"category": "Footwear"}, _decision("nl_to_sql"),
        nla_sql="SELECT productDisplayName, finalPrice FROM alloydb_usecase.fashion_products WHERE brand = 'Nike' AND finalPrice <= 50;",
    )
    _assert_benign_details(resp, "nl_to_sql", {"Nike Women Red Casual Shoes"}, seq_before, seq_last_value)


def test_benign_nl_to_sql_select_count_star(client: TestClient, seq_last_value: Callable[[], int | None]) -> None:
    seq_before = seq_last_value()
    resp = _post_search(
        client, "How many Nike products are there?", {}, _decision("nl_to_sql"),
        nla_sql="SELECT COUNT(*) FROM alloydb_usecase.fashion_products WHERE brand = 'Nike';",
    )
    _assert_benign_details(resp, "nl_to_sql", {"Nike Men Black Running Shoes", "Nike Women Red Casual Shoes"}, seq_before, seq_last_value)


def test_benign_nl_to_sql_select_star(client: TestClient, seq_last_value: Callable[[], int | None]) -> None:
    seq_before = seq_last_value()
    resp = _post_search(
        client, "List all items with stock code 123ABC", {}, _decision("nl_to_sql"),
        nla_sql="SELECT * FROM alloydb_usecase.fashion_products WHERE stockCode = '123ABC' LIMIT 5;",
    )
    _assert_benign_details(resp, "nl_to_sql", {"Puma Men White Cotton Shirt"}, seq_before, seq_last_value)
