"""Defines and registers various tools for the LangGraph agent."""
import json
from typing import Any, Dict, List, Optional
import crud
from langchain.tools import tool
from models import UserDetails, OrderDetails
import logic

# --- Tool Definitions ---


@tool
async def orderCheckout(
    product_name: str, price: float, user_id: int = 123
) -> Dict[str, Any]:
  """Fetches user details like shipping address and partial credit card info for the given user ID.

  Provided product name and price are used to construct the response text.

  Args:
      user_id (int): The ID of the user whose details are to be fetched.

  Returns:
      Dict: A dictionary containing order details or an error message.
  """
  print(f"TOOL: orderCheckout called for user_id: {user_id}")
  details = await crud.fetch_user_details(user_id)
  if details:
    cc_info = details.credit_card[-4:] if details.credit_card else "N/A"
    shipping_address = details.shipping_address
    order_details = OrderDetails(
        product_name=product_name,
        price=price,
        credit_card_last4=cc_info,
        shipping_address=shipping_address
    )
    response_text = (
        "Excellent! To confirm your order, please verify the following"
        f" information:\n\nProduct: {order_details.product_name}\nPrice:"
        f" ${order_details.price:.2f}\nPayment Method: Credit Card (ending in"
        f" {order_details.credit_card_last4})\nShipping Address:"
        f" {order_details.shipping_address}\n\nWould you like to confirm this"
        " order?"
    )
    
    return {
        "order_status": 'CONFIRMATION_REQUIRED',
        "order_details": order_details.dict(),
        "response": response_text
    }
  else:
    return {"error": f"User details not found for user_id {user_id}."}


@tool
async def getResultsOnly(
    query: str, user_id: int = 123
) -> Dict[str, Any]:
  """Executes a natural language query against the product database.

  Use this for finding products, getting product details, checking prices, or
  listing items based on criteria. The user ID provides context for
  personalization if applicable. Returns the database results, potentially as a
  list of items or a single dictionary/value.

  Args:
      query (str): The natural language query to execute.
      user_id (int): The ID of the user for whom the query is being executed.

  Returns:
      Dict: A dictionary containing the query results or an error message.
  """
  print(
      f"TOOL: getResultsOnly called for user {user_id}:"
      f" '{query}'"
  )
  generated_sql = ""
  params = []
  response_text = "Here are the results based on your query."
  try:
    sql_info = await crud.get_alloydb_sql(query)
    generated_sql = sql_info.get_sql.sql
    params = sql_info.get_sql.params
  except Exception as e:
    print(f"Failed to get SQL: {e}")
    generated_sql = "Error retrieving generated SQL"
    params = []
  try:
    db_result_raw = await crud.execute_parameterized_query(
        generated_sql, user_id
    )
    results = logic._transform_db_result(db_result_raw)
    flat_result = (
        results[0]["value"].execute_parameterized_query if results else []
    )

    return {
        "nl2sql": generated_sql,
        "params": params,
        "result": flat_result,
        "response": response_text,
    }
  except Exception as e:
    print(f"Error in execute_natural_language_query tool: {e}")
    return {"error": f"Failed to execute query '{query}'. Error: {e}"}


@tool
async def getSummaryOnly(query: str, user_id: int = 123) -> Dict[str, Any]:
  """Generates a natural language summary or explanation for a query about products or comparisons.

  Use this when the user asks 'why', 'explain', 'compare', 'tell me more about'.

  Args:
      query (str): The natural language query for which a summary is needed.

  Returns:
      Dict: A dictionary containing the summary or an error message.
  """
  print(f"TOOL: getSummaryOnly called for query: '{query}'")
  try:
    summary_data = await crud.get_alloydb_sql_summary(query)
    sql_summary_dict = getattr(summary_data, 'get_sql_summary', {})
    summary = sql_summary_dict.get('answer', 'Summary not available.')

    return {
        "response": summary
    }
  except Exception as e:
    print(f"Error in get_natural_language_summary tool: {e}")
    return {"error": f"Failed to get summary for query '{query}'. Error: {e}"}


@tool
async def getSummaryAndResults(query: str, user_id: int = 123) -> Dict[str, Any]:
  """Returns the results and summary for a given query."""
  print(f"TOOL: getSummaryAndResults called for query: '{query}'")
  summary_text = ""
  flat_result = []
  generated_sql = ""
  params = []
  try:
    summary_data = await crud.get_alloydb_sql_summary(query)
    sql_summary_dict = getattr(summary_data, "get_sql_summary", {})
    summary_text = sql_summary_dict.get("answer", "Summary not available.")
  except Exception as e:
    print(f"Failed to get summary: {e}")
    summary_text = f"Sorry, I couldn't generate a summary. Error: {e}"

  try:
    sql_info = await crud.get_alloydb_sql(query)
    generated_sql = sql_info.get_sql.sql
    params = sql_info.get_sql.params
  except Exception as e:
    print(f"Failed to get SQL: {e}")
    generated_sql = "Error retrieving generated SQL"
    params = []

  try:
    db_result_raw = await crud.execute_parameterized_query(
        generated_sql, user_id
    )
    results = logic._transform_db_result(db_result_raw)
    flat_result = (
        results[0]["value"].execute_parameterized_query if results else []
    )
  except Exception as e:
    print(f"Failed to execute NL query for results: {e}")
    # Return summary only if results fail
  return {
      "params": params,
      "results": flat_result,
      "response": summary_text,
      "nl2sql": generated_sql,
      "result": flat_result,
  }


# --- Tools related to Ordering ---


@tool
async def get_product_price(product_name: str, user_id: int = 123) -> Dict[str, Any]:
  """Gets the price of a specific product using a natural language query to the database.

  Requires the product name and user ID.

  Args:
      product_name (str): The name of the product for which the price is to be
        fetched.
      user_id (int): The ID of the user for whom the price is being checked.

  Returns:
  Returns:
      Dict: A dictionary containing the product price or an error message.
  """
  print(
      f"TOOL: get_product_price called for product: '{product_name}', user:"
      f" {user_id}"
  )
  price_query = f"What is the price of the product named '{product_name}'?"
  price = 0.0
  try:
    price_result = await crud.execute_alloydb_nl_query(price_query, user_id)

    raw_result = getattr(price_result, "execute_nl_query", None)

    if isinstance(raw_result, list):
        first_item = raw_result[0] if raw_result else None
        if isinstance(first_item, dict):
            return first_item
        else:
            return {'value': first_item}

    elif isinstance(raw_result, dict):
        return raw_result

    elif raw_result is None:
        return {
            "product_name": product_name,
            "price": 35.0,
            "warning": "Used default price because result was None"
        }

    else:
        return {'value': raw_result}

  except Exception as e:
      print(f"Error fetching price for {product_name}: {e}")
      return {
          "product_name": product_name,
          "price": 35.0,
          "warning": f"Used default price due to error: {e}"
      }

@tool
async def orderInsert(
    product_name: str, price: float, user_id: int = 123
) -> Dict[str, Any]:
  """Inserts a confirmed order into the database ONLY AFTER the user has confirmed details.
  """
  print(f"TOOL: orderInsert called for user {user_id}, product {product_name}")
  details = await crud.fetch_user_details(user_id)
  try:
    order_id = await crud.insert_order_db(
        user_id=user_id, price=price, address=details.shipping_address
    )
    order_details = OrderDetails(
        order_id=order_id,
        product_name=product_name,  # Node.js used 'product' here
        product=product_name,  # Match Node.js response field
        price=price,
        total_amount=price,  # Match Node.js response field
        credit_card_last4=(
            details.credit_card[-4:] if details.credit_card else "N/A"
        ),
        shipping_address=details.shipping_address,
        status="CONFIRMED",  # Match Node.js response field
        user_id=user_id,
    )

    response_text = (
        f"Your order for {product_name} has been successfully placed! "
        f"Order number: #{order_id}\n"
        f"Total amount: ${price:.2f}\n"
        "A confirmation email will be sent to your registered email address."
    )
    return{
        "order_status": 'CONFIRMED',
        "order_details": order_details.dict(),
        "response": response_text
    }
  except Exception as e:
    print(f"Order insertion failed: {e}")
    return {"error": f"Failed to place order for '{product_name}'. Error: {e}"}


# Combine all tools into a list
available_tools = [
    get_product_price,
    getResultsOnly,
    getSummaryOnly,
    getSummaryAndResults,
    orderCheckout,
    orderInsert
]