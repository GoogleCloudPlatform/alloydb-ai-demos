import uvicorn
from contextlib import asynccontextmanager
import json
from typing import List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- LangChain & LangGraph Imports ---
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from config import *


# --- Behavior Prompt (System) ---
CORE_BEHAVIOR_PROMPT = """You are a helpful shopping assistant. Your goal is to help users find the perfect gift or product.

Follow these rules strictly:
1.  **Analyze and Clarify**: When a user asks for a suggestion (e.g., "suggest a gift"), do NOT use tools immediately. First, you MUST ask clarifying questions to understand their needs. Ask for:
    - Gender (e.g., Male, Female, Unisex)
    - Occasion (e.g., Birthday, Wedding, Casual)
    - Color or Style preferences
    - Budget (optional)

2.  **Execute Tool**: ONLY after you have gathered enough details (at least gender, occasion, and color/style), use the `retrieve_neighbors_from_alloydb` tool to find relevant products.

3.  **Format Response**:
    -   If you are asking a clarifying question, respond with plain text.
    -   If you have used the tool and are presenting results, you MUST respond with a single JSON object. Do not add any text before or after the JSON. The JSON object must have two keys:
        -   `"message"`: A friendly introductory sentence (e.g., "Here are some suggestions based on your preferences:").
        -   `"products"`: A list of JSON objects, where each object represents a product and has the keys `"productDisplayName"`, `"unitPrice"`,`"rating"`and `"link"`.
""".strip()

# --- Global State ---
agent_app = None
mcp_client = None

# --- Data Models ---
class Message(BaseModel):
    role: str
    content: str

class Product(BaseModel):
    productDisplayName: str
    rating: float = 0.0
    unitPrice: float
    link: str = ""


class ChatRequest(BaseModel):
    question: str
    history: List[Message] = []

class ChatResponse(BaseModel):
    answer: str
    products: List[Product] = []

# --- Helper Functions ---
def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and "text" in part:
                    parts.append(part["text"])
                elif "text" in part:
                    parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts) if parts else ""
    return str(content)

def reconstruct_history(history_data: List[Message]):
    messages = []
    for msg in history_data:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    return messages

# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_app, mcp_client
    print("--- Server Starting: Initializing resources ---")
    try:
        # 1. Initialize Vertex AI LLM
        # Note: ChatVertexAI is fine to use. The warning in your logs is just a deprecation notice for the future.
        llm = ChatVertexAI(
            model_name=MODEL_NAME,
            project=PROJECT_ID,
            location=LOCATION,
            temperature=0.1,
        )

        # 2. Initialize MCP Client
        # We simply instantiate it. We DO NOT use 'await mcp_client.__aenter__()'
        mcp_client = MultiServerMCPClient({
            "gift_server": {
                "transport": "http",
                "url": MCP_SERVER_URL,
            }
        })

        # 3. Fetch tools directly
        print(f"Connecting to MCP Server at {MCP_SERVER_URL}...")
        tools = await mcp_client.get_tools()
        print(f"Successfully fetched {len(tools)} tools.")

        # 4. Create LangGraph Agent
        agent_app = create_react_agent(llm, tools)
        print("Agent initialized successfully.")

        yield  # Server runs here

    except Exception as e:
        print(f"CRITICAL ERROR during startup: {e}")
        raise e
    finally:
        print("--- Server Shutting Down ---")
        # Removed mcp_client.__aexit__ as it is no longer supported in 0.1.0+

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan,
    title="MCP CloudSQL Client Chatbot",
    description="A FastAPI-based MCP CloudSQL client that connects to MCP servers and provides intelligent chatbot capabilities."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
def read_root(request: Request):
    base_url = str(request.base_url).rstrip("/")
    docs_url = f"{base_url}/docs"
    return f"""
    <!DOCTYPE html>
    <html>
        <head><title>Welcome</title></head>
        <body>
            <h2>Welcome to the Chatbot MCP FastAPI Service!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """

@app.post("/chat", 
    response_model=ChatResponse,
    summary="Submit a user prompt to the chatbot",
    description="Processes the user's question and optional history via the MCP-powered agent, returning an answer and any recommended products."
)
async def chat_endpoint(request: ChatRequest):
    if not agent_app:
        raise HTTPException(status_code=503, detail="Agent system not initialized")

    # 1. Build State
    conversation_chain = [SystemMessage(content=CORE_BEHAVIOR_PROMPT)]
    if request.history:
        conversation_chain.extend(reconstruct_history(request.history))
    conversation_chain.append(HumanMessage(content=request.question))

    state = {"messages": conversation_chain}

    try:
        # 2. Run Agent
        result = await agent_app.ainvoke(state)

        # 3. Extract Response
        last_message = result["messages"][-1]
        response_text = extract_text(last_message.content)
        print(f"Raw Agent Response: {response_text}")

        # 4. Parse response for JSON or plain text
        try:
            # Clean the response text by removing markdown fences if they exist
            cleaned_response_text = response_text.strip()
            if cleaned_response_text.startswith("```json"):
                cleaned_response_text = cleaned_response_text[7:]
            if cleaned_response_text.endswith("```"):
                cleaned_response_text = cleaned_response_text[:-3]
            # Attempt to parse the response as JSON
            data = json.loads(cleaned_response_text.strip())
            products_data = data.get("products", [])
            # Rename 'productDisplayName' to 'displayname' for the ChatResponse model if needed,
            # but it's easier to just match the Pydantic model.
            products = []
            for p in products_data:
                # The model now expects productDisplayName, so no aliasing is needed here.
                products.append(Product(**p))
            return ChatResponse(answer=data.get("message", ""), products=products)
        except (json.JSONDecodeError, TypeError):
            # If it's not JSON, it's a follow-up question or a simple text response.
            # The 'products' list will be empty by default.
            return ChatResponse(answer=response_text)

    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("mcp_client:app", host="0.0.0.0", port=8001, reload=False)