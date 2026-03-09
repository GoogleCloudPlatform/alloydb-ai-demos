import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# --- Request Models ---
class MagicApiQueryParams(BaseModel):
  query: str
  userId: Optional[int] = None
  sessionId: Optional[str] = None


# --- LLM Interaction Models ---
class LLMResponse(BaseModel):
  is_followup: Optional[bool] = False  # Default based on Node.js v2 prompt
  product_name: Optional[str] = None
  original_query: str
  rewritten_query: Optional[str] = None
  selected_api: str
  confidence: float


class PredictRowResult(BaseModel):
  # Structure might need adjustment based on actual google_ml.predict_row output
  # This is the main content, usually includes the generated text/JSON
  candidates: List[Dict[str, Any]]
  # Optional fields often included in LLM responses
  usageMetadata: Dict[str, Any]
  modelVersion: str
  createTime: str
  responseId: str


# --- Database Interaction Models ---
class UserDetails(BaseModel):
  user_id: int
  credit_card: str
  shipping_address: str


class GetSqlResult(BaseModel):
  sql: str
  params: Optional[List[Any]] = []


class GetSqlResponse(BaseModel):
  get_sql: GetSqlResult


class GetSqlSummaryResponse(BaseModel):
  get_sql_summary: Dict[str, Any]  # Adjust structure as needed


class ExecuteNlQueryResponse(BaseModel):
  # This structure depends heavily on what execute_nl_query actually returns
  # Assuming it returns a list of dicts for results, or a dict for summary/price
  execute_nl_query: (
      List[Dict[str, Any]] | Dict[str, Any] | Any
  )  # Make this flexible

class ExecuteParameterizedQueryResponse(BaseModel):
  # This structure depends heavily on what execute_nl_query actually returns
  # Assuming it returns a list of dicts for results, or a dict for summary/price
  execute_parameterized_query: (
      List[Dict[str, Any]] | Dict[str, Any] | Any
  )  # Make this flexible


# --- API Response Models ---
class PingResponse(BaseModel):
  status: str
  message: str
  timestamp: str
  port: int  # Assuming port is needed in response


class OrderDetails(BaseModel):
  order_id: Optional[int] = None
  product_name: str
  price: float
  credit_card_last4: str
  shipping_address: str
  user_id: Optional[int] = None
  status: Optional[str] = None
  total_amount: Optional[float] = None  # For orderInsert response
  product: Optional[str] = None  # For orderInsert response


class ErrorResponse(BaseModel):
  error: str
  details: Optional[str] = None
  selected_api: Optional[str] = None


# NEW ONES


# --- Database Interaction Models (Keep relevant ones) ---
# --- API Request/Response Models ---
class ChatRequest(BaseModel):
  query: str
  session_id: str  # Use session_id for thread_id in LangGraph config
  user_id: Optional[int] = None  # Optional override for default user


class ChatResponse(BaseModel):
  response: str
  session_id: str
  # Add any other fields you want to return, e.g., results from tools
  tool_outputs: Optional[List[Dict[str, Any]]] = None
  final_state: Optional[Dict[str, Any]] = None  # For debugging


# --- LangGraph State Definition ---
def add_messages(left: list[BaseMessage], right: list[BaseMessage]):
  """Adds messages to the state, ensuring the order is maintained."""
  return left + right


class AgentState(TypedDict):
  messages: Annotated[List[BaseMessage], add_messages]
  user_details: Optional[UserDetails]
  tool_output: Optional[List[Dict[str, Any]]] = (
      None  # Keep this if you want structured tool output separately
  )
  user_id: int
  original_query: Optional[str] = None  # <-- ADD THIS FIELD


# ... (rest of models.py, including MagicApiResponse) ...


# Ensure MagicApiResponse is defined as it was in your original file
class MagicApiResponse(BaseModel):
  """Response model for the Magic API."""
  original_query: Optional[str] = (
      None  # Make optional if it might not always be available
  )
  rewritten_query: Optional[str] = (
      ""  # LangGraph doesn't easily provide this, keep Optional
  )
  selected_api: Optional[str] = None  # Will try to infer from last tool call
  response: Optional[str] = None  # The final text response from the AI
  order_status: Optional[str] = None
  order_details: Optional[OrderDetails] = None
  nl2sql: Optional[str] = None  # Not generated in this flow
  params: Optional[List[Any]] = None  # Not generated in this flow
  result: Optional[List[Dict[str, Any]] | Dict[str, Any] | Any] = (
      None  # Store parsed tool output here
  )
  a: Optional[Any] = None
  status: Optional[str] = None
  analysis: Optional[str] = None
  priority: Optional[str] = None
  skinType: Optional[str] = None
  productSearch: Optional[str] = None