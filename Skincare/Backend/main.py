"""Main application file for the FastAPI server."""
from contextlib import asynccontextmanager
import json
import os
import traceback
import time

import asyncpg
from config import Settings, settings
import crud
from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from graph import app as langgraph_app, get_initial_state
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
import llm_interface
import logic
from models import (
    ChatResponse,
    ErrorResponse,
    MagicApiQueryParams,
    MagicApiResponse,
    PingResponse,
    UserDetails,
    OrderDetails
)
from typing import Any, Dict, List, Optional


# --- Database Connection Pool Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
  """Context manager to manage the database connection pool."""
  # Startup: Initialize database pool
  print("Initializing database pool...")
  try:
    crud.pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=10,  # Adjust pool size as needed
    )
    print(f"Database pool initialized for {settings.database_url}")
    # Initialize pool for client2 if needed
    if settings.database_url_v1:
      crud.pool_v1 = await asyncpg.create_pool(
          dsn=settings.database_url_v1, min_size=1, max_size=10
      )
      print(f"Database pool_v1 initialized for {settings.database_url_v1}")
  except Exception as e:
    print(f"Failed to initialize database pool: {e}")
    traceback.print_exc()
    # Decide if the app should fail to start or continue without DB
    crud.pool = None
    crud.pool_v1 = None
  yield
  # Shutdown: Close database pool
  print("Closing database pool...")
  if crud.pool:
    await crud.pool.close()
    print("Database pool closed.")
  if crud.pool_v1:
    await crud.pool_v1.close()
    print("Database pool_v1 closed.")


app = FastAPI(lifespan=lifespan)

# --- CORS Middleware ---
# Basic permissive CORS for development (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---


@app.get("/ping", response_model=PingResponse)
async def ping():
  # Port info might require inspecting the running server
  # (e.g., via request headers or env vars)
  # Hardcoding for now, similar to Node.js example
  return PingResponse(
      status="ok",
      message="Server is alive and responding",
      timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
      port=8000,  # Default uvicorn port, adjust if needed
  )


@app.post(
    "/magic-api-v1",
    response_model=MagicApiResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def magic_api_v1(params: MagicApiQueryParams):
  """Unified API endpoint to handle user queries via LLM intent detection and specific logic execution."""
  print("-============== API STARTS ========================-")
  print(f"Session ID: {params.sessionId}")
  print(f"Original Query: {params.query}")

  # Ensure DB pool is available
  if not crud.pool:
    raise HTTPException(
        status_code=500, detail="Database connection pool not available."
    )

  # --- Get User Details ---
  # Using default user ID from settings, replace with actual auth if needed
  user_id = settings.default_user_id
  print(f"User ID: {user_id}")
  user_details = await crud.fetch_user_details(user_id)
  if not user_details:
    print(f"User details not found for user_id: {user_id}")
    raise HTTPException(
        status_code=404, detail=f"User details not found for user_id: {user_id}"
    )
  print(f"User Details: {user_details}")

  # --- Determine Intent and API using LLM ---
  llm_response = await llm_interface.get_intent_and_api(
      params.query, params.sessionId
  )

  if not llm_response:
    raise HTTPException(
        status_code=500,
        detail="Failed to get valid response from LLM interface",
    )

  print(f"LLM Response: {llm_response}")
  print(f"Selected API: {llm_response.selected_api}")

  # --- Route to appropriate logic based on selected_api ---
  try:
    if llm_response.selected_api == "orderCheckout":
      response = await logic.handle_order_checkout(
          llm_response, user_details, params.sessionId
      )
    elif llm_response.selected_api == "orderInsert":
      response = await logic.handle_order_insert(
          llm_response, user_details, params.sessionId
      )
    elif llm_response.selected_api == "getResultsOnly":
      response = await logic.handle_get_results_only(
          llm_response, user_details, params.sessionId
      )
    elif llm_response.selected_api == "getSummaryOnly":
      response = await logic.handle_get_summary_only(
          llm_response, user_details, params.sessionId
      )
    elif llm_response.selected_api == "getSummaryAndResults":
      response = await logic.handle_get_summary_and_results(
          llm_response, user_details, params.sessionId
      )
    else:
      print(f"Unknown API type received: {llm_response.selected_api}")
      raise HTTPException(
          status_code=400,
          detail=f"Unknown API type selected: {llm_response.selected_api}",
          # headers={"X-Selected-API": llm_response.selected_api}
      )

    return response

  except ValueError as ve:
    # Handle specific value errors from logic functions
    # (e.g., missing product name)
    print(f"Value Error processing request: {ve}")
    raise HTTPException(
        status_code=400,
        detail=str(ve),
        # headers={"X-Selected-API": llm_response.selected_api}
    )
  except HTTPException as he:
    # Re-raise HTTPExceptions directly
    raise he
  except Exception as e:
    # Catch-all for other unexpected errors during logic execution
    print(
        f"Error processing query logic for API {llm_response.selected_api}: {e}"
    )
    import traceback

    traceback.print_exc()  # Print full traceback for debugging
    raise HTTPException(
        status_code=500,
        detail=(
            f"Failed to process query for API '{llm_response.selected_api}'."
            " Internal error."
        ),
        # headers={"X-Selected-API": llm_response.selected_api}
    )

@app.post("/magic-api", response_model=MagicApiResponse, tags=["Chat"])
async def magic_api(request: MagicApiQueryParams):
  """Handles user chat requests, routes through LangGraph, and returns the response formatted as MagicApiResponse.
  """
  if not crud.pool:
    raise HTTPException(
        status_code=503, detail="Database connection not available."
    )

  session_id = request.sessionId
  user_query = request.query
  user_id = (
      request.userId
      if request.userId is not None
      else settings.default_user_id
  )

  print("\n--- New Request ---")
  print(f"Session ID: {session_id}")
  print(f"User ID: {user_id}")
  print(f"Query: {user_query}")

  config = {"configurable": {"thread_id": session_id}}
  # Include original_query in the initial input state
  inputs = {
      "messages": [HumanMessage(content=user_query)],
      "user_id": user_id,
      "original_query": user_query,  # Pass original query into state
  }

  final_state_raw: Optional[Dict[str, Any]] = None
  try:
    if crud.is_base64_png(user_query):
      skin_analysis_response = await crud.analyze_skin_and_fetch_products(
          user_query
      )
      magic_response = MagicApiResponse(
          selected_api="analyze_skin_and_fetch_products",
          a=skin_analysis_response.get("rows"),
          status=skin_analysis_response.get("status", "Unknown"),
          analysis=skin_analysis_response.get("analysis", "Unknown"),
          priority=skin_analysis_response.get("priority", "Unknown"),
          skinType=skin_analysis_response.get("skinType", "Unknown"),
          productSearch=skin_analysis_response.get("productSearch", "Unknown"),
      )
      return magic_response
    else: 
      # Use invoke to get the final state
      final_state_raw = await langgraph_app.ainvoke(inputs, config=config)

  except GraphRecursionError as e:
    print(f"ERROR: Graph recursion limit reached: {e}")
    # Return an error within the MagicApiResponse structure
    return MagicApiResponse(
        original_query=user_query,
        response=f"Sorry, the request got too complex. Error: {e}",
        selected_api="error",
    )
  except Exception as e:
    print(f"ERROR: Exception during LangGraph execution: {e}")
    import traceback

    traceback.print_exc()
    # Return an error within the MagicApiResponse structure
    return MagicApiResponse(
        original_query=user_query,
        response=f"Sorry, an internal error occurred. Error: {e}",
        selected_api="error",
    )

  # --- Construct MagicApiResponse from final_state_raw ---
  final_response_text = "Sorry, could not determine the final response."
  selected_api_name = None
  tool_result_data = None
  order_details_data = None
  order_status = None

  if isinstance(final_state_raw, dict) and "messages" in final_state_raw:
    messages: List[BaseMessage] = final_state_raw.get("messages", [])
    final_ai_message: Optional[AIMessage] = None
    last_tool_message: Optional[ToolMessage] = None
    last_tool_name: Optional[str] = None

    # Find the last AI message
    for msg in reversed(messages):
      if isinstance(msg, AIMessage):
        final_ai_message = msg
        break

    # Find the last Tool message and associated tool call in AI message
    # before it
    tool_call_id = None
    for i in range(len(messages) - 1, 0, -1):
      # Find last ToolMessage
      if isinstance(messages[i], ToolMessage):
        last_tool_message = messages[i]
        tool_call_id = (
            last_tool_message.tool_call_id
        )  # Get ID to find corresponding call
        # Now find the AIMessage *before* this ToolMessage that
        # initiated the call
        for j in range(i - 1, -1, -1):
          if isinstance(messages[j], AIMessage) and messages[j].tool_calls:
            for tc in messages[j].tool_calls:
              if tc.get("id") == tool_call_id:
                last_tool_name = tc.get("name")
                break  # Found the tool name
          if last_tool_name:
            break  # Stop searching backwards once name is found
        break  # Stop searching for ToolMessage

    # Determine final response text
    if final_ai_message:
      final_response_text = final_ai_message.content

    # Set selected_api based on the last tool called
    selected_api_name = last_tool_name  # May be None if no tool was called

    # Extract tool result if available
    if last_tool_message:
      try:
        # ToolNode stringifies the output, try to parse it back
        tool_result_data = json.loads(last_tool_message.content)
      except json.JSONDecodeError:
        # If not JSON, use the raw string content
        tool_result_data = last_tool_message.content

      # --- Special handling for order insertion result ---
      # Check if the last tool was insert_order and if it was successful
      if selected_api_name == "insert_order" and isinstance(
          tool_result_data, dict
      ):
        if (
            "order_id" in tool_result_data
            and tool_result_data.get("status") == "Order Confirmed"
        ):
          order_status = "CONFIRMED"
          # Attempt to reconstruct OrderDetails if possible
          # (might need more info)
          # This requires the agent/state to hold product_name, price etc.
          # For now, we just extract the ID.
          order_details_data = OrderDetails(
              order_id=tool_result_data["order_id"],
              product_name=tool_result_data.get(
                  "product_name", "Unknown - Check Logs"
              ),  # Tool should return this ideally
              price=tool_result_data.get(
                  "price", 0.0
              ),  # Tool should return this ideally
              # These might not be readily available in the tool output,
              # may need state access
              credit_card_last4="N/A",
              shipping_address="N/A",
              status="CONFIRMED",
          )
        elif "error" in tool_result_data:
          order_status = "FAILED"
          # Optionally add error details to final_response_text:
          # final_response_text += (
          #     f" (Order Failed: {tool_result_data['error']})"
          # )

  magic_response = MagicApiResponse(
      original_query=final_state_raw.get("original_query", user_query)
      if final_state_raw
      else user_query,
      selected_api=selected_api_name,
      response=tool_result_data.get("response") or "",
      result=tool_result_data.get("result") or None,
      order_status=tool_result_data.get("order_status") or None,
      order_details=tool_result_data.get("order_details") or None,
      nl2sql=tool_result_data.get("nl2sql") or None,
      params=tool_result_data.get("params") or None,
  )

  return magic_response

@app.get("/")
async def root( request: Request, query: str = Query("", description="Search query text"), personalized: bool = Query(False, description="Enable personalized search") ):
  """Handles root endpoint requests, searches products using client2 logic."""
  query_text = request.query_params.get("query", "")
  personalized = request.query_params.get("personalized") == "true"
  if not crud.pool_v1:
    raise HTTPException(
        status_code=500, detail="Database V1 connection not available"
    )
  try:
    results = await crud.search_products_distinct(query_text, personalized)
    print(f"results: {results}")
    return {"a": results}  # Match Node.js structure {'a': result}
  except Exception as e:
    print(f"Error in root endpoint query: {e}")
    raise HTTPException(
        status_code=500, detail=f"Database error in root endpoint: {str(e)}"
    )


# --- Run the server (for local development) ---
if __name__ == "__main__":
  import uvicorn
  # Use reload=True for development, it watches for file changes
  uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
  # For production, run without reload:
  # uvicorn main:app --host 0.0.0.0 --port 8000