import json
import re
from typing import Any, Dict, Optional

import crud
from models import LLMResponse, PredictRowResult

# In-memory conversation history (replace with Redis/DB for production)
conversation_history: Dict[str, list] = {}

def _build_api_prompt_v2(query: str) -> str:
    """Builds the JSON prompt string for the LLM call via DB
    (using CORRECT V2 prompt).

    Args:
        query (str): The user's input query.

    Returns:
        str: A JSON string representing the prompt for the LLM.
    """

    # --- CORRECT V2 system prompt ---
    # This instructs the LLM on the desired API selection task and
    # JSON output format
    system_instruction_text = """
      You are an AI assistant for a skincare product database. Your primary goal is to identify user intent and categorize queries into appropriate API endpoints. You must return a structured JSON response with the classification result and nothing else. Analyze queries based on the following categories:

      ## Query Categories and Response Types

      Analyze each user query to determine which selected_api category it belongs to:

      1. **getResultsOnly**: When users request structured information or listings
      2. **getSummaryOnly**: When users seek detailed explanations or comparisons
      3. **getSummaryAndResults**: When users want both listings and detailed information
      4. **orderCheckout**: When users express intent to purchase a specific product
      5. **orderInsert**: when user is confirming to purchase a product.

      ## Response Guidelines

      ### For getResultsOnly queries:
      - Provide concise, structured results (lists, tables, rankings)
      - Focus on factual information without lengthy explanations
      - Include relevant product specifications and pricing

      **Trigger phrases**: "list", "top", "tabulate", "show me", "what are", "display", "rank", "compare", "list by previous orders", "list my orders"

      **Examples**:
      - "List all moisturizers for dry skin"
      - "What are your top 5 sunscreens?"
      - "Show me foundations with SPF"
      - "Tabulate all cleansers under $30"

      ### For getSummaryOnly queries:
      - Provide detailed explanations and in-depth information
      - Include product benefits, key ingredients, and use cases
      - Offer comparative analysis when products are mentioned
      - Address specific concerns mentioned in the query

      **Trigger phrases**: "tell me more about", "why should I", "help me decide", "what's the difference", "explain", "describe"

      **Examples**:
      - "Tell me more about retinol serums"
      - "Why should I prefer hyaluronic acid over glycerin?"
      - "Help me decide between clay masks and sheet masks"
      - "Explain the benefits of niacinamide in skincare"

      ### For getSummaryAndResults queries:
      - Provide structured listings followed by detailed explanations
      - Include both factual information and contextual details
      - Combine elements of both results and summary responses

      **Trigger phrases**: "list and tell me", "show and explain", "compare and describe"

      **Examples**:
      - "List vitamin C serums and tell me more about their benefits"
      - "Show me oil cleansers and explain how to use them"
      - "Compare toners and moisturizers and describe when to use each"

      ### For orderCheckout queries:
      - Confirm the product details and availability
      - Provide pricing information
      - Offer to proceed with checkout
      - Request any necessary information to complete the order

      **Trigger phrases**: "order now", "buy", "purchase", "checkout", "add to cart", "confirm"

      ### For orderInsert queries:
      - process the order and confirm the order.

      **Trigger phrases**: "I confirm the order with product name: <product_name>", "I confirm the order", "yes order"

      **Examples**:
      - "I confirm a new order with product name: Light Ivory Cymbaluxe Skin Tint" # Added 'a new order' for clarity
      - "I confirm the order"
      - "yes order"

      ## Additional Response Requirements

      1. **Ambiguous queries**: If a query could belong to multiple categories, prioritize in this order: orderInsert < orderCheckout < getSummaryAndResults < getSummaryOnly < getResultsOnly

      2. **Product name extraction**:
          - Extract any specific product names mentioned in the query
          - Include the full product name in the product_name field
          - If no product is mentioned, use an empty string or null
          - For partial or ambiguous product mentions, include what was mentioned

      3. **Confidence scoring**:
          - Assign 0.9-1.0 for highly confident classifications
          - Assign 0.7-0.89 for moderate confidence
          - Assign 0.5-0.69 for low confidence
          - Never assign below 0.5

      4. **Exact query reproduction**: Always include the user's query exactly as provided in the original_query field, preserving case and punctuation.

      ## Response Format

      You must provide a structured JSON response and nothing else. The response should follow this exact format:
      ```json
      {
        "original_query": "User's original query",
        "selected_api": "getResultsOnly|getSummaryOnly|getSummaryAndResults|orderCheckout|orderInsert",
        "product_name": "Extracted product name or null",
        "confidence": 0.0-1.0
      }
      ```

      Where:

      original_query: The exact query as entered by the user
      selected_api: The appropriate API to call based on query categorization
      product_name: Any specific product name mentioned in the query (null if none)
      confidence: A decimal between 0.0-1.0 indicating confidence in the categorization
      Do not include any additional text, explanations, or formatting outside of this JSON structure.
      """

    # Create properly formatted JSON prompt object
    prompt_obj = {
        "systemInstruction": {
            "role": "system",
            "parts": [{"text": system_instruction_text}]
        },
        "generationConfig": {"temperature": 0, "seed": 1234567890},
        "contents": [{
            "role": "user",
            "parts": [{"text": f"\nInput Query: {json.dumps(query)}\n"}]
        }]
    }
    
    # Convert Python dict to JSON string and return it directly
    return json.dumps(prompt_obj)

def _parse_llm_json_output(
    text: str, original_query: str
) -> Optional[LLMResponse]:
  """Extracts and parses the JSON from the LLM's text response."""
  # Regex to find JSON block
  match = re.search(r"```json\n([\s\S]*?)\n```", text, re.MULTILINE)
  if not match:
    # Sometimes the LLM might return JSON without the ```json markdown
    # Try parsing the whole text directly, stripping whitespace
    try:
      parsed_result = json.loads(text.strip())
      print("Parsed LLM JSON directly (no ```json found)")
    except json.JSONDecodeError:
      print(
          "Could not extract JSON using regex or direct parse from text:"
          f" {text}"
      )
      return None  # Or return a default error response
  else:
    json_str = match.group(1)
    try:
      parsed_result = json.loads(json_str)
    except json.JSONDecodeError as e:
      print(f"Error parsing extracted JSON: {e}")
      print(f"Problematic JSON string: {json_str}")
      return None  # Or return a default error response

  # Construct LLMResponse, ensuring required fields exist
  try:
    return LLMResponse(
        original_query=original_query,
        # is_followup=parsed_result.get('is_followup', False), # Removed in v2
        product_name=parsed_result.get("product_name"),
        rewritten_query=parsed_result.get(
            "rewritten_query", original_query
        ),  # Use original if not rewritten
        selected_api=parsed_result["selected_api"],  # selected_api is mandatory
        confidence=parsed_result["confidence"],  # confidence is mandatory
    )
  except KeyError as e:
    print(f"Missing mandatory key in LLM JSON response: {e}")
    print(f"Parsed result: {parsed_result}")
    return None  # Or return a default error response


async def get_intent_and_api(
    query: str, session_id: Optional[str]
) -> Optional[LLMResponse]:
  """Gets intent, API selection, and potentially rewritten query from LLM via DB."""
  prompt_json_str = _build_api_prompt_v2(query)

  try:
    # Get raw response from LLM
    db_response: PredictRowResult = await crud.call_llm_predict(prompt_json_str)
    print(f"vkanishk:get_intent_and_api  db_response: {db_response}")
    # Extract the text part containing the JSON
    # Adjust path based on actual 'google_ml.predict_row' response structure
    if (
        db_response
        and db_response.candidates
        and db_response.candidates[0].get("content")
        and db_response.candidates[0]["content"].get("parts")
        and db_response.candidates[0]["content"]["parts"][0].get(
            "text"
        )
    ):

      llm_text_output = db_response.candidates[0]["content"][
          "parts"
      ][0]["text"]
      parsed_response = _parse_llm_json_output(llm_text_output, query)

      # --- Update Conversation History (Optional based on v2 prompt) ---
      # The v2 prompt explicitly states *not* to rely on context.
      # If needed, re-enable this.
      # if session_id and parsed_response:
      #    update_conversation_history(
      #        parsed_response.rewritten_query or query,
      #        "Placeholder for result - depends on where it's called",
      #        parsed_response.is_followup,
      #        session_id
      #    )
      print(f"vkanishk: parsed_response: {parsed_response}")
      return parsed_response
    else:
      print("LLM DB response structure unexpected:", db_response)
      return None  # Or default error response

  except json.JSONDecodeError as e:
    print(f"Fatal Error decoding JSON response from DB: {e}")
    return None  # Or default error response
  except Exception as e:
    print(f"Error during LLM interaction: {e}")
    # Fallback similar to Node.js code
    return LLMResponse(
        original_query=query,
        rewritten_query=query,
        selected_api="getSummaryOnly",  # Default fallback API
        confidence=0.1,
        product_name=None,
    )


def update_conversation_history(
    query: str, result: Any, is_followup: bool, session_id: str
):
  """Updates the in-memory conversation history."""
  if not session_id:
    return
  if session_id not in conversation_history:
    conversation_history[session_id] = []

  if not is_followup:
    conversation_history[session_id] = []  # Clear history for new convos

  conversation_history[session_id].append(
      {"query": query, "result": result, "is_followup": is_followup}
  )

  # Keep only the last 10 entries
  if len(conversation_history[session_id]) > 10:
    conversation_history[session_id].pop(0)