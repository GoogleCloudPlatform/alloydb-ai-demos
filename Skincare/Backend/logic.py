"""Logic for handling API requests and orchestrating responses."""
import json
from typing import Dict, Any, List, Optional

import crud
from config import settings
from models import (
    UserDetails,
    OrderDetails,
    MagicApiResponse,
    LLMResponse,
    ExecuteNlQueryResponse
)
from llm_interface import update_conversation_history
from fastapi.responses import JSONResponse

# --- Helper Functions ---

def _transform_db_result(
    db_response: ExecuteNlQueryResponse
) -> List[Dict[str, Any]]:
    """Transforms the raw result from execute_nl_query (needs adjustment)."""
    # This is highly dependent on the *actual* structure returned by
    # execute_nl_query
    # The Node.js code did `data.rows.map(item => item.execute_nl_query)`
    # Let's assume execute_nl_query returns a list of dicts directly
    print(f"vkanishk: transform_ db_response: {db_response}")
    raw_result = db_response
    if isinstance(raw_result, list):
         # If it's already a list of dicts, return it
         # Ensure items are dicts, handle potential non-dict items if necessary
        return [
            item if isinstance(item, dict) else {'value': item}
            for item in raw_result
        ]
    elif isinstance(raw_result, dict):
         # If it's a single dict, wrap it in a list
        return [raw_result]
    elif raw_result is None:
        return []
    else:
         # Handle other potential types (scalar values, etc.)
         return [{'value': raw_result}]


async def _get_product_price(
    product_name: str, user_id: str
) -> Optional[float]:
    """Helper to get product price using the NL query function."""
    price_nl_query = f"Determine the price of product {product_name}"
    try:
        price_result_raw = await crud.execute_alloydb_nl_query(
            price_nl_query, user_id
        )
        # --- Parse Price ---
        # This depends heavily on the structure returned for a price query.
        # Adjust the parsing logic based on actual results.
        # Example: Assuming it returns {'price_usd': 35.0}
        price_data = price_result_raw.execute_nl_query
        if isinstance(price_data, dict) and 'price_usd' in price_data:
             print(f"Price found for {product_name}: {price_data['price_usd']}")
             return float(price_data['price_usd'])
        else:
             print(f"Could not parse price from result: {price_data}")
             # Fallback to default/dummy price as in Node.js
             print(f"Using fallback price 35.0 for {product_name}")
             return 35.0 # DUMMY PRICE
    except Exception as e:
        print(f"Error fetching price for {product_name}: {e}")
        print(f"Using fallback price 35.0 for {product_name}")
        return 35.0 # DUMMY PRICE


# --- Main Logic Handlers (Potential Agent Tools) ---

async def handle_order_checkout(
    llm_response: LLMResponse,
    user_details: UserDetails,
    session_id: Optional[str]
) -> MagicApiResponse:
    """Logic for 'orderCheckout' API type."""
    product_name = llm_response.product_name
    if not product_name:
        # Or return error response
        raise ValueError("Product name is required for orderCheckout")

    price = await _get_product_price(product_name, user_details.user_id)
    if price is None:
         # Should ideally not happen with the fallback in _get_product_price
         raise ValueError(f"Could not determine price for {product_name}")

    cc_last4 = (
        user_details.credit_card[-4:] if user_details.credit_card else "N/A"
    )

    order_details = OrderDetails(
        product_name=product_name,
        price=price,
        credit_card_last4=cc_last4,
        shipping_address=user_details.shipping_address
    )

    response_text = (
        "Excellent! To confirm your order, please verify the following "
        "information:\n\n"
        f"Product: {order_details.product_name}\n"
        f"Price: ${order_details.price:.2f}\n"
        "Payment Method: Credit Card "
        f"(ending in {order_details.credit_card_last4})\n"
        f"Shipping Address: {order_details.shipping_address}\n\n"
        f"Would you like to confirm this order?"
    )

    return MagicApiResponse(
        original_query=llm_response.original_query,
        selected_api=llm_response.selected_api,
        order_status='CONFIRMATION_REQUIRED',
        response=response_text,
        order_details=order_details
    )

async def handle_order_insert(
    llm_response: LLMResponse,
    user_details: UserDetails,
    session_id: Optional[str]
) -> MagicApiResponse:
    """Logic for 'orderInsert' API type."""
    product_name = llm_response.product_name
     # Extract product name from confirmation query if not directly in
     # llm_response
    if (not product_name and
        "confirm the order with product name: " in llm_response.original_query):
         # Basic extraction, make more robust if needed
         try:
            product_name = llm_response.original_query.split(
                "confirm the order with product name: "
            )[1]
         except IndexError as exc:
             # If extraction fails but intent is orderInsert, maybe use last
             # product from history?
             # For now, raise error if name is missing and not extractable.
              raise ValueError(
                  "Product name missing or not extractable for orderInsert"
              ) from exc
    elif not product_name:
         # If it's a generic confirmation "yes order", you *need* context.
         # The v2 prompt forbids context, so this case is problematic.
         # An Agent framework *would* handle this context. For now, error out.
          raise ValueError("Product name missing for orderInsert confirmation")


    price = await _get_product_price(product_name, user_details.user_id)
    if price is None:
        raise ValueError(
            f"Could not determine price for {product_name} "
            "during order insertion"
        )

    try:
        order_id = await crud.insert_order_db(
            user_id=user_details.user_id,
            price=price,
            address=user_details.shipping_address
        )
        print(f"Order inserted successfully with ID: {order_id}")
    except Exception as e:
        print(f"Order insertion failed: {e}")
        # Return an error response instead of raising exception to main handler
        return MagicApiResponse(
            original_query=llm_response.original_query,
            selected_api=llm_response.selected_api,
            response=(
                f"Sorry, there was an error placing your order for "
                f"{product_name}. Error: {e}"
            ),
            order_status="FAILED"
        )


    order_details = OrderDetails(
        order_id=order_id,
        product_name=product_name, # Node.js used 'product' here
        product=product_name,      # Match Node.js response field
        price=price,
        total_amount=price,      # Match Node.js response field
        credit_card_last4=(
            user_details.credit_card[-4:] if user_details.credit_card else "N/A"
        ),
        shipping_address=user_details.shipping_address,
        status='CONFIRMED',        # Match Node.js response field
        user_id=user_details.user_id
    )

    response_text = (
        f"Your order for {product_name} has been successfully placed! "
        f"Order number: #{order_id}\n"
        f"Total amount: ${price:.2f}\n"
        f"A confirmation email will be sent to your registered email address."
    )

    # Update history (if needed, though v2 prompt suggests against context)
    # result_for_history = order_details.dict() # Or format as needed
    # update_conversation_history(
    #     llm_response.rewritten_query or llm_response.original_query,
    #     result_for_history,
    #     llm_response.is_followup,
    #     session_id
    # )

    return MagicApiResponse(
        original_query=llm_response.original_query,
        selected_api=llm_response.selected_api,
        order_status='CONFIRMED',
        response=response_text,
        order_details=order_details
    )

async def handle_get_results_only(
    llm_response: LLMResponse,
    user_details: UserDetails,
    session_id: Optional[str]
) -> MagicApiResponse:
    """Logic for 'getResultsOnly' API type."""
    query_to_execute = (
        llm_response.rewritten_query or llm_response.original_query
    )

    # 1. Get the SQL query first (optional, but matches Node.js flow)
    try:
        sql_info = await crud.get_alloydb_sql(query_to_execute)
        print(f"vkanishk: sql_info: {sql_info}")
        generated_sql = sql_info.get_sql.sql
        params = sql_info.get_sql.params
        print(f"Generated SQL: {generated_sql}, Params: {params}")
    except Exception as e:
        print(
            f"Failed to get SQL via get_alloydb_sql: {e}. "
            "Proceeding without it."
        )
        generated_sql = "Error retrieving generated SQL"
        params = []

    # 2. Execute the NL query to get actual results
    try:
        db_result_raw = await crud.execute_alloydb_nl_query(
            query_to_execute, user_details.user_id
        )
        print(f"vkanishk: db_result_raw: {db_result_raw}")
        results = _transform_db_result(db_result_raw)
        flat_result = results[0]['value'].execute_nl_query if results else []
        response_text = "Here are the results based on your query."
    except Exception as e:
        print(f"Failed to execute NL query: {e}")
        return MagicApiResponse(
            original_query=llm_response.original_query,
            selected_api=llm_response.selected_api,
            response=(
                f"Sorry, I couldn't retrieve results for your query. Error: {e}"
            ),
            nl2sql=generated_sql,
            params=params,
            result=[]
        )

    # Update history (if needed)
    # update_conversation_history(
    #     query_to_execute, results, llm_response.is_followup, session_id
    # )

    return MagicApiResponse(
        original_query=llm_response.original_query,
        rewritten_query=query_to_execute,
        selected_api=llm_response.selected_api,
        response=response_text,
        nl2sql=generated_sql,
        params=params,
        result=flat_result
    )

async def handle_get_summary_only(
    llm_response: LLMResponse,
    user_details: UserDetails, # Not strictly needed but passed for consistency
    session_id: Optional[str]
) -> MagicApiResponse:
    """Logic for 'getSummaryOnly' API type."""
    query_to_execute = (
        llm_response.rewritten_query or llm_response.original_query
    )

    try:
        summary_response = await crud.get_alloydb_sql_summary(
            query_to_execute
        )
        # Adjust parsing based on actual summary structure
        summary_text = summary_response.get_sql_summary.get(
            "answer", "Summary not available."
        )
    except Exception as e:
        print(f"Failed to get summary: {e}")
        summary_text = (
            f"Sorry, I couldn't generate a summary for your query. Error: {e}"
        )

    # Update history (if needed)
    # update_conversation_history(
    #     query_to_execute, summary_text, llm_response.is_followup, session_id
    # )

    return MagicApiResponse(
        original_query=llm_response.original_query,
        rewritten_query=query_to_execute,
        selected_api=llm_response.selected_api,
        response=summary_text,
    )

async def handle_get_summary_and_results(
    llm_response: LLMResponse,
    user_details: UserDetails,
    session_id: Optional[str]
) -> MagicApiResponse:
    """Logic for 'getSummaryAndResults' API type."""
    query_to_execute = (
        llm_response.rewritten_query or llm_response.original_query
    )

    # 1. Get Summary
    try:
        summary_response = await crud.get_alloydb_sql_summary(query_to_execute)
        summary_text = summary_response.get_sql_summary.get(
            "answer", "Summary not available."
        )
    except Exception as e:
        print(f"Failed to get summary: {e}")
        summary_text = f"Sorry, I couldn't generate a summary. Error: {e}"

    # 2. Get SQL (Optional, matches Node.js)
    try:
        sql_info = await crud.get_alloydb_sql(query_to_execute)
        print(f"vkanishk: sql_info: {sql_info}")
        generated_sql = sql_info.get_sql.sql
        params = sql_info.get_sql.params
    except Exception as e:
        print(f"Failed to get SQL: {e}")
        generated_sql = "Error retrieving generated SQL"
        params = []

    # 3. Get Results
    try:
        db_result_raw = await crud.execute_alloydb_nl_query(
            query_to_execute, user_details.user_id
        )
        results = _transform_db_result(db_result_raw)
        flat_result = results[0]['value'].execute_nl_query if results else []
    except Exception as e:
        print(f"Failed to execute NL query for results: {e}")
        # Return summary only if results fail
        return MagicApiResponse(
            original_query=llm_response.original_query,
            rewritten_query=query_to_execute,
            selected_api=llm_response.selected_api,
            response=(
                summary_text +
                f"\n\nNote: Could not retrieve detailed results. Error: {e}"
            ),
            nl2sql=generated_sql,
            params=params,
            result=[]
        )

    # Update history (if needed)
    # update_conversation_history(
    #     query_to_execute, results, llm_response.is_followup, session_id
    # )

    return MagicApiResponse(
        original_query=llm_response.original_query,
        rewritten_query=query_to_execute,
        selected_api=llm_response.selected_api,
        response=summary_text,
        nl2sql=generated_sql,
        params=params,
        result=flat_result
    )