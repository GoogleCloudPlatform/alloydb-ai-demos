import uvicorn
import json
import re
import os

from contextlib import asynccontextmanager
from typing import List, Dict, Any, Union
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
# --- LangChain & Integration Imports ---
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langgraph.prebuilt import create_react_agent

from pydantic import BaseModel

from config import PROJECT_ID, LOCATION, MODEL_NAME, MCP_SERVER_URL, logger

# --- Behavior Prompt (System) ---
CORE_BEHAVIOR_PROMPT = """You are a helpful shopping assistant. Your goal is to help users find the perfect gift or product.
Follow these rules strictly:
1.  **Analyze and Clarify**: When a user asks for a suggestion (e.g., "suggest a gift"), do NOT use tools immediately. First, you MUST ask clarifying questions to understand their needs. Ask for:
    - Gender (e.g., Male, Female, Unisex)
    - Occasion (e.g., Birthday, Wedding, Casual)
    - Color or Style preferences
    - Budget (optional)
2.  **Execute Tool**: 
        - ONLY after you have gathered enough details (at least gender, occasion, and color/style), use the available tools to find relevant products.
        - If the user later asks to *refine, filter, or narrow down* recommendations (e.g., “show only watches”, “filter by black color”, “give cheaper options”), you MUST execute the tool **again** using the new filters.
3.  **Format Response**:
    -   If you are asking a clarifying question, respond with plain text.
    -   If you have used the tool and are presenting results, you MUST respond with a single JSON object. Do not add any text before or after the JSON. The JSON object must have two keys:
        -   `"message"`: A friendly introductory sentence (e.g., "Here are top *[n]* suggestions based on your preferences:").
        -   `"products"`: A list of JSON objects, where each object represents a product and has the keys `"productDisplayName"`, `"brand"`, `"unitPrice"`,`"finalPrice"`,`"discount"`,`"rating"` and `"link"`.
""".strip()

# --- Data Models ---
class Message(BaseModel):
    role: str
    content: str

class Product(BaseModel):
    productDisplayName: str
    rating: float = 0.0
    unitPrice: float
    finalPrice: float
    discount: float = 0.0
    brand: str = ""
    link: str = ""

class ChatRequest(BaseModel):
    question: str
    history: List[Message] = []

class ChatResponse(BaseModel):
    answer: str
    products: List[Product] = []


# --- Helper Functions ---
def extract_text_from_message(content: Union[str, List[Union[str, Dict]]]) -> str:
    """
    Extracts plain text from complex LangChain message content types.
    Args:
        content: The content field of a LangChain message (str or list of parts).
    Returns:
        str: The combined text content.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if "text" in part:
                    parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content)

def reconstruct_history(history_data: List[Dict[str, str]]) -> List[BaseMessage]:
    """
    Converts a list of raw dictionary messages into LangChain Message objects.
    Args:
        history_data: List of dicts with 'role' and 'content' keys.
    Returns:
        List[BaseMessage]: A list of HumanMessage and AIMessage objects.
    """
    messages = []
    if not history_data:
        return messages
    for msg in history_data:
        if hasattr(msg, "role") and hasattr(msg, "content"):
            role = msg.role
            content = msg.content
        else:
            # If msg is a dict
            role = msg.get("role")
            content = msg.get("content")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages

# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the lifecycle of the application resources.
    Initializes the Vertex AI LLM, connects to the MCP Server, and loads tools
    BEFORE the server starts accepting requests.
    """
    logger.info("--- Server Starting: Initializing resources ---")
    try:
        # Initialize Vertex AI LLM
        # Setting temperature to 0.1 for deterministic tool usage
        llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            project=PROJECT_ID,
            location=LOCATION,
            temperature=0.1,
        )

        # We simply instantiate it.
        mcp_client = MultiServerMCPClient({
            "gift_server": {
                "transport": "http",
                "url": MCP_SERVER_URL,
            }
        })
        logger.info("Connecting to MCP Server ")
        tools = await mcp_client.get_tools()
        print(f"Successfully fetched {len(tools)} tools.")
        # Create Agent
        agent_executable = create_react_agent(llm, tools)
        # Store in app.state for global access within endpoints
        app.state.agent = agent_executable
        logger.info("Agent initialized and stored in app.state.")
        # Application runs while this yield is active
        yield
        logger.info("--- Server Shutting Down: Closing connection ---")
    except Exception as e:
        logger.critical(f"CRITICAL ERROR during startup: {e}", exc_info=True)
        # Re-raise to prevent the server from starting in a broken state
        raise e

# --- FastAPI Application ---
app = FastAPI(
    lifespan=lifespan,
    title="AlloyDB MCP Chatbot",
    description="FastAPI MCP client using LangGraph.",
    version="1.0.0"
)
# CORS is vital for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", 
response_class=JSONResponse,
summary="To get the health status of the server",
description="To check the health status of the server and see the status ok"
)
async def health_check():
    """
    Simple health check endpoint for load balancers.
    """
    if not hasattr(app.state, "agent"):
        return JSONResponse(status_code=503, content={"status": "initializing"})
    return {"status": "ok"}

@app.post("/chat",
response_model=ChatResponse,
summary="Submit a user prompt to the chatbot",
description="Processes the user's question and optional history via the MCP-powered agent, returning an answer and any recommended products."
)
async def chat_endpoint(payload: ChatRequest, request: Request):
    """
    Main chat endpoint. Accepts a raw JSON body with 'question' and optional 'history'.
    Args:
        request: The FastAPI request object (used to access app.state).
        payload: The parsed JSON body containing user input.
    Returns:
        JSON response containing the answer text and strict product data.
    """
    # 1. Access the pre-initialized agent
    # Using getattr defaults to None to avoid crashing if state isn't ready
    agent = getattr(request.app.state, "agent", None)
    if not agent:
        logger.error("Agent not initialized in app.state")
        raise HTTPException(status_code=503, detail="Agent system not initialized")
    # 2. Validate Input
    question = payload.question
    history = payload.history
    if not question:
        raise HTTPException(status_code=400, detail="Missing 'question' in request body")
    # 3. Build Conversation State
    # Start with the System Prompt to enforce behavior
    conversation_chain = [SystemMessage(content=CORE_BEHAVIOR_PROMPT)]
    # Add history
    conversation_chain.extend(reconstruct_history(history))
    # Add current question
    conversation_chain.append(HumanMessage(content=question))
    state = {"messages": conversation_chain}
    try:
        # 4. Run Agent (Async)
        logger.info(f"Invoking agent for question: {question}...")
        # ainvoke executes the ReAct loop.
        result = await agent.ainvoke(state)
        # 5. Extract Response
        last_message = result["messages"][-1]
        response_text = extract_text_from_message(last_message.content)
        try:
            # Parse Response: Use regex to find a JSON object in the response.
            # re.DOTALL allows '.' to match newlines.
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
 
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                # Success: Return structured data
                return {
                    "answer": data.get("message", "Here are your products:"),
                    "products": data.get("products", [])
                }
            else:
                # Fallback: Treat as a clarifying question (plain text)
                return {
                    "answer": response_text,
                    "products": []
                }
        except json.JSONDecodeError:
            logger.warning(f"Agent returned text that looked like JSON but failed to parse, falling back to text. Content: {response_text[:200]}")
            return {
                "answer": response_text,
                "products": []
            }
    except Exception as e:
        logger.error(f"Error processing chat request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal processing error")

if __name__ == "__main__":
    uvicorn.run("mcp_client:app", host="0.0.0.0", port=8001, reload=False)