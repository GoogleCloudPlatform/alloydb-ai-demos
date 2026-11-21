"""Regression tests for crud.get_alloydb_sql_summary parameterization."""

import json
import os
import sys
import types
import unittest
from unittest import mock

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_STUBS = {
    "asyncpg": mock.MagicMock(),
    "config": mock.MagicMock(),
    "models": mock.MagicMock(GetSqlSummaryResponse=types.SimpleNamespace),
    "google": mock.MagicMock(),
    "google.genai": mock.MagicMock(),
    "google.genai.types": mock.MagicMock(),
}
with mock.patch.object(sys, "path", [_BACKEND_DIR, *sys.path]):
  with mock.patch.dict(sys.modules, _STUBS):
    import crud  # noqa: E402

_EXPECTED_SQL = "SELECT alloydb_ai_nl.get_sql_summary($1, $2);"


class TestGetAlloydbSqlSummary(unittest.IsolatedAsyncioTestCase):

  async def test_binds_config_and_query_as_parameters(self):
    payload = {"answer": "summary text"}
    records = [{"get_sql_summary": json.dumps(payload)}]
    cases = [
        ("plain", "test_nl_config", "best moisturizer for dry skin"),
        ("single_quote", "test_nl_config", "what's the gentlest cleanser?"),
        ("backslash_quote", "test_nl_config", r"sample\'value"),
        ("trailing_backslash", "test_nl_config", "sample\\"),
        ("combined_payload", "test_nl_config", r"alpha\'beta\\'; -- $1"),
        ("special_config_name", "cfg'with\\special; -- $1", "daily summary"),
    ]

    for label, config_name, query in cases:
      with self.subTest(case=label):
        conn = mock.MagicMock(fetch=mock.AsyncMock(return_value=records))
        pool = mock.MagicMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        settings = types.SimpleNamespace(nl_config_name=config_name)

        with (
            mock.patch.object(crud, "pool", pool),
            mock.patch.object(crud, "settings", settings),
        ):
          result = await crud.get_alloydb_sql_summary(query)

        conn.fetch.assert_awaited_once_with(mock.ANY, config_name, query)
        self.assertEqual(conn.fetch.await_args.args[0].strip(), _EXPECTED_SQL)
        self.assertEqual(result.get_sql_summary, payload)


if __name__ == "__main__":
  unittest.main()
