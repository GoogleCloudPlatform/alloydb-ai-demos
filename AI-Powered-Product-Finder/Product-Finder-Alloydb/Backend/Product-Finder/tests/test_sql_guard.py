"""Unit, PG17 integration, and FastAPI security regression tests for sql_guard & search_case."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import json
import logging
import time
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
import requests
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from services.search_case import AlloyDbSearchTypes, IdentifySearchType
from services.sql_guard import (
    CATALOG_COLUMN_TYPES, UI_SELECT_COLUMNS, UnsafeSQLError,
    build_safe_nltosql_query, clean_search_text, coerce_column_literal,
    combine_where_clauses, compile_sql_constraints, empty_search_result,
    execute_readonly, format_display_sql, tokenize_sql,
    validate_question_template, validate_sql_identifier,
)
from services.utils import build_where_clause, normalize_filters

SCHEMA_NAME = "alloydb_usecase"
TABLE_NAME = "fashion_products"
FQ = f"{SCHEMA_NAME}.{TABLE_NAME}"
UI_SELECT = f"SELECT productDisplayName, link, unitPrice, discount, finalPrice, rating FROM {FQ}"
UI_COLUMNS_LOWER = frozenset(col.lower() for col in UI_SELECT_COLUMNS)
EXPECTED_UI_KEYS = frozenset(UI_SELECT_COLUMNS)
UPSTREAM_SECRET_MARKER = "SECRET_API_KEY_123"


def _assert_clean_search_response(resp: Any, *, canary_secret: str) -> dict[str, Any]:
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    raw, lowered = resp.text, resp.text.lower()
    assert canary_secret not in raw and UPSTREAM_SECRET_MARKER not in raw
    for needle in ("traceback (most recent call last)", "pg8000", "sqlalchemy", "invalid input syntax"):
        assert needle not in lowered
    body = resp.json()
    assert isinstance(body.get("search_type"), str) and body["search_type"] != ""
    assert isinstance(body.get("reason"), str)
    ans = body.get("answer")
    assert isinstance(ans, dict) and "error" not in ans and "traceback" not in ans
    assert isinstance(ans.get("sql_command"), str) and isinstance(ans.get("details"), list)
    for item in ans["details"]:
        assert EXPECTED_UI_KEYS.issubset(item.keys())
    return body


def _post_with_router(
    client: TestClient, router_output: Any, question: str = "running shoes", filters: dict[str, Any] | None = None
) -> Any:
    with patch("services.search_case.IdentifySearchType.get_search_type", return_value=router_output):
        return client.post("/search", json={"question": question, "filters": filters or {}})


# =============================================================================
# 1. compile_sql_constraints & coerce_column_literal
# =============================================================================

POSITIVE_CONSTRAINT_CASES: list[tuple[str, str, list[tuple[Any, type]], int]] = [
    ("year = '2012'", "year = :llm_c_0", [(2012, sa.Integer)], 2),
    ("rating >= '4'", "rating >= :llm_c_0", [(Decimal("4"), sa.Numeric)], 4),
    ("discount >= 40.0", "discount >= :llm_c_0", [(40, sa.Integer)], 3),
    ("discount >= 40.5", "discount >= :llm_c_0", [(Decimal("40.5"), sa.Numeric)], 2),
    ("stockCode = 12345", "stockcode = :llm_c_0", [("12345", sa.String)], 0),
    ("year > 3000000000", "year > :llm_c_0", [(Decimal("3000000000"), sa.Numeric)], 0),
    ("brand NOT ILIKE '%nike%'", "brand NOT ILIKE :llm_c_0", [("%nike%", sa.String)], 3),
    (
        "NOT (brand ILIKE '%nike%') AND NOT (combined_description LIKE '%leather%')",
        "NOT (brand ILIKE :llm_c_0) AND NOT (combined_description LIKE :llm_c_1)",
        [("%nike%", sa.String), ("%leather%", sa.String)], 3,
    ),
    (
        "gender IN ('Men', 'Unisex') AND year NOT IN (2010, '2018')",
        "gender IN (:llm_c_0, :llm_c_1) AND year NOT IN (:llm_c_2, :llm_c_3)",
        [("Men", sa.String), ("Unisex", sa.String), (2010, sa.Integer), (2018, sa.Integer)], 2,
    ),
    (
        "finalPrice BETWEEN 10.50 AND 40.00 AND rating NOT BETWEEN '1' AND '2.5'",
        "finalprice BETWEEN :llm_c_0 AND :llm_c_1 AND rating NOT BETWEEN :llm_c_2 AND :llm_c_3",
        [(Decimal("10.50"), sa.Numeric), (Decimal("40.00"), sa.Numeric), (Decimal("1"), sa.Numeric), (Decimal("2.5"), sa.Numeric)], 3,
    ),
    ("brand IS NOT NULL AND season IS NULL", "brand IS NOT NULL AND season IS NULL", [], 0),
    (
        "(gender = 'Men' OR gender = 'Women') AND baseColour <> 'Red' AND articleType != 'Belts' AND rating > -1",
        "(gender = :llm_c_0 OR gender = :llm_c_1) AND basecolour <> :llm_c_2 AND articletype != :llm_c_3 AND rating > :llm_c_4",
        [("Men", sa.String), ("Women", sa.String), ("Red", sa.String), ("Belts", sa.String), (Decimal("-1"), sa.Numeric)], 3,
    ),
    (
        "brand = 'Levi''s' AND \"finalPrice\" < 100 -- benign note\n",
        "brand = :llm_c_0 AND finalprice < :llm_c_1",
        [("Levi's", sa.String), (Decimal("100"), sa.Numeric)], 0,
    ),
]


@pytest.mark.parametrize("raw_sql,expected_sql,expected_binds,expected_rows", POSITIVE_CONSTRAINT_CASES)
def test_compile_sql_constraints_positive_and_pg17_exec(
    raw_sql: str, expected_sql: str, expected_binds: list[tuple[Any, type]], expected_rows: int, pg_engine: Engine, reset_db: Any
) -> None:
    del reset_db
    where_expr, binds = compile_sql_constraints(raw_sql)
    assert where_expr == expected_sql and len(binds) == len(expected_binds)
    for idx, (exp_val, exp_cls) in enumerate(expected_binds):
        bp = binds[f"llm_c_{idx}"]
        assert bp.value == exp_val and type(bp.value) is type(exp_val) and isinstance(bp.type, exp_cls)
    stmt = sa.text(f"SELECT id FROM {FQ} WHERE ({where_expr})")
    if binds:
        stmt = stmt.bindparams(*binds.values())
    assert len(execute_readonly(pg_engine, stmt, timeout_ms=5_000)) == expected_rows


@pytest.mark.parametrize("sentinel", [None, "", "   ", "\t\r\n", "None", "none", "NONE", "NULL", "null"])
def test_compile_sql_constraints_sentinels(sentinel: Any) -> None:
    assert compile_sql_constraints(sentinel) == ("", {})


@pytest.mark.parametrize("bad_non_str", [123, True, ["brand = 'Nike'"], {"a": 1}])
def test_compile_sql_constraints_strict_non_string(bad_non_str: Any) -> None:
    with pytest.raises(UnsafeSQLError):
        compile_sql_constraints(bad_non_str)


NEGATIVE_CONSTRAINT_CASES = [
    "1 = 1", "brand = 'Nike' OR 1 = 1", f"brand = 'Nike'; DROP TABLE {FQ}",
    "brand = 'Nike' /* OR 1=1 */", "brand = 'Nike' -- ok\rOR 1=1", "brand = $$Nike$$",
    "brand = E'Nike'", "brand = U&'\\004Eike'", "brand = 'Nike\\' OR 1=1 --'",
    "brand = :brand", "brand = $1", "brand = %(brand)s", "pg_sleep(1) IS NULL",
    "1 = CAST((SELECT secret FROM public.security_canary LIMIT 1) AS INTEGER)",
    "brand = CURRENT_USER", "combined_description_embedding IS NOT NULL", "query_embedding.embed IS NOT NULL",
    "discount ILIKE '%4%'", "year = 'not_a_year'", "finalPrice <= 'NaN'", "rating >= 'Infinity'",
    "rating >= '\u0664'", "finalPrice <= '1e1000000'", "brand IN ()", "brand = 'Nike') OR (1=1",
    "-- comment only", "none\x0b", "brand = 'Nike'\x00", "brand = 'Nike\ud800'", "brand = 'Nike\u2028'",
    "br\u0430nd = 'Nike'", "brand\u00a0=\u00a0'Nike'", "rating = - -4", "id = 0x10", "finalPrice = 1_000",
    "WHERE brand = 'Nike'", "brand = 'Nike' ORDER BY finalPrice LIMIT 1", "brand ILIKE '%%'",
    f"brand ILIKE '%{'a' * 127}%'", "brand ILIKE '%a%b%c%d%e%f%'",
    " OR ".join(f"brand ILIKE '%k{i}%'" for i in range(9)),
    "brand IN (" + ", ".join(f"'B{i}'" for i in range(51)) + ")",
    "(" * 17 + "brand = 'Nike'" + ")" * 17, "NOT " * 17 + "brand = 'Nike'",
    " OR ".join(["brand = 'Nike'"] * 65), " " * 2001,
]


@pytest.mark.parametrize("payload", NEGATIVE_CONSTRAINT_CASES)
def test_compile_sql_constraints_negative_attacks(payload: str) -> None:
    with pytest.raises(UnsafeSQLError):
        compile_sql_constraints(payload)


def test_compile_sql_constraints_boundaries_and_coercion(pg_engine: Engine, reset_db: None) -> None:
    del reset_db
    assert len(CATALOG_COLUMN_TYPES) == 19 and "combined_description_embedding" not in CATALOG_COLUMN_TYPES
    assert coerce_column_literal("stockCode", "00123", is_string_literal=False)[0] == "00123"
    assert coerce_column_literal("finalPrice", "-0.0")[0] == Decimal("0")
    sql16, b16 = compile_sql_constraints("(" * 16 + "brand = 'Nike'" + ")" * 16)
    assert len(execute_readonly(pg_engine, sa.text(f"SELECT id FROM {FQ} WHERE ({sql16})").bindparams(*b16.values()))) == 2
    in50 = "brand IN (" + ", ".join(f"'B{i}'" for i in range(50)) + ")"
    assert len(compile_sql_constraints(f"{in50} OR {in50}")[1]) == 100
    with pytest.raises(UnsafeSQLError):
        compile_sql_constraints(f"{in50} OR {in50} OR brand = 'X'")
    giant = "X" * 400
    with pytest.raises(UnsafeSQLError) as exc_info:
        coerce_column_literal("finalPrice", giant)
    assert len(str(exc_info.value)) < 256 and giant not in str(exc_info.value)


# =============================================================================
# 2. build_safe_nltosql_query: Positive Exact Emitted SQL + PG17 Execution
# =============================================================================

POSITIVE_NLTOSQL_CASES: list[tuple[str, str, dict[str, Any], str, dict[str, Any], int]] = [
    (f"SELECT * FROM {FQ}", "", {}, f"{UI_SELECT}", {}, 5),
    (
        f"SELECT COUNT(*) FROM {FQ} WHERE brand = 'Nike';", "", {},
        f"{UI_SELECT} WHERE (brand = :nla_p_0)", {"nla_p_0": "Nike"}, 2,
    ),
    (
        f"SELECT COUNT(DISTINCT brand) FROM {TABLE_NAME} WHERE {TABLE_NAME}.year = '2012'", "", {},
        f"{UI_SELECT} WHERE (year = :nla_p_0)", {"nla_p_0": 2012}, 2,
    ),
    (
        f"SELECT p.* FROM {FQ} AS p WHERE LOWER(p.brand) = 'nike' AND UPPER(p.gender) IN ('MEN', 'WOMEN') ORDER BY p.finalPrice ASC, p.rating DESC NULLS LAST LIMIT 2 OFFSET 1",
        "", {},
        f"{UI_SELECT} WHERE (LOWER(brand) = :nla_p_0 AND UPPER(gender) IN (:nla_p_1, :nla_p_2)) ORDER BY finalprice ASC, rating DESC NULLS LAST LIMIT :nla_p_3 OFFSET :nla_p_4",
        {"nla_p_0": "nike", "nla_p_1": "MEN", "nla_p_2": "WOMEN", "nla_p_3": 2, "nla_p_4": 1}, 1,
    ),
    (
        f"SELECT UPPER(brand) AS b FROM {FQ} WHERE brand NOT ILIKE '%biba%' ORDER BY LOWER(brand) ASC NULLS FIRST LIMIT 3 OFFSET 0",
        "", {},
        f"{UI_SELECT} WHERE (brand NOT ILIKE :nla_p_0) ORDER BY LOWER(brand) ASC NULLS FIRST LIMIT :nla_p_1 OFFSET :nla_p_2",
        {"nla_p_0": "%biba%", "nla_p_1": 3, "nla_p_2": 0}, 3,
    ),
    (
        f"SELECT DISTINCT productDisplayName FROM {FQ} WHERE gender = 'Men' OR gender = 'Women' ORDER BY finalPrice DESC",
        "WHERE masterCategory = :category AND brand = :brand", {"category": "Footwear", "brand": "Nike"},
        f"SELECT DISTINCT productDisplayName, link, unitPrice, discount, finalPrice, rating FROM {FQ} WHERE (masterCategory = :category AND brand = :brand) AND (gender = :nla_p_0 OR gender = :nla_p_1) ORDER BY finalprice DESC",
        {"category": "Footwear", "brand": "Nike", "nla_p_0": "Men", "nla_p_1": "Women"}, 2,
    ),
    (
        f"SELECT * FROM {FQ} ORDER BY finalPrice ASC LIMIT 5",
        "WHERE masterCategory = :category", {"category": "Apparel"},
        f"{UI_SELECT} WHERE (masterCategory = :category) ORDER BY finalprice ASC LIMIT :nla_p_0",
        {"category": "Apparel", "nla_p_0": 5}, 2,
    ),
    (
        f"SELECT * FROM {FQ} WHERE brand = 'Nike' LIMIT 5000",
        "", {},
        f"{UI_SELECT} WHERE (brand = :nla_p_0) LIMIT :nla_p_1",
        {"nla_p_0": "Nike", "nla_p_1": 5000}, 2,
    ),
    (
        '-- header\rSELECT "ProductDisplayName" FROM "ALLOYDB_USECASE"."FASHION_PRODUCTS" WHERE "discount" >= 40.5 -- note\nLIMIT 0',
        "", {}, f"{UI_SELECT} WHERE (discount >= :nla_p_0) LIMIT :nla_p_1", {"nla_p_0": Decimal("40.5"), "nla_p_1": 0}, 0,
    ),
    (
        f"SELECT SUM(finalPrice), MAX(rating) FROM {FQ} WHERE finalPrice BETWEEN 10 AND 60 AND stockStatus IS NOT NULL",
        "", {}, f"{UI_SELECT} WHERE (finalprice BETWEEN :nla_p_0 AND :nla_p_1 AND stockstatus IS NOT NULL)",
        {"nla_p_0": Decimal("10"), "nla_p_1": Decimal("60")}, 5,
    ),
]


@pytest.mark.parametrize("raw_sql,ui_where,ui_params,expected_sql,expected_binds,expected_rows", POSITIVE_NLTOSQL_CASES)
def test_build_safe_nltosql_query_positive_exact_sql_and_pg17(
    raw_sql: str, ui_where: str, ui_params: dict[str, Any],
    expected_sql: str, expected_binds: dict[str, Any], expected_rows: int, pg_engine: Engine, reset_db: Any,
) -> None:
    del reset_db
    stmt, display_sql = build_safe_nltosql_query(
        raw_sql, schema_name=SCHEMA_NAME, table_name=TABLE_NAME, ui_where_sql=ui_where, ui_params=ui_params
    )
    assert stmt.text == expected_sql
    if "LIMIT" not in raw_sql.upper():
        assert "LIMIT" not in stmt.text
    assert set(stmt._bindparams) == set(expected_binds)
    for k, exp_val in expected_binds.items():
        bp = stmt._bindparams[k]
        assert bp.value == exp_val and type(bp.value) is type(exp_val)
        if f"LIMIT :{k}" in stmt.text or f"OFFSET :{k}" in stmt.text:
            assert isinstance(bp.type, sa.BigInteger)
    assert "--" not in stmt.text and ";" not in stmt.text and "'" not in stmt.text and display_sql
    rows = execute_readonly(pg_engine, stmt, timeout_ms=5_000)
    assert len(rows) == expected_rows and all(set(r.keys()) == UI_COLUMNS_LOWER for r in rows)


# =============================================================================
# 3. build_safe_nltosql_query: Negative Attacks (Parametrized)
# =============================================================================

NEGATIVE_NLTOSQL_CASES = [
    # Multi-statement, set ops, CTEs
    f"SELECT * FROM {FQ}; DROP TABLE {FQ}", f"SELECT * FROM {FQ};;",
    f"SELECT * FROM {FQ} UNION SELECT secret FROM public.security_canary",
    f"SELECT id FROM {FQ} UNION ALL SELECT id FROM {FQ}",
    f"SELECT brand FROM {FQ} INTERSECT SELECT brand FROM {FQ}",
    f"SELECT brand FROM {FQ} EXCEPT SELECT brand FROM {FQ}",
    f"WITH p AS (SELECT * FROM {FQ}) SELECT * FROM p",
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT * FROM r",
    f"WITH u AS (UPDATE {FQ} SET finalPrice = 0 RETURNING id) SELECT * FROM {FQ}",
    # Subqueries in select list, WHERE, ORDER BY, and IN
    f"SELECT (SELECT secret FROM public.security_canary LIMIT 1) FROM {FQ}",
    f"SELECT * FROM {FQ} WHERE brand = (SELECT brand FROM {FQ} LIMIT 1)",
    f"SELECT * FROM {FQ} WHERE EXISTS (SELECT 1 FROM public.security_canary)",
    f"SELECT * FROM {FQ} ORDER BY (SELECT id FROM {FQ} LIMIT 1)",
    f"SELECT * FROM {FQ} WHERE brand IN (SELECT brand FROM {FQ})",
    # JOINs, comma joins, LATERAL, ONLY, TABLESAMPLE, derived/VALUES/TABLE
    f"SELECT p.* FROM {FQ} p JOIN public.security_canary c ON TRUE",
    f"SELECT a.* FROM {FQ} a LEFT JOIN {FQ} b ON a.id = b.id",
    f"SELECT * FROM {FQ} a, {FQ} b", f"SELECT p.* FROM {FQ} p, LATERAL (SELECT 1) x",
    f"SELECT * FROM ONLY {FQ}", f"SELECT * FROM {FQ} TABLESAMPLE SYSTEM (10)",
    "SELECT * FROM (SELECT * FROM public.security_canary) x",
    "SELECT * FROM (VALUES ('Nike')) AS t(brand)", f"TABLE {FQ}",
    # Other table/schema, 3-part names, wrong qualifier, reserved/bad aliases
    "SELECT * FROM public.security_canary", "SELECT * FROM pg_catalog.pg_tables",
    f"SELECT * FROM other_schema.{TABLE_NAME}", f"SELECT * FROM postgres.{FQ}",
    f"SELECT {FQ}.brand FROM {FQ}", f"SELECT x.brand FROM {FQ}",
    f"SELECT * FROM {FQ} AS fp WHERE {TABLE_NAME}.brand = 'Nike'",
    f"SELECT * FROM {FQ} AS select", f"SELECT * FROM {FQ} AS collate",
    f"SELECT * FROM {FQ} AS brand", f'SELECT * FROM {FQ} AS "fp"', f"SELECT * FROM {FQ} AS fp(c1)",
    # Dangerous functions, system/excluded cols, :: and CAST
    f"SELECT * FROM {FQ} WHERE pg_sleep(1) IS NULL",
    f"SELECT * FROM {FQ} WHERE set_config('log_statement', 'none', false) = 'none'",
    f"SELECT * FROM {FQ} WHERE ai.generate('hi') IS NOT NULL",
    f"SELECT * FROM {FQ} WHERE id = nextval('public.security_canary_seq')",
    f"SELECT pg_catalog.lower(brand) FROM {FQ}", f"SELECT CURRENT_USER FROM {FQ}",
    f"SELECT ctid FROM {FQ}", f"SELECT combined_description_embedding FROM {FQ}",
    f"SELECT * FROM {FQ} WHERE finalPrice::numeric > 0",
    f"SELECT * FROM {FQ} WHERE 'public.security_canary'::regclass IS NOT NULL",
    f"SELECT * FROM {FQ} WHERE CAST(year AS INTEGER) = 2012",
    f"SELECT * FROM {FQ} WHERE regclass 'public.security_canary' IS NOT NULL",
    # Lexical attacks: comments, quotes, escapes, params
    f"SELECT /* comment */ * FROM {FQ}", f"SELECT /* a /* b */ c */ * FROM {FQ}",
    f"SELECT * FROM {FQ} -- ok\rUNION SELECT secret FROM public.security_canary",
    f"SELECT * FROM {FQ} WHERE brand = $$Nike$$", f"SELECT * FROM {FQ} WHERE brand = $q$Nike$q$",
    f"SELECT * FROM {FQ} WHERE brand = E'Nike'", f"SELECT * FROM {FQ} WHERE brand = U&'\\004Eike'",
    f'SELECT U&"brand" FROM {FQ}', f"SELECT * FROM {FQ} WHERE brand = 'Nike\\'",
    f"SELECT * FROM {FQ} WHERE brand = :brand", f"SELECT * FROM {FQ} WHERE brand = $1",
    f"SELECT * FROM {FQ} WHERE brand = %(brand)s", f"SELECT * FROM {FQ} WHERE brand = 'Ni'\n'ke'",
    # Locking, INTO, RETURNING, DML/DDL/utility
    f"SELECT * FROM {FQ} FOR UPDATE", f"SELECT * FROM {FQ} FOR SHARE",
    f"SELECT * INTO TEMP TABLE leak FROM {FQ}",
    f"UPDATE {FQ} SET finalPrice = 0 WHERE id = 1 RETURNING *",
    f"DELETE FROM {FQ} WHERE id = 1", f"INSERT INTO {FQ} (id) VALUES (99)",
    f"TRUNCATE {FQ}", f"COPY {FQ} TO PROGRAM 'id'",
    "DO $$ BEGIN PERFORM 1; END $$", f"EXPLAIN SELECT * FROM {FQ}",
    # LIMIT / OFFSET / FETCH bounds (int8 overflow and non-uint forms)
    f"SELECT * FROM {FQ} LIMIT 9223372036854775808", f"SELECT * FROM {FQ} LIMIT ALL", f"SELECT * FROM {FQ} LIMIT NULL",
    f"SELECT * FROM {FQ} LIMIT -1", f"SELECT * FROM {FQ} LIMIT 5.5",
    f"SELECT * FROM {FQ} OFFSET 9223372036854775808", f"SELECT * FROM {FQ} OFFSET -1",
    f"SELECT * FROM {FQ} FETCH FIRST 5 ROWS ONLY",
    # ORDER BY / DISTINCT / GROUP BY / aggregates
    f"SELECT productDisplayName, finalPrice FROM {FQ} ORDER BY 2",
    f"SELECT * FROM {FQ} ORDER BY random()",
    f"SELECT DISTINCT brand FROM {FQ} ORDER BY brand",
    f"SELECT DISTINCT productDisplayName FROM {FQ} ORDER BY LOWER(productDisplayName)",
    f"SELECT DISTINCT productDisplayName FROM {FQ} ORDER BY LOWER(brand)",
    f"SELECT * FROM {FQ} ORDER BY " + ", ".join(["id"] * 9),
    f"SELECT COUNT(*) FROM {FQ} ORDER BY id",
    f"SELECT DISTINCT ON (brand) * FROM {FQ}", f"SELECT brand, COUNT(*) FROM {FQ} GROUP BY brand",
    f"SELECT COUNT(*) FROM {FQ} HAVING COUNT(*) > 0", f"SELECT COUNT(*) OVER () FROM {FQ}",
    f"SELECT COUNT(*) FILTER (WHERE brand = 'Nike') FROM {FQ}",
    f"SELECT brand, COUNT(*) FROM {FQ}", f"SELECT AVG(brand) FROM {FQ}",
    # LIKE/ILIKE, IN, depth, LOWER/UPPER type & nesting rules
    f"SELECT * FROM {FQ} WHERE brand ILIKE '%{'a' * 127}%'",
    f"SELECT * FROM {FQ} WHERE brand ILIKE '%a%b%c%d%e%f%'", f"SELECT * FROM {FQ} WHERE brand ILIKE '%%'",
    f"SELECT * FROM {FQ} WHERE " + " OR ".join(f"brand ILIKE '%k{i}%'" for i in range(9)),
    f"SELECT * FROM {FQ} WHERE year ILIKE '%20%'",
    f"SELECT * FROM {FQ} WHERE brand IN (" + ", ".join(f"'B{i}'" for i in range(51)) + ")",
    f"SELECT * FROM {FQ} WHERE brand IN ()",
    f"SELECT * FROM {FQ} WHERE " + "(" * 17 + "brand = 'Nike'" + ")" * 17,
    f"SELECT * FROM {FQ} WHERE " + "NOT " * 17 + "brand = 'Nike'",
    f"SELECT LOWER(id) FROM {FQ}", f"SELECT * FROM {FQ} WHERE LOWER(id) = '1'",
    f"SELECT * FROM {FQ} ORDER BY UPPER(year)", f"SELECT * FROM {FQ} WHERE LOWER(brand) > 'a'",
    f"SELECT * FROM {FQ} WHERE LOWER(brand) IS NULL", f"SELECT * FROM {FQ} WHERE LOWER(brand) BETWEEN 'a' AND 'z'",
    f"SELECT * FROM {FQ} WHERE LOWER(LOWER(brand)) = 'nike'",
    f"SELECT * FROM {FQ} WHERE UPPER(LOWER(brand)) = 'NIKE'",
]


@pytest.mark.parametrize("bad_sql", NEGATIVE_NLTOSQL_CASES)
def test_build_safe_nltosql_query_negative_attacks(bad_sql: str) -> None:
    with pytest.raises(UnsafeSQLError):
        build_safe_nltosql_query(bad_sql, schema_name=SCHEMA_NAME, table_name=TABLE_NAME)


def test_build_safe_nltosql_query_invalid_args_and_ui_params(pg_engine: Engine, reset_db: None) -> None:
    del reset_db
    max_int8_stmt, _ = build_safe_nltosql_query(
        f"SELECT * FROM {FQ} LIMIT 9223372036854775807 OFFSET 0", schema_name=SCHEMA_NAME, table_name=TABLE_NAME
    )
    assert isinstance(max_int8_stmt._bindparams["nla_p_0"].type, sa.BigInteger)
    assert isinstance(max_int8_stmt._bindparams["nla_p_1"].type, sa.BigInteger)
    assert len(execute_readonly(pg_engine, max_int8_stmt)) == 5

    for bad_ui, bad_params in (
        (123, {}),
        ("WHERE brand = :brand\x00", {"brand": "Nike"}),
        ("WHERE brand = :brand\ud800", {"brand": "Nike"}),
        ("WHERE brand = :brand", ["Nike"]),
        ("WHERE brand = :nla_p_0", {"nla_p_0": "Nike"}),
        ("WHERE brand = :nla_p_custom", {"nla_p_custom": "Nike"}),
        ("WHERE brand = :brand", {123: "Nike"}),
        ("WHERE brand = :brand", {"": "Nike"}),
        ("WHERE brand = :brand", {"1bad": "Nike"}),
        ("WHERE brand = :brand", {"bad-key": "Nike"}),
        ("WHERE brand = :brand", {"a" * 64: "Nike"}),
        ("WHERE brand = :brand", {"brand": "Nike\x00"}),
        ("WHERE brand = :brand", {"brand": "Nike\ud800"}),
        ("WHERE brand = :brand", {"brand": "Nike\udfff"}),
        ("WHERE brand = :missing", {}),
        ("WHERE brand = :missing", None),
        ("", {"unused": "Nike"}),
    ):
        with pytest.raises(UnsafeSQLError):
            build_safe_nltosql_query(f"SELECT * FROM {FQ}", schema_name=SCHEMA_NAME, table_name=TABLE_NAME, ui_where_sql=bad_ui, ui_params=bad_params)  # type: ignore[arg-type]

    ws_stmt, _ = build_safe_nltosql_query(
        f"SELECT * FROM {FQ}",
        ui_where_sql="WHERE brand = :brand",
        ui_params={"brand": "Nike\n\r\t"},
        schema_name=SCHEMA_NAME,
        table_name=TABLE_NAME,
    )
    assert execute_readonly(pg_engine, ws_stmt) == []

    # Integration: services.utils.build_where_clause -> build_safe_nltosql_query -> PG17.
    ui_w, ui_p = build_where_clause(
        normalize_filters({"filter": {"category": "Footwear", "brand": "Nike", "rating": 4.0, "price": {"min": 50, "max": 100}}})
    )
    stmt, _ = build_safe_nltosql_query(
        f"SELECT * FROM {FQ} WHERE gender = 'Men' OR gender = 'Women'",
        ui_where_sql=ui_w, ui_params=ui_p, schema_name=SCHEMA_NAME, table_name=TABLE_NAME,
    )
    rows = execute_readonly(pg_engine, stmt, timeout_ms=5_000)
    assert [r["productdisplayname"] for r in rows] == ["Nike Men Black Running Shoes"]


# =============================================================================
# 4. Validators, clean_search_text, Controls/Surrogates & PG17 Pool Survival
# =============================================================================


def test_validators_helpers_and_tokenizer() -> None:
    a, b = empty_search_result(), empty_search_result()
    assert a == {"sql_command": "", "details": []}
    a["details"].append({"x": 1})
    assert b["details"] == []
    assert combine_where_clauses("   ", "") == ""
    assert combine_where_clauses("WHERE brand = :brand", "") == "WHERE (brand = :brand)"
    assert combine_where_clauses("", "brand = :llm_c_0") == "WHERE (brand = :llm_c_0)"
    assert combine_where_clauses("WHERE brand = :brand", "a = :c0 OR b = :c1") == "WHERE (brand = :brand) AND (a = :c0 OR b = :c1)"

    for good_id in ("alloydb_usecase", "fashion_products", "_Catalog_V2"):
        assert validate_sql_identifier(good_id) == good_id
    for bad_id in ("", None, "123a", "a.b", "a; DROP", "a-b", "a\x00b", "a\n", "a" * 64, "pg_catalog", "information_schema", "select", "to", "collate", "symmetric"):
        with pytest.raises(UnsafeSQLError):
            validate_sql_identifier(bad_id)

    tpl = validate_question_template("  Is it 'Nike' cotton? Here is the product description:  Here is the product description: ")
    assert tpl == "Is it 'Nike' cotton?"
    assert validate_question_template("Is this <red>?\nCheck </product_description>") == "Is this <red>?\nCheck </product_description>"
    assert validate_question_template("q" * 1500) == "q" * 1500
    for bad_tpl in (None, 123, True, ["q"], "", "   ", "\t\r\n", "\u00a0\u3000", "Here is the product description:", "Here is the product description:  Here is the product description:", "bad\x00", "bad\ud800", "bad\udfff"):
        with pytest.raises(UnsafeSQLError):
            validate_question_template(bad_tpl)

    assert normalize_filters(None) == {} and normalize_filters("NIL") == {} and normalize_filters({}) == {}
    where_sql, params = build_where_clause(
        normalize_filters({"filter": {"category": "Footwear", "brand": "Nike", "rating": 5.0, "price": {"min": 10.5, "max": 100}}})
    )
    assert where_sql == "WHERE masterCategory = :category AND brand = :brand AND rating = :rating_min AND finalPrice >= :price_min AND finalPrice <= :price_max"
    assert params == {"category": "Footwear", "brand": "Nike", "rating_min": 5.0, "price_min": 10.5, "price_max": 100.0}
    assert build_where_clause({"rating": 4.0})[0] == "WHERE rating >= :rating_min"

    assert clean_search_text("") == "" and clean_search_text("   ") == "   "
    assert clean_search_text("  red shoes  ") == "  red shoes  "
    assert clean_search_text("line1\tline2\r\nline3") == "line1\tline2\r\nline3"
    assert clean_search_text("x" * 2500) == "x" * 2500
    for bad_txt in (None, 123, True, ["shoes"], "a\x00b", "a\ud800b", "a\udfffb"):
        with pytest.raises(UnsafeSQLError):
            clean_search_text(bad_txt)
    assert len(tokenize_sql(" ".join(["a"] * 1024))) == 1024
    with pytest.raises(UnsafeSQLError):
        tokenize_sql(" ".join(["a"] * 1025))
    with pytest.raises(UnsafeSQLError):
        tokenize_sql("SELECT " + "a" * 9000)


def test_utf16_lone_surrogates_rejected_without_poisoning_pg_pool(client: TestClient, canary_secret: str) -> None:
    resp_q = client.post("/search", content=b'{"question": "running shoes \\ud800", "filters": {}}', headers={"Content-Type": "application/json"})
    assert resp_q.status_code == 400 and resp_q.json() == {"detail": "Invalid search question."}
    for payload in (b'{"question": "shoes", "filters": {"brand": "Nike\\ud800"}}', b'{"question": "shoes", "filters": {"category": "Footwear\\udfff"}}'):
        body_f = _assert_clean_search_response(
            client.post("/search", content=payload, headers={"Content-Type": "application/json"}), canary_secret=canary_secret
        )
        assert body_f["answer"] == {"sql_command": "", "details": []}
    ok_body = _assert_clean_search_response(
        client.post("/search", json={"question": "Nike running shoes", "filters": {"brand": "Nike"}}), canary_secret=canary_secret
    )
    assert {r["productDisplayName"] for r in ok_body["answer"]["details"]} == {"Nike Men Black Running Shoes", "Nike Women Red Casual Shoes"}
    assert client.get("/list-brands").json() == {"brands": ["Biba", "Levis", "Nike", "Puma"]}


# =============================================================================
# 5. execute_readonly (PG17 State, AUTOCOMMIT, Writes, nextval, Timeout)
# =============================================================================


def test_execute_readonly_session_state_and_pg17_enforcement(
    pg17_cluster: dict[str, object], pg_engine: Engine, reset_db: Any,
    seq_last_value: Callable[[], int | None], product_final_price: Callable[[int], Decimal],
) -> None:
    del reset_db
    default_state = execute_readonly(
        pg_engine,
        sa.text("SELECT current_setting('transaction_read_only') AS ro, current_setting('statement_timeout') AS st"),
    )
    assert default_state == [{"ro": "on", "st": "0"}]
    timed_state = execute_readonly(
        pg_engine,
        sa.text("SELECT current_setting('transaction_read_only') AS ro, current_setting('standard_conforming_strings') AS scs, current_setting('statement_timeout') AS st"),
        timeout_ms=10_000,
    )
    assert timed_state == [{"ro": "on", "scs": "on", "st": "10s"}]
    with pg_engine.begin() as conn:
        assert conn.execute(sa.text("SHOW transaction_read_only")).scalar() == "off"
        assert conn.execute(sa.text("SHOW statement_timeout")).scalar() == "0"
    with pytest.raises(DBAPIError):
        execute_readonly(pg_engine, sa.text("SELECT 1 / 0"))
    assert execute_readonly(pg_engine, sa.text("SELECT 42 AS v"))[0]["v"] == 42

    ac_engine = sa.create_engine(str(pg17_cluster["db_url"]), isolation_level="AUTOCOMMIT")
    try:
        with pytest.raises(UnsafeSQLError, match="READ ONLY"):
            execute_readonly(ac_engine, sa.text("SELECT nextval('public.security_canary_seq')"))
    finally:
        ac_engine.dispose()
    assert seq_last_value() is None

    price_before = product_final_price(1)
    with pytest.raises(DBAPIError):
        execute_readonly(pg_engine, sa.text(f"UPDATE {FQ} SET finalPrice = 0 WHERE id = 1"))
    assert product_final_price(1) == price_before
    with pytest.raises(DBAPIError):
        execute_readonly(pg_engine, sa.text("SELECT nextval('public.security_canary_seq')"))
    assert seq_last_value() is None

    for bad_timeout in (True, False, 0, -50, 600_001, 100.5, "1000; DROP TABLE x"):
        with pytest.raises(UnsafeSQLError):
            execute_readonly(pg_engine, sa.text("SELECT 1"), timeout_ms=bad_timeout)  # type: ignore[arg-type]
    bound_stmt = sa.text("SELECT :v AS v").bindparams(sa.bindparam("v", value=99, type_=sa.Integer()))
    assert execute_readonly(pg_engine, bound_stmt, timeout_ms=None) == [{"v": 99}]
    with pytest.raises((UnsafeSQLError, sa.exc.SQLAlchemyError, TypeError)):
        execute_readonly(pg_engine, "SELECT 1")  # type: ignore[arg-type]

    t0 = time.monotonic()
    with pytest.raises(DBAPIError) as exc_info:
        execute_readonly(pg_engine, sa.text("SELECT pg_sleep(2)"), timeout_ms=100)
    assert time.monotonic() - t0 < 1.5
    assert "57014" in str(exc_info.value).lower() or "statement timeout" in str(exc_info.value).lower()


@pytest.mark.parametrize("show_value", ["off", None, ""])
def test_execute_readonly_mock_show_off_blocks_stmt(show_value: Any) -> None:
    executed: list[str] = []

    class _FakeConn:
        def execute(self, stmt: Any, params: Any = None) -> MagicMock:
            del params
            executed.append(str(stmt))
            res = MagicMock()
            res.scalar.return_value = show_value if "SHOW transaction_read_only" in str(stmt) else None
            return res

    fake_engine = MagicMock(spec=Engine)
    fake_engine.begin.side_effect = contextmanager(lambda: (yield _FakeConn()))
    with pytest.raises(UnsafeSQLError, match="READ ONLY"):
        execute_readonly(fake_engine, sa.text("SELECT 'SHOULD_NEVER_EXECUTE'"))
    assert not any("statement_timeout" in s for s in executed)
    assert not any("SHOULD_NEVER_EXECUTE" in s for s in executed)


# =============================================================================
# 6. format_display_sql (Named Dialect %/\ Fidelity & sqlparse DoS Resilience)
# =============================================================================


def test_format_display_sql_dialect_fidelity_and_dos_resilience() -> None:
    stmt = sa.text("SELECT :s1, :s2, :pat, :price, :yr, :dt, :ts").bindparams(
        sa.bindparam("s1", value=r"50%(off)s shirt C:\mens", type_=sa.String()),
        sa.bindparam("s2", value="Levi's", type_=sa.String()),
        sa.bindparam("pat", value="%nike%", type_=sa.String()),
        sa.bindparam("price", value=Decimal("49.99"), type_=sa.Numeric()),
        sa.bindparam("yr", value=2012, type_=sa.Integer()),
        sa.bindparam("dt", value=date(2020, 5, 15), type_=sa.Date()),
        sa.bindparam("ts", value=datetime(2020, 5, 15, 12, 30, 0), type_=sa.DateTime()),
    )
    rendered = format_display_sql(stmt)
    assert r"'50%(off)s shirt C:\mens'" in rendered and "%%" not in rendered and r"\\" not in rendered
    assert "'Levi''s'" in rendered and "'%nike%'" in rendered and "49.99" in rendered and "2020-05-15" in rendered
    assert ":x" in format_display_sql(sa.text("select * from t where id = :x").bindparams(sa.bindparam("x", value=object())))

    # Normal lowercase SQL is reindented without uppercasing keywords; backslash, >64 parens, and >4096 chars bypass sqlparse.
    normal_out = format_display_sql(sa.text("select id from t where a = :p").bindparams(sa.bindparam("p", value="ok", type_=sa.String())))
    assert normal_out.startswith("select ") and "SELECT " not in normal_out and "\nfrom t\nwhere a = 'ok'" in normal_out
    for depth in (250, 990):
        adv = sa.text("select id from t where a = :q").bindparams(sa.bindparam("q", value="\\'" + "(" * depth + "shoes" + ")" * depth, type_=sa.String()))
        t0 = time.monotonic()
        out = format_display_sql(adv)
        assert time.monotonic() - t0 < 1.0 and "shoes" in out and out.startswith("select id from t where ") and "\n" not in out
    parens_only = sa.text("select id from t where a = :p").bindparams(sa.bindparam("p", value="(" * 65 + "shoes" + ")" * 65, type_=sa.String()))
    t0 = time.monotonic()
    parens_out = format_display_sql(parens_only)
    assert time.monotonic() - t0 < 1.0 and "shoes" in parens_out and parens_out.startswith("select id from t where ") and "\n" not in parens_out
    long_out = format_display_sql(sa.text("select id from t where a = :p").bindparams(sa.bindparam("p", value="A" * 5000, type_=sa.String())))
    assert "A" * 5000 in long_out and long_out.startswith("select id from t where ") and "\n" not in long_out
    t0 = time.monotonic()
    _, nla_disp = build_safe_nltosql_query(
        f"SELECT * FROM {FQ} WHERE year = 2012", schema_name=SCHEMA_NAME, table_name=TABLE_NAME,
        ui_where_sql="WHERE masterCategory = :category AND brand = :brand",
        ui_params={"category": "\\'" + "(" * 250, "brand": "\\'" + ")" * 250},
    )
    assert time.monotonic() - t0 < 1.0 and nla_disp


# =============================================================================
# 7. FastAPI & search_case.py Security Regressions
# =============================================================================


@pytest.mark.parametrize(
    "router_output,expected_type",
    [
        ({"mode": "unexpected_mode", "reason": "unknown", "decision": {}}, "unknown"),
        (None, "unknown"), ([], "unknown"), ({}, "unknown"),
        ({"mode": None, "reason": None, "decision": None}, "unknown"),
        ({"mode": "  AI.IF  ", "reason": 123, "decision": {"parameters": ["non-dict"]}}, "ai.if"),
        ({"mode": "", "reason": None, "decision": {"selected_strategy": "vector"}}, "vector"),
        ({"mode": "  REJECT  ", "reason": None, "decision": {}}, "reject"),
    ],
)
def test_api_unknown_search_type_and_malformed_router_returns_valid_dict(
    client: TestClient, canary_secret: str, router_output: Any, expected_type: str
) -> None:
    body = _assert_clean_search_response(_post_with_router(client, router_output), canary_secret=canary_secret)
    assert body["search_type"] == expected_type


def test_api_question_validation_and_sanitized_errors(
    client: TestClient, canary_secret: str
) -> None:
    # Empty/whitespace, \t/\r/\n, and >2000-char questions return HTTP 200; app.py strips request.question.
    seen_questions: list[str] = []
    orig_init = IdentifySearchType.__init__

    def _spy_init(self: IdentifySearchType, question: str, engine: Engine) -> None:
        seen_questions.append(question)
        orig_init(self, question, engine)

    with patch.object(IdentifySearchType, "__init__", _spy_init):
        _assert_clean_search_response(
            client.post("/search", json={"question": "  Nike running shoes \t\r\n ", "filters": {}}), canary_secret=canary_secret
        )
    assert seen_questions == ["Nike running shoes"]

    for ok_q in ("", "   ", "   \t\r\n", "running\tshoes\r\nmen", "x" * 2005):
        _assert_clean_search_response(client.post("/search", json={"question": ok_q, "filters": {}}), canary_secret=canary_secret)

    for bad_q in ("bad\x00q", "bad\ud800q", "bad\udfffq"):
        with patch("services.search_case.IdentifySearchType.get_search_type") as mock_router:
            r400 = client.post(
                "/search",
                content=json.dumps({"question": bad_q, "filters": {}}).encode("ascii"),
                headers={"Content-Type": "application/json"},
            )
            mock_router.assert_not_called()
        assert r400.status_code == 400 and r400.json() == {"detail": "Invalid search question."}

    for raw_body in (b'{"question":"shoes","filters":{"rating":NaN}}', b'{"question":"shoes","filters":{"price":{"max":Infinity}}}'):
        r_raw = client.post("/search", content=raw_body, headers={"Content-Type": "application/json"})
        assert r_raw.status_code in (200, 422) and "Traceback" not in r_raw.text
        if r_raw.status_code == 200:
            b_raw = _assert_clean_search_response(r_raw, canary_secret=canary_secret)
            assert b_raw["answer"] == {"sql_command": "", "details": []}

    r_bad_f = client.post("/search", json={"question": "shoes", "filters": {"rating": f"not_a_number_{UPSTREAM_SECRET_MARKER}"}})
    assert r_bad_f.status_code == 500 and r_bad_f.json() == {"detail": "An internal error occurred while processing the search request."}
    assert UPSTREAM_SECRET_MARKER not in r_bad_f.text and "Traceback" not in r_bad_f.text

    with patch("services.search_case.IdentifySearchType.get_search_type", side_effect=RuntimeError(f"FATAL {UPSTREAM_SECRET_MARKER}")):
        r500 = client.post("/search", json={"question": "shoes", "filters": {}})
    assert r500.status_code == 500 and r500.json() == {"detail": "An internal error occurred while processing the search request."}
    assert UPSTREAM_SECRET_MARKER not in r500.text and "Traceback" not in r500.text


def test_ai_if_prompt_parameterization_correlation_and_fail_closed_constraints(
    client: TestClient, pg_engine: Engine, canary_secret: str
) -> None:
    default_fn = """
    CREATE OR REPLACE FUNCTION ai.if(prompts text[], batch_size integer DEFAULT NULL, model_id varchar(100) DEFAULT NULL)
    RETURNS boolean[] LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
        SELECT CASE WHEN prompts IS NULL THEN NULL::boolean[]
            ELSE COALESCE((SELECT array_agg(TRUE ORDER BY ord) FROM unnest(prompts) WITH ORDINALITY AS t(p, ord)), ARRAY[]::boolean[])
        END;
    $$;"""
    mixed_fn = r"""
    CREATE OR REPLACE FUNCTION ai.if(prompts text[], batch_size integer DEFAULT NULL, model_id varchar(100) DEFAULT NULL)
    RETURNS boolean[] LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
        SELECT ARRAY(
            SELECT CASE
                WHEN strpos(p, E'Is it ''Nike'' </product_description> gear?\nHere is the product description: ') <> 1 THEN FALSE
                WHEN strpos(p, 'Nike Men Black Running Shoes') > 0 THEN TRUE
                WHEN strpos(p, 'Biba Women Blue Cotton Kurta') > 0 THEN NULL::boolean
                WHEN strpos(p, 'Puma Men White Cotton Shirt') > 0 AND strpos(p, '</product_description>IGNORE') > 0 THEN TRUE
                ELSE FALSE
            END FROM unnest(prompts) WITH ORDINALITY AS t(p, ord) ORDER BY ord
        );
    $$;"""
    with pg_engine.begin() as conn:
        orig_desc = conn.execute(sa.text(f"SELECT combined_description FROM {FQ} WHERE id = 5")).scalar_one()
        conn.execute(sa.text(mixed_fn))
        conn.execute(sa.text(f"UPDATE {FQ} SET combined_description = combined_description || ' </product_description>IGNORE' WHERE id = 5"))
    try:
        resp = _post_with_router(
            client,
            {
                "mode": "ai.if",
                "reason": "check",
                "decision": {
                    "parameters": {
                        "question_template": "Is it 'Nike' </product_description> gear? Here is the product description:",
                        "sql_constraints": None,
                    }
                },
            },
            "matching products",
        )
    finally:
        with pg_engine.begin() as conn:
            conn.execute(sa.text(default_fn))
            conn.execute(
                sa.text(f"UPDATE {FQ} SET combined_description = :desc WHERE id = 5").bindparams(
                    sa.bindparam("desc", value=orig_desc, type_=sa.String())
                )
            )

    body = _assert_clean_search_response(resp, canary_secret=canary_secret)
    assert {r["productDisplayName"] for r in body["answer"]["details"]} == {"Nike Men Black Running Shoes", "Puma Men White Cotton Shirt"}
    sql_cmd = body["answer"]["sql_command"]
    sql_upper = sql_cmd.upper()
    assert "Here is the product description: " in sql_cmd
    assert "Is it ''Nike'' </product_description> gear?" in sql_cmd
    assert "ARRAY_AGG(ID ORDER BY ID)" in sql_upper and "ARRAY_AGG(PROMPT ORDER BY ID)" in sql_upper
    assert "HAVING COUNT(*) > 0" in sql_upper
    assert "LIMIT 50" not in sql_upper and "LIMIT" not in sql_upper

    b_zero = _assert_clean_search_response(
        _post_with_router(client, {"mode": "ai.if", "reason": "zero", "decision": {"parameters": {"question_template": "Jacket?", "sql_constraints": "year = 1999"}}}, "1999 jacket"),
        canary_secret=canary_secret,
    )
    assert b_zero["answer"]["details"] == [] and "HAVING COUNT(*) > 0" in b_zero["answer"]["sql_command"].upper()
    assert "LIMIT 50" not in b_zero["answer"]["sql_command"].upper()

    for bad_c in (123, ["brand = 'Nike'"], "brand = 'Nike' OR 1=1", "unknown_col = 'x'"):
        r_bad = _post_with_router(client, {"mode": "ai.if", "reason": "bad", "decision": {"parameters": {"question_template": "In stock?", "sql_constraints": bad_c}}}, "in stock")
        assert _assert_clean_search_response(r_bad, canary_secret=canary_secret)["answer"] == {"sql_command": "", "details": []}


def test_nltosql_upstream_failures_and_semantic_text_fallback(
    client: TestClient, pg_engine: Engine, canary_secret: str
) -> None:
    svc = AlloyDbSearchTypes(pg_engine)
    with patch.object(AlloyDbSearchTypes, "get_access_token", return_value=None), patch("services.search_case.requests.post") as mp:
        assert asyncio.run(svc.nltosql_search("Puma", {})) == {"sql_command": "", "details": []}
        mp.assert_not_called()

    for bad in (
        requests.Timeout(f"timeout {UPSTREAM_SECRET_MARKER}"),
        MagicMock(status_code=500, text=UPSTREAM_SECRET_MARKER),
        MagicMock(status_code=200, json=MagicMock(return_value={"explanation": UPSTREAM_SECRET_MARKER})),
        MagicMock(status_code=200, json=MagicMock(return_value={"generatedQuery": "   "})),
        MagicMock(status_code=200, json=MagicMock(return_value={"generatedQuery": 123})),
    ):
        kw = {"side_effect": bad} if isinstance(bad, Exception) else {"return_value": bad}
        with (
            patch("services.search_case.IdentifySearchType.get_search_type", return_value={"mode": "nl_to_sql", "reason": "r", "decision": {}}),
            patch.object(AlloyDbSearchTypes, "get_access_token", return_value="tok"),
            patch("services.search_case.requests.post", **kw),
        ):
            b_fb = _assert_clean_search_response(client.post("/search", json={"question": "Levis belt", "filters": {"brand": "Levis"}}), canary_secret=canary_secret)
        assert b_fb["search_type"] == "vector" and [r["productDisplayName"] for r in b_fb["answer"]["details"]] == ["Levis Men Brown Leather Belt"]

    for mode in ("vector", "hybrid"):
        b_sem = _assert_clean_search_response(
            _post_with_router(client, {"mode": mode, "reason": "r", "decision": {"parameters": {"semantic_text": "bad\x00", "sql_constraints": "brand = 'Puma'"}}}, "Puma shirt"),
            canary_secret=canary_secret,
        )
        assert "'Puma shirt'" in b_sem["answer"]["sql_command"]
        assert [r["productDisplayName"] for r in b_sem["answer"]["details"]] == ["Puma Men White Cotton Shirt"]


def test_prompt_hardening_and_cwe117_log_redaction(
    client: TestClient, pg_engine: Engine, canary_secret: str, caplog: pytest.LogCaptureFixture
) -> None:
    user_q = "running shoes for men"
    router = IdentifySearchType(user_q, pg_engine)
    prompt = router.search_strategy_prompt()
    assert '"sql_query":' not in prompt and "WITH base AS" not in prompt
    assert 'Never output "sql_query"' in prompt
    assert f'USER QUERY: "{user_q}"' in prompt

    marker = "SENSITIVE_QUERY_MARKER_987"
    nla_resp = MagicMock(status_code=200)
    nla_resp.json.return_value = {"generatedQuery": f"SELECT * FROM {FQ} WHERE brand = 'Nike'"}
    with caplog.at_level(logging.DEBUG):
        for mode, params in (
            ("vector", {"semantic_text": marker, "sql_constraints": "brand = 'Nike'"}),
            ("hybrid", {"semantic_text": marker, "sql_constraints": "brand = 'Nike'"}),
            ("ai.if", {"question_template": f"Matches {marker}?", "sql_constraints": "brand = 'Nike'"}),
            ("nl_to_sql", {}),
        ):
            with (
                patch("services.search_case.IdentifySearchType.get_search_type", return_value={"mode": mode, "reason": "r", "decision": {"parameters": params}}),
                patch.object(AlloyDbSearchTypes, "get_access_token", return_value="tok"),
                patch("services.search_case.requests.post", return_value=nla_resp),
            ):
                _assert_clean_search_response(client.post("/search", json={"question": f"shoes {marker}", "filters": {}}), canary_secret=canary_secret)
        for nl_q in ("shoes\nFAKE_LOG", "shoes\rFAKE_LOG"):
            _assert_clean_search_response(client.post("/search", json={"question": nl_q, "filters": {}}), canary_secret=canary_secret)
        for nl_f in ({"brand": "Nike\nFAKE_LOG"}, {"category": "Footwear\rFAKE_LOG"}):
            nl_f_body = _assert_clean_search_response(
                client.post("/search", json={"question": "shoes", "filters": nl_f}), canary_secret=canary_secret
            )
            assert nl_f_body["answer"]["sql_command"] != "" and nl_f_body["answer"]["details"] == []
        bad_mode_body = _assert_clean_search_response(
            _post_with_router(client, {"mode": "vector\nFAKE_LOG", "reason": "r", "decision": {}}), canary_secret=canary_secret
        )
        assert bad_mode_body["search_type"] == "unknown"
    all_msgs = [rec.getMessage() for rec in caplog.records]
    assert all_msgs
    for msg in all_msgs:
        assert marker not in msg and "FAKE_LOG" not in msg and "\n" not in msg and "\r" not in msg
        assert TABLE_NAME not in msg and "SELECT " not in msg.upper()
