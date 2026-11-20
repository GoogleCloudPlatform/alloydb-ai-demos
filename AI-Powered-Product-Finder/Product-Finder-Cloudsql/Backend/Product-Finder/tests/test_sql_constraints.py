"""Tests for parameterized AI filter constraints and generic error responses."""
import asyncio
import os
from pathlib import Path
import sys
import types
from unittest import mock

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine

for _k, _v in {"VECTOR_THRESHOLD": "0.8", "HYBRID_THRESHOLD": "0.05", "RATING_THRESHOLD": "4",
               "CLOUDSQL_SCHEMA_NAME": "cloudsql_demo", "TABLE_NAME": "fashion_products"}.items():
    os.environ.setdefault(_k, _v)
sys.path.insert(0, os.environ.get("PRODUCT_FINDER_BACKEND_DIR", str(Path(__file__).resolve().parent.parent)))
for _mod in ("vertexai", "vertexai.preview", "vertexai.preview.generative_models", "google.cloud.sql.connector"):
    sys.modules.setdefault(_mod, mock.MagicMock())

import app as app_module  # noqa: E402
import service  # noqa: E402

UNSAFE_CONSTRAINTS = [
    "CAST((SELECT current_user) AS INT) > 0",
    "brand = 'x'; DROP TABLE t; --",
    "brand = E'x\\' OR 1=1 --'",
    "brand::text = 'x'",
    "pg_sleep(5) = 0",
    "brand = 'x') OR (1=1",
    "(" * 6 + "brand = 'x'" + ")" * 6,
    "brand = '" + "x" * 1100 + "'",
    "rating = 1" + "0" * 30,
    ["brand = 'x'"],
]


class _FakeEngine:
    """Records executed SQL instead of touching a database."""
    dialect = create_engine("postgresql+pg8000://").dialect

    def __init__(self, error=None):
        self.executed, self.error = [], error

    def connect(self):
        if self.error:
            raise self.error
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query):
        self.executed.append((str(query), query.compile().params))
        return types.SimpleNamespace(fetchall=list, keys=list)


@pytest.mark.parametrize("method", ["vector_search", "hybrid_search"])
def test_constraints_are_bound_and_scoped(method):
    search, engine = getattr(service.CloudSQLSearchTypes(), method), _FakeEngine()
    search(engine, "jeans", {"brand": "Levi's"}, "brand = 'Levi''s' AND finalPrice <= 100", "jeans")
    search(engine, "jeans", {"brand": "Nike"}, "brand = 'Nike' OR 1=1", "jeans")
    (sql, params), (scoped_sql, _) = engine.executed
    assert "AND (brand = :llm_constraint_0 AND finalPrice <= :llm_constraint_1)" in sql
    assert (params["llm_constraint_0"], params["llm_constraint_1"]) == ("Levi's", 100)
    assert "brand = :brand AND (brand = :llm_constraint_0 OR :llm_constraint_1 = :llm_constraint_2)" in scoped_sql


@pytest.mark.parametrize("method", ["vector_search", "hybrid_search"])
@pytest.mark.parametrize("constraint", UNSAFE_CONSTRAINTS)
def test_unsafe_constraints_are_rejected(method, constraint):
    engine = _FakeEngine()
    with pytest.raises(ValueError):
        getattr(service.CloudSQLSearchTypes(), method)(engine, "jeans", {}, constraint, "jeans")
    assert not engine.executed


@pytest.mark.parametrize("method", ["vector_search", "hybrid_search"])
def test_db_errors_are_not_echoed(method):
    res = getattr(service.CloudSQLSearchTypes(), method)(_FakeEngine(RuntimeError("db_secret")), "q", {}, None, None)
    assert "db_secret" not in str(res)


def test_api_rejects_unsafe_constraints_with_generic_500(monkeypatch):
    engine = _FakeEngine()
    decision = {"parameters": {"sql_constraints": "brand = 'x'; DROP TABLE t; --", "semantic_text": "x"}}
    monkeypatch.setattr(app_module.IdentifySearchTypes, "get_search_type",
                        lambda self, q: {"mode": "vector", "reason": "r", "decision": decision})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(app_module.search(app_module.CloudSqlSearchRequest(question="q", filters={}), engine))
    assert exc.value.status_code == 500 and exc.value.detail == "Internal server error"
    assert not engine.executed
