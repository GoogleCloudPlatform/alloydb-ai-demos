"""CRUD operations for the database."""
import json
from typing import Any, Dict, List, Optional
import asyncpg
from config import settings
from models import ExecuteNlQueryResponse, GetSqlResult, GetSqlResponse, GetSqlSummaryResponse, PredictRowResult, UserDetails, ExecuteParameterizedQueryResponse
import re
# from google import genai
from google.genai.types import HttpOptions, Part
import base64

# Global pool variable (initialized in main.py)
pool: asyncpg.Pool = None


async def fetch_user_details(user_id: int) -> Optional[UserDetails]:
  """Fetches user details from the database."""
  if not pool:
    raise RuntimeError("Database pool not initialized")
  query = """
        SELECT credit_card, shipping_address
        FROM user_details_reqd_to_order
        WHERE user_id = $1;
    """
  print(f"vkanishk : user_id: {user_id}")
  async with pool.acquire() as conn:
    row = await conn.fetchrow(query, user_id)
    if row:
      return UserDetails(
          user_id=user_id,
          credit_card=row["credit_card"],
          shipping_address=row["shipping_address"],
      )
    return None


async def call_llm_predict(prompt_json_str: str, model_name: str = "gemini-2.5-flash") -> PredictRowResult:
  """Calls the google_ml.predict_row function in the database."""
  if not pool:
    raise RuntimeError("Database pool not initialized")
  # Need to escape single quotes within the JSON string for SQL
  # However, asyncpg parameters handle this safely. Pass the raw string.
  # Escape single quotes within the JSON string for SQL - mimicking the
  # Node.js approach
  escaped_json = prompt_json_str.replace("'", "''")

  # Build the query string directly - similar to Node.js implementation
  query = f"SELECT google_ml.predict_row('{model_name}', '{escaped_json}');"
  async with pool.acquire() as conn:
    try:
      # Using fetchval because we expect a single JSON(B) result
      result_json = await conn.fetchval(query)
      if result_json:
        # Assuming the DB function returns a structure parseable
        # into PredictRowResult
        # Adjust parsing if the actual return type is different
        # (e.g., just the dict)
        if isinstance(result_json, str):
          # If the DB returns it as a JSON string
          data = json.loads(result_json)
          print(f"vkanishk: result_json22--: {data}")
          return PredictRowResult(**data)
        elif isinstance(result_json, dict):
          result_json["type"] = "prediction"  # Add the missing type field
          print(f"vkanishk: result_json33: {result_json}")
          # If the DB returns it as a dictionary-like object (e.g., JSONB)
          return PredictRowResult(**result_json)
        else:
          raise ValueError(
              f"Unexpected type from google_ml.predict_row: {type(result_json)}"
          )
      else:
        raise ValueError("No result returned from google_ml.predict_row")
    except Exception as e:
      print(f"Error calling google_ml.predict_row: {e}")
      print(f"Prompt String causing error: {prompt_json_str}")
      raise  # Re-raise the exception


async def execute_parameterized_query(
    sql_query: str, user_id: int
) -> ExecuteParameterizedQueryResponse:
  """Executes alloydb_ai_nl.execute_nl_query."""
  if not pool:
    raise RuntimeError("Database pool not initialized")
  user_id_str = str(user_id)

  sql = """
        SELECT * FROM parameterized_views.execute_parameterized_query(
        $1,
        param_names => ARRAY['userid'],
        param_values => ARRAY[$2]
        );
    """
  print(
      f"execute_parameterized_query, sql: {sql}, query: {sql_query} ,"
      f" user_id: {user_id_str}"
  )

  
  async with pool.acquire() as conn:
    records = await conn.fetch(sql, sql_query, user_id_str)
    print(f"records: {records}")
    processed_results = []
    for record in records:
      if record["json_results"]:
        try:
          # Parse the JSON string into a Python dictionary
          parsed_json = json.loads(record["json_results"])
          processed_results.append(parsed_json)
        except json.JSONDecodeError:
          # If not valid JSON, add the raw value
          processed_results.append(record["json_results"])

    # Handle the results based on the number of records
    if not processed_results:
      # Empty result
      return ExecuteParameterizedQueryResponse(execute_parameterized_query=None)
    elif len(processed_results) == 1:
      # Single result - can be returned as is
      return ExecuteParameterizedQueryResponse(
          execute_parameterized_query=processed_results[0]
      )
    else:
      # Multiple results - return as a list
      return ExecuteParameterizedQueryResponse(
          execute_parameterized_query=processed_results
      )


async def execute_alloydb_nl_query(
    query: str, user_id: int
) -> ExecuteNlQueryResponse:
  """Executes alloydb_ai_nl.execute_nl_query."""
  if not pool:
    raise RuntimeError("Database pool not initialized")
  user_id_str = str(user_id)
  sql = """
        SELECT alloydb_ai_nl.execute_nl_query(
            $1,
            $2,
            param_names => ARRAY['userid'],
            param_values => ARRAY[$3] -- Ensure userid is passed as text
        );
    """
  print(
      f"vkanishk: execute_alloydb_nl_query, sql: {sql}, query: {query} ,"
      f" settings.nl_config_name: {settings.nl_config_name}, user_id:"
      f" {user_id_str}"
  )
  async with pool.acquire() as conn:
    records = await conn.fetch(sql, query, settings.nl_config_name, user_id_str)
    processed_results = []
    for record in records:
      if record["execute_nl_query"]:
        try:
          # Parse the JSON string into a Python dictionary
          parsed_json = json.loads(record["execute_nl_query"])
          processed_results.append(parsed_json)
        except json.JSONDecodeError:
          # If not valid JSON, add the raw value
          processed_results.append(record["execute_nl_query"])

    # Handle the results based on the number of records
    if not processed_results:
      # Empty result
      return ExecuteNlQueryResponse(execute_nl_query=None)
    elif len(processed_results) == 1:
      # Single result - can be returned as is
      return ExecuteNlQueryResponse(execute_nl_query=processed_results[0])
    else:
      # Multiple results - return as a list
      return ExecuteNlQueryResponse(execute_nl_query=processed_results)


async def get_alloydb_sql(query: str) -> GetSqlResponse:
  """Executes alloydb_ai_nl.get_sql.

  Args:
      query: Natural language query to execute

  Returns:
      GetSqlResponse containing the SQL query and parameters

  Raises:
      RuntimeError: If database pool is not initialized
  """
  if not pool:
    raise RuntimeError("Database pool not initialized")

  sql = """
        SELECT alloydb_ai_nl.get_sql($1, $2);
    """

  async with pool.acquire() as conn:
    # Using fetch to get all records
    records = await conn.fetch(sql, settings.nl_config_name, query)
    print(f"vkanishk: records: {records}")

    # Process the first record (we expect only one)
    if records and records[0]["get_sql"]:
      try:
        # Parse the JSON string into a Python dictionary
        parsed_json = json.loads(records[0]["get_sql"])

        # Extract the SQL and parameters from the parsed JSON
        sql_query = parsed_json.get("sql", "")
        params = parsed_json.get("params", [])

        # Create the result object
        result = GetSqlResult(sql=sql_query, params=params)

        # Return the response
        return GetSqlResponse(get_sql=result)
      except json.JSONDecodeError:
        # Handle invalid JSON
        print(f"Warning: Could not parse JSON: {records[0]['get_sql']}")
        return GetSqlResponse(get_sql=GetSqlResult(sql="", params=[]))

    # Handle no results
    return GetSqlResponse(get_sql=GetSqlResult(sql="", params=[]))


async def get_alloydb_sql_summary(query: str) -> GetSqlSummaryResponse:
  """Executes alloydb_ai_nl.get_sql_summary."""
  if not pool:
    raise RuntimeError("Database pool not initialized")
  # Note: Using f-string requires careful handling of quotes if query
  # contains them. Parameterization is safer if the function supports it.
  # Assuming it takes a literal.
  # Replicating Node.js's toPgStringLiteral logic (basic version)
  escaped_query = query.replace("'", "''")
  sql = f"""
        SELECT alloydb_ai_nl.get_sql_summary('{settings.nl_config_name}', E'{escaped_query}');
    """
  async with pool.acquire() as conn:
    records = await conn.fetch(sql)  # Assuming it returns JSONB
    processed_results = []
    for record in records:
      if record["get_sql_summary"]:
        try:
          # Parse the JSON string into a Python dictionary
          parsed_json = json.loads(record["get_sql_summary"])
          processed_results.append(parsed_json)
        except json.JSONDecodeError:
          return None
    return GetSqlSummaryResponse(get_sql_summary=processed_results[0])


async def insert_order_db(user_id: int, price: float, address: str) -> int:
  """Inserts an order into the orders1 table and returns the order ID."""
  if not pool:
    raise RuntimeError("Database pool not initialized")
  query = """
        INSERT INTO orders1 (
            user_id, order_date, total_amount, shipping_address,
            billing_address, order_status
        ) VALUES (
            $1, CURRENT_TIMESTAMP, $2, $3, $4, 'CONFIRMED'
        ) RETURNING order_id;
    """
  async with pool.acquire() as conn:
    # Assuming shipping_address is used for billing_address as in Node.js code
    order_id = await conn.fetchval(query, user_id, price, address, address)
    if order_id is None:
      raise RuntimeError("Failed to insert order, no order_id returned.")
    return order_id


pool_v1: asyncpg.Pool = None


async def search_products_distinct(query: str, personalized: bool):
  """Searches products using the search_products_distinct function.

  Args:
      query: The search query string.
      personalized: Whether to personalize the search results.

  Returns:
      A dictionary containing the search results.

  Raises:
      RuntimeError: If the database pool is not initialized.
  """
  if not pool_v1:
    raise RuntimeError("Database pool_v1 not initialized")
  print(
      f"search_products_distinct, query: {query}, personalized: {personalized}"
  )
  sql = "SELECT * FROM search_products_distinct($1, $2, FALSE);"
  async with pool_v1.acquire() as conn:
    stmt = await conn.prepare(sql)
    rows_raw = await stmt.fetch(query, personalized)
    rows = [dict(row) for row in rows_raw]
    fields = [
        {
            "name": col.name,
            "tableID": 0,
            "columnID": 0,
            "dataTypeID": col.type.oid,
            "dataTypeSize": -1,
            "dataTypeModifier": -1,
            "format": "text",
        }
        for col in stmt.get_attributes()
    ]

    return {
        "command": "SELECT",
        "rowCount": len(rows),
        "oid": None,
        "rows": rows,
        "fields": fields,
    }

def is_base64_png(base64_str: str) -> bool:
  """Check if the given base64-encoded string is a PNG image."""
  try:
    if not isinstance(base64_str, str):
      return False
    buffer = base64.b64decode(base64_str)

    png_signature = '89504e470d0a1a0a'
    file_signature = buffer[:8].hex()

    return file_signature == png_signature
  except Exception:
    return False

async def analyze_skin_and_fetch_products(
    base64_image: str, personalized: bool = False
):
  """Analyzes skin from a base64 image and fetches relevant products.

  Args:
      base64_image: A base64-encoded string of the input image.
      personalized: Whether to personalize the product search results.

  Returns:
      A dictionary containing the analysis results, product recommendations,
      and status.

  Raises:
      Exception: If any error occurs during the process.
  """
  try:
    system_prompt = """
    You are a highly knowledgeable and encouraging skincare specialist. Your expertise allows you to precisely analyze people's skin from an image, celebrating its strengths while clearly identifying specific areas for focused care.
    Based on the image, generate a short description for "skin_analysis" (around 70 words):
    Begin with a genuine compliment about a noticeable positive aspect of their skin. Then, lead into the expert analysis, clearly stating observable characteristics such as skin texture (e.g., smooth, slightly uneven), visible concerns (e.g., fine lines, dehydration, mild redness, dark spots), and their general location if apparent. Use specific but neutral terminology.
    Next, for "top_priority_area" (around 30 words):
    Based on your detailed analysis, highlight the single most impactful skin characteristic that could be enhanced.
    Succinctly describe how a particular type of skincare product (e.g., hydrating serum, gentle exfoliant, brightening moisturizer) can help address this specific characteristic for noticeable improvement.
    For the output, return:
    "status": to show if the response was successfully generated.
    "skin_analysis": (around 70 words, following the two-step structure above).
    "top_priority_area": (around 30 words, focused and actionable).
    "skin_type": Choose the most appropriate: combination, normal, dry, oily (base this on your expert assessment).
    "product_search": A product search string directly related to the "top_priority_area" and suggested product type (e.g., "retinol serum for fine lines forehead," "hydrating moisturizer for dry cheeks" ).
    Important: Maintain an encouraging and expert tone throughout. Ensure the word counts for "skin_analysis" and "top_priority_area" are closely adhered to.
    Do not include any introduction, explanation, or non-JSON text in the output.
    """
    analysis_result = {}
    try:
      request_payload = {
          "systemInstruction": {
              "role": "system",
              "parts": [{"text": system_prompt}],
          },
          "contents": [{
              "role": "user",
              "parts": [
                  {"text": "Image input"},
                  {
                      "inlineData": {
                          "mimeType": "image/png",
                          "data": base64_image,
                      }
                  },
              ],
          }],
      }

      prediction_response = await call_llm_predict(
          json.dumps(request_payload), "gemini-2.5-flash"
      )
      prediction_text = prediction_response.candidates[0]["content"]["parts"][
          0
      ]["text"]
      match = re.search(
          r"```json\s*(\{.*?\})\s*```", prediction_text, re.DOTALL
      )
      if match:
          json_text = match.group(1)
          analysis_result = json.loads(json_text)
          print("Parsed analysis_result:", analysis_result)
      else:
          raise ValueError("No JSON block found in prediction_text.")

    except Exception as e:
      print(f"An error occurred: {e}")

    if analysis_result["status"] != "success":
      return {"status": "failed", "error": "Failed to process image"}
    product_query = analysis_result["product_search"]
    product_recommendations = await search_products_distinct(
        product_query, personalized
    )
    return {
        "rows": product_recommendations,
        "status": analysis_result.get("status"),
        "analysis": analysis_result.get("skin_analysis"),
        "priority": analysis_result.get("top_priority_area"),
        "skinType": analysis_result.get("skin_type"),
        "productSearch": analysis_result.get("product_search"),
    }
  except Exception as e:
    print("Error:", e)
    return {"status": "error", "message": str(e)}