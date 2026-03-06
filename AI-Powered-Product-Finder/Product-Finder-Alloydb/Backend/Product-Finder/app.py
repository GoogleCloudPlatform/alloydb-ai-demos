from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import traceback
from db.alloydb_client import AlloyDBClient
from services.search_case import AlloyDbSearchTypes, IdentifySearchType
from config import INSTANCE_URI, DB_USER, DB_PASSWORD, DB_NAME, log_execution, logger

# ---------- Initialize Engine ----------
alloydb_client = AlloyDBClient(INSTANCE_URI, DB_USER, DB_PASSWORD, DB_NAME)
engine = alloydb_client.create_engine()

# ---------- FastAPI App ----------
app = FastAPI(
    title="Hybrid search for Alloydb API",
    description="An API for Hybrid Search using Alloydb database.",
)

# Allow CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


class SearchRequest(BaseModel):
    question: str
    filters: dict


class SearchResponse(BaseModel):
    search_type: str
    reason: str
    answer: dict


# ---------- Root Endpoint ----------
@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
def root(request: Request):
    """Returns a welcome message and API documentation link.

    Args:
        request (Request): The incoming request object.
    Returns:
        HTMLResponse: A welcome message with a link to the API docs."""
    base_url = str(request.base_url).rstrip("/")
    docs_url = f"{base_url}/docs"
    return f"""
    <!DOCTYPE html>
    <html>
        <head><title>Welcome</title></head>
        <body>
            <h2>Welcome to the Hybrid search FastAPI Service!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """


# ---------- API Endpoint ----------


@app.get(
    "/list-products",
    summary="List of products to show for display",
    description="Returns a list of products with image url",
)
@log_execution(is_api=True)
async def get_product_list():
    """Fetch and return a list of products for display.

    The list includes product details along with image URLs, retrieved from AlloyDB
    using the `show_products` method.

    Returns:
        list: A list of product records with associated image URLs.
    """
    get_product_obj = AlloyDbSearchTypes(engine)
    product_list = await get_product_obj.show_products()
    return product_list


@app.get(
    "/list-brands",
    summary="List of brands to show in filter",
    description="Returns a list of brand names for the filter",
)
@log_execution(is_api=True)
async def brand_data():
    """Fetch and return a list of brands for filters.

    The list includes brand details.

    Returns:
        list: A list of brands to show for filters.
    """
    get_brand_obj = AlloyDbSearchTypes(engine)
    brand_list = await get_brand_obj.show_brands()
    return brand_list


@app.get(
    "/list-categories",
    summary="List of categories to show in filter",
    description="Returns a list of category names for the filter",
)
@log_execution(is_api=True)
async def categories_data():
    """Fetch and return a list of categories for filters.

    The list includes category details.

    Returns:
        list: A list of categories to show for filters.
    """
    get_category_obj = AlloyDbSearchTypes(engine)
    category_list = await get_category_obj.show_categories()
    return category_list


@app.post(
    "/search",
    summary="Perform a hybrid, vector, or NL-to-SQL search based on the configured logic internally",
    description="Accepts a search type and question, runs the appropriate search logic, and returns the answer. Search types: 'vector', 'hybrid', 'nltosql'.",
    response_model=SearchResponse,
)
@log_execution(is_api=True)
async def search(request: SearchRequest):
    """Performs a specified search (vector, hybrid, NL-to-SQL, ai.if).

    Args:
        request (SearchRequest): Contains question and filters.
    Returns:
        dict: The search results based on the identified search type."""
    logger.info(f"Search request received: {request.question},{request.filters}")
    try:
        question = request.question
        filters = request.filters
        question = question.strip()

        identify_search_type_obj = IdentifySearchType(question, engine)
        llm_response = identify_search_type_obj.get_search_type()
        logger.info(f"Search type identified: {llm_response}")
        search_type = llm_response.get("mode")
        reason = llm_response.get("reason")
        decision = llm_response.get("decision")

        if search_type == "reject":
            # raise ValueError("Unsupported search")
            return {"search_type": search_type, "reason": reason, "answer": {"sql_command":"","details":[]}}
        else:
            search_obj = AlloyDbSearchTypes(engine)
            if search_type.lower() == "nl_to_sql":
                answer = await search_obj.nltosql_search(question, filters)
                if len(answer["details"]) == 0:
                    search_type = "vector"
                else:
                    return {"search_type": search_type, "reason": reason, "answer": answer}

            if search_type.lower() == "vector":
                sql_constraints = decision.get("parameters").get("sql_constraints")
                filtered_search = None if sql_constraints == "None" else sql_constraints
                semantic_text = decision.get("parameters").get("semantic_text")
                answer = await search_obj.vector_search(
                    question, filters, filtered_search, semantic_text
                )
                return {"search_type": search_type, "reason": reason, "answer": answer}
            elif search_type.lower() == "hybrid":
                sql_constraints = decision.get("parameters").get("sql_constraints")
                filtered_search = None if sql_constraints == "None" else sql_constraints
                semantic_text = decision.get("parameters").get("semantic_text")
                answer = await search_obj.hybrid_search(
                    question, filters, filtered_search, semantic_text
                )
                return {"search_type": search_type, "reason": reason, "answer": answer}
            elif search_type.lower() == "ai.if":
                query_processed = decision.get("sql_query")
                answer = await search_obj.ai_if_case(query_processed, filters)
                return {"search_type": search_type, "reason": reason, "answer": answer}
            else:
                # raise ValueError(f"Unsupported search type: {search_type}")
                return {"search_type": search_type, "reason": reason, "answer": reason}
    except Exception as e:
        logger.error(f"Error during search: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Run Server ----------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)
