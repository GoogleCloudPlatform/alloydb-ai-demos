"""Real-dependency unit tests for Skincare Backend session user scoping."""

import os
import pathlib
import sys
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = str(pathlib.Path(__file__).resolve().parent)
if BACKEND_DIR not in sys.path:
  sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
os.environ.setdefault("DATABASE_URL_V1", "postgresql://user:pass@localhost:5433/db_v1")
os.environ.setdefault("GOOGLE_API_KEY", "test-api-key")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "false")
os.environ.setdefault("LANGSMITH_TRACING", "false")

from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import crud
import graph
import llm_interface
import logic
import main
import models
import tools


def _llm_visible_params(tool_obj: Any) -> set[str]:
  schema = tool_obj.tool_call_schema
  if isinstance(schema, dict):
    return set(schema.get("properties", {}).keys())
  return set(schema.model_json_schema().get("properties", {}).keys())


class OrderSessionValidationTest(unittest.IsolatedAsyncioTestCase):
  """Verifies server-bound session user_id across tools, graph, and endpoints."""

  def test_all_six_tool_schemas_hide_user_id_from_llm(self) -> None:
    expected = {
        "orderCheckout": {"product_name", "price"},
        "orderInsert": {"product_name", "price"},
        "getResultsOnly": {"query"},
        "getSummaryOnly": {"query"},
        "getSummaryAndResults": {"query"},
        "get_product_price": {"product_name"},
    }
    self.assertEqual({tool.name for tool in tools.available_tools}, set(expected))
    for tool_obj in tools.available_tools:
      visible = _llm_visible_params(tool_obj)
      self.assertNotIn("user_id", visible, f"{tool_obj.name} leaked user_id")
      self.assertEqual(visible, expected[tool_obj.name])

  async def test_compiled_graph_overrides_llm_user_id_for_all_six_tools(self) -> None:
    self.assertTrue(type(graph.tool_node).__module__.startswith("langgraph"))
    user_details = models.UserDetails(user_id=123, credit_card="0000-0000-0000-1234", shipping_address="100 Oak Ave")
    cases = [
        (123, "orderCheckout", {"product_name": "Serum", "price": 25.0, "user_id": 999}),
        (42, "orderCheckout", {"product_name": "Serum", "price": 25.0, "user_id": 999}),
        (123, "orderInsert", {"product_name": "Serum", "price": 25.0, "user_id": 999}),
        (123, "getResultsOnly", {"query": "my orders", "user_id": 999}),
        (123, "getSummaryOnly", {"query": "explain retinol", "user_id": 999}),
        (123, "getSummaryAndResults", {"query": "list and explain", "user_id": 999}),
        (123, "get_product_price", {"product_name": "Serum", "user_id": 999}),
    ]
    with (
        patch.object(crud, "fetch_user_details", new=AsyncMock(return_value=user_details)) as mock_fetch_user,
        patch.object(crud, "insert_order_db", new=AsyncMock(return_value=77)) as mock_insert,
        patch.object(crud, "get_alloydb_sql", new=AsyncMock(return_value=models.GetSqlResponse(get_sql=models.GetSqlResult(sql="SELECT 1", params=[])))),
        patch.object(crud, "execute_parameterized_query", new=AsyncMock(return_value=models.ExecuteParameterizedQueryResponse(execute_parameterized_query=[{"name": "A"}]))) as mock_exec_param,
        patch.object(crud, "get_alloydb_sql_summary", new=AsyncMock(return_value=models.GetSqlSummaryResponse(get_sql_summary={"answer": "Great"}))) as mock_summary,
        patch.object(crud, "execute_alloydb_nl_query", new=AsyncMock(return_value=models.ExecuteNlQueryResponse(execute_nl_query={"price": 25.0}))) as mock_exec_nl,
        patch.object(graph, "agent_runnable") as mock_runnable,
    ):
      for state_uid, tool_name, llm_args in cases:
        mock_runnable.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{"name": tool_name, "args": llm_args, "id": "c1", "type": "tool_call"}]),
            AIMessage(content="done"),
        ]
        result = await graph.app.ainvoke({"messages": [HumanMessage(content="test")], "user_id": state_uid})
        self.assertTrue(any(isinstance(m, ToolMessage) for m in result["messages"]))

      self.assertEqual([c.args[0] for c in mock_fetch_user.call_args_list], [123, 42, 123])
      mock_insert.assert_awaited_once_with(user_id=123, price=25.0, address="100 Oak Ave")
      self.assertEqual([c.args[1] for c in mock_exec_param.call_args_list], [123, 123])
      mock_exec_nl.assert_awaited_once_with("What is the price of the product named 'Serum'?", 123)
      self.assertEqual(mock_summary.await_count, 2)

  async def test_magic_api_pins_default_user_id(self) -> None:
    fake_state = {
        "original_query": "hi",
        "messages": [
            HumanMessage(content="hi"),
            AIMessage(content="", tool_calls=[{"name": "getSummaryOnly", "args": {"query": "hi"}, "id": "c1", "type": "tool_call"}]),
            ToolMessage(content='{"response": "ok"}', tool_call_id="c1"),
            AIMessage(content="done"),
        ],
    }
    with (
        patch.object(crud, "pool", MagicMock()),
        patch.object(crud, "is_base64_png", return_value=False),
        patch.object(main, "langgraph_app", MagicMock(ainvoke=AsyncMock(return_value=fake_state))) as mock_app,
    ):
      for rejected_uid in (7, "7"):
        with self.assertRaises(HTTPException) as ctx:
          await main.magic_api(models.MagicApiQueryParams(query="hi", userId=rejected_uid))
        self.assertEqual(ctx.exception.status_code, 403)
      mock_app.ainvoke.assert_not_awaited()

      for allowed_uid in ("123", None):
        resp = await main.magic_api(models.MagicApiQueryParams(query="hi", userId=allowed_uid))
        self.assertEqual(resp.response, "ok")
      self.assertEqual([c.args[0]["user_id"] for c in mock_app.ainvoke.call_args_list], [123, 123])

  async def test_magic_api_v1_pins_default_user_id(self) -> None:
    user_details = models.UserDetails(user_id=123, credit_card="0000-0000-0000-1234", shipping_address="100 Oak Ave")
    llm_resp = models.LLMResponse(original_query="explain", selected_api="getSummaryOnly", confidence=0.95)
    expected = models.MagicApiResponse(original_query="explain", selected_api="getSummaryOnly", response="ok")
    with (
        patch.object(crud, "pool", MagicMock()),
        patch.object(crud, "fetch_user_details", new=AsyncMock(return_value=user_details)) as mock_fetch,
        patch.object(llm_interface, "get_intent_and_api", new=AsyncMock(return_value=llm_resp)),
        patch.object(logic, "handle_get_summary_only", new=AsyncMock(return_value=expected)),
    ):
      for requested_uid in (999, None):
        resp = await main.magic_api_v1(models.MagicApiQueryParams(query="explain", userId=requested_uid))
        self.assertEqual(resp.response, "ok")
      self.assertEqual([c.args[0] for c in mock_fetch.call_args_list], [123, 123])

  def test_system_prompt_hides_user_id(self) -> None:
    self.assertNotIn('default="123"', graph.system_prompt)
    self.assertNotIn("userId", graph.system_prompt)
    self.assertNotIn("If the user_id is required pass that also", graph.system_prompt)


if __name__ == "__main__":
  unittest.main()
