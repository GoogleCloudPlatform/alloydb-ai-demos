"""Regression tests for crud.get_alloydb_sql_summary parameterization."""

import importlib.util
import json
import os
import sys
import types
import unittest
from unittest import mock

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
  sys.path.insert(0, _BACKEND_DIR)


def _install_missing_dependency_stubs() -> None:
  """Stub optional third-party imports so tests run hermetically with stdlib."""
  if "asyncpg" not in sys.modules and importlib.util.find_spec("asyncpg") is None:
    asyncpg_stub = types.ModuleType("asyncpg")
    asyncpg_stub.Pool = object
    sys.modules["asyncpg"] = asyncpg_stub

  if "google.genai.types" not in sys.modules:
    try:
      import google.genai.types  # noqa: F401
    except ImportError:
      google_mod = sys.modules.get("google")
      if google_mod is None:
        try:
          import google as google_mod  # noqa: F401
        except ImportError:
          google_mod = types.ModuleType("google")
          google_mod.__path__ = []
          sys.modules["google"] = google_mod

      genai_mod = sys.modules.get("google.genai")
      if genai_mod is None:
        genai_mod = types.ModuleType("google.genai")
        genai_mod.__path__ = []
        sys.modules["google.genai"] = genai_mod
        setattr(google_mod, "genai", genai_mod)

      types_mod = types.ModuleType("google.genai.types")
      types_mod.HttpOptions = object
      types_mod.Part = object
      sys.modules["google.genai.types"] = types_mod
      setattr(genai_mod, "types", types_mod)

  if "langchain_core.messages" not in sys.modules:
    try:
      import langchain_core.messages  # noqa: F401
    except ImportError:
      lc_mod = sys.modules.get("langchain_core")
      if lc_mod is None:
        lc_mod = types.ModuleType("langchain_core")
        lc_mod.__path__ = []
        sys.modules["langchain_core"] = lc_mod
      messages_mod = types.ModuleType("langchain_core.messages")
      messages_mod.BaseMessage = object
      sys.modules["langchain_core.messages"] = messages_mod
      setattr(lc_mod, "messages", messages_mod)

  if "config" not in sys.modules:
    has_config_deps = (
        importlib.util.find_spec("dotenv") is not None
        and importlib.util.find_spec("pydantic_settings") is not None
        and all(
            key in os.environ
            for key in ("DATABASE_URL", "DATABASE_URL_V1", "GOOGLE_API_KEY")
        )
    )
    if has_config_deps:
      import config  # noqa: F401
    else:
      config_stub = types.ModuleType("config")
      config_stub.settings = types.SimpleNamespace(nl_config_name="google_io")
      sys.modules["config"] = config_stub

  if "models" not in sys.modules and importlib.util.find_spec("pydantic") is None:
    models_stub = types.ModuleType("models")

    class _BaseStub:
      def __init__(self, **kwargs):
        for key, value in kwargs.items():
          setattr(self, key, value)

    for name in (
        "ExecuteNlQueryResponse",
        "ExecuteParameterizedQueryResponse",
        "GetSqlResponse",
        "GetSqlResult",
        "GetSqlSummaryResponse",
        "PredictRowResult",
        "UserDetails",
    ):
      setattr(models_stub, name, type(name, (_BaseStub,), {}))
    sys.modules["models"] = models_stub


_install_missing_dependency_stubs()

import crud  # noqa: E402


class _FakeConnection:
  """Minimal asyncpg connection double recording fetch calls."""

  def __init__(self, records):
    self._records = records
    self.calls = []

  async def fetch(self, sql, *args):
    self.calls.append((sql, args))
    return self._records


class _FakeAcquireContext:
  """Async context manager returned by _FakePool.acquire()."""

  def __init__(self, conn):
    self._conn = conn

  async def __aenter__(self):
    return self._conn

  async def __aexit__(self, exc_type, exc, tb):
    return False


class _FakePool:
  """Minimal asyncpg pool double yielding a _FakeConnection."""

  def __init__(self, conn):
    self._conn = conn

  def acquire(self):
    return _FakeAcquireContext(self._conn)


class TestGetAlloydbSqlSummary(unittest.IsolatedAsyncioTestCase):
  """Tests bound-parameter SQL execution in crud.get_alloydb_sql_summary."""

  async def test_parameterizes_special_character_queries(self):
    cases = [
        ("plain", "best moisturizer for dry skin"),
        ("single_quote", "what's the gentlest cleanser?"),
        ("backslash_quote", r"sample\'value"),
        ("double_backslash_quote", r"sample\\'value"),
        ("trailing_backslash", "sample\\"),
        ("comment_and_semicolon", "sample; -- trailing note"),
        ("placeholder_literal", "compare $1 and $2 options"),
        ("combined_special_chars", r"alpha\'beta\\'; -- $1"),
    ]
    payload = {"answer": "summary text"}

    for label, query in cases:
      with self.subTest(case=label):
        conn = _FakeConnection(
            [{"get_sql_summary": json.dumps(payload)}]
        )
        fake_settings = types.SimpleNamespace(nl_config_name="test_nl_config")

        with (
            mock.patch.object(crud, "pool", _FakePool(conn)),
            mock.patch.object(crud, "settings", fake_settings),
        ):
          result = await crud.get_alloydb_sql_summary(query)

        self.assertEqual(len(conn.calls), 1)
        sql, args = conn.calls[0]
        self.assertEqual(
            " ".join(sql.split()),
            "SELECT alloydb_ai_nl.get_sql_summary($1, $2);",
        )
        self.assertEqual(args, ("test_nl_config", query))
        self.assertNotIn("E'", sql)
        self.assertNotIn("test_nl_config", sql)
        self.assertNotIn(query, sql)
        self.assertEqual(result.get_sql_summary, payload)

  async def test_parameterizes_nl_config_name(self):
    config_name = "cfg'with\\special; -- $1"
    query = "daily skincare summary"
    payload = {"answer": "ok"}
    conn = _FakeConnection([{"get_sql_summary": json.dumps(payload)}])
    fake_settings = types.SimpleNamespace(nl_config_name=config_name)

    with (
        mock.patch.object(crud, "pool", _FakePool(conn)),
        mock.patch.object(crud, "settings", fake_settings),
    ):
      result = await crud.get_alloydb_sql_summary(query)

    self.assertEqual(len(conn.calls), 1)
    sql, args = conn.calls[0]
    self.assertEqual(
        " ".join(sql.split()),
        "SELECT alloydb_ai_nl.get_sql_summary($1, $2);",
    )
    self.assertEqual(args, (config_name, query))
    self.assertNotIn(config_name, sql)
    self.assertEqual(result.get_sql_summary, payload)

  async def test_raises_when_pool_uninitialized(self):
    with mock.patch.object(crud, "pool", None):
      with self.assertRaises(RuntimeError):
        await crud.get_alloydb_sql_summary("best cleanser")

  async def test_returns_none_on_invalid_json(self):
    conn = _FakeConnection([{"get_sql_summary": "not valid json"}])
    fake_settings = types.SimpleNamespace(nl_config_name="test_nl_config")

    with (
        mock.patch.object(crud, "pool", _FakePool(conn)),
        mock.patch.object(crud, "settings", fake_settings),
    ):
      result = await crud.get_alloydb_sql_summary(r"sample\'value")

    self.assertIsNone(result)
    self.assertEqual(len(conn.calls), 1)
    sql, args = conn.calls[0]
    self.assertEqual(
        " ".join(sql.split()),
        "SELECT alloydb_ai_nl.get_sql_summary($1, $2);",
    )
    self.assertEqual(args, ("test_nl_config", r"sample\'value"))


if __name__ == "__main__":
  unittest.main()
