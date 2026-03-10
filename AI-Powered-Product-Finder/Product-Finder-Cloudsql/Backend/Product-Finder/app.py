from fastapi import FastAPI, HTTPException, Request,Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.engine import Engine
import asyncio
from service import CloudSQLSearchTypes, IdentifySearchTypes
import uvicorn
from config import log_execution, logger
from db import get_engine
import traceback

app = FastAPI(title="Hybrid search for CloudSQL API",
    description="An API for Hybrid Search using CloudSQL database.")

# Allow CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class CloudSqlSearchRequest(BaseModel):
    question: str
    filters: dict

class CloudSqlSearchResponse(BaseModel):
    search_type : str
    reason: str
    answer: dict

@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
async def root(request: Request):
    base_url = str(request.base_url).rstrip("/")
    docs_url = f"{base_url}/docs"
    return f"""
    <!DOCTYPE html>
    <html>
        <head><title>Welcome</title></head>
        <body>
            <h2>Welcome to the CloudSQL FastAPI Service!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """

# ------ ENDPOINTS -------- #
@app.get(
    "/list-products",
    summary="List of products to show for display",
    description="Returns a list of products with image url",
)
@log_execution(is_api=True)
async def get_product_list(engine: Engine = Depends(get_engine)):
    """Fetch and return a list of products for display.

    The list includes product details along with image URLs, retrieved from AlloyDB
    using the `show_products` method.

    Returns:
        list: A list of product records with associated image URLs.
    """
    get_product_obj = CloudSQLSearchTypes()
    product_list = await get_product_obj.show_products(engine)
    return product_list

@app.get(
    "/list-brands",
    summary="List of brands to show in filter",
    description="Returns a list of brand names for the filter",)
@log_execution(is_api=True)
async def brand_data(engine: Engine = Depends(get_engine)):
    """Fetch and return a list of brands for filters.

    The list includes brand details.

    Returns:
        list: A list of brands to show for filters.
    """
    get_brand_obj = CloudSQLSearchTypes()
    brand_list = await get_brand_obj.show_brands(engine)
    return brand_list

@app.get(
    "/list-categories",
    summary="List of categories to show in filter",
    description="Returns a list of category names for the filter",)
@log_execution(is_api=True)
async def categories_data(engine: Engine = Depends(get_engine)):
    """Fetch and return a list of categories for filters.

    The list includes category details.

    Returns:
        list: A list of categories to show for filters.
    """
    get_category_obj = CloudSQLSearchTypes()
    category_list = await get_category_obj.show_categories(engine)
    return category_list

@app.post(
    "/cloudsql/search",
    summary="Perform Vector and Hybrid search in cloudsql decided automatically based on the question asked",
    description="Accepts question and filters as input, executes the search logic identified, and returns the response.",
    response_model=CloudSqlSearchResponse
)
@log_execution(is_api=True)
async def search(request: CloudSqlSearchRequest, engine: Engine = Depends(get_engine)):
    """Performs multiple search types (vector, hybrid) concurrently.

    Args:
        request (CloudSqlSearchRequest): Contains question and filters.
    Returns:
        dict: A dictionary with results of the choosen search type."""
    try:
        question = request.question
        filters = request.filters

        identify_obj = IdentifySearchTypes()
        llm_response = identify_obj.get_search_type(question)
        search_type = llm_response["mode"]
        reason = llm_response["reason"]
        decision = llm_response["decision"]
        sql_constraints = decision.get("parameters").get("sql_constraints")
        filtered_search = None if sql_constraints == "None" else sql_constraints
        semantic_text = decision.get("parameters").get("semantic_text")

        search_obj = CloudSQLSearchTypes()
        answer = {}
        if search_type.lower() == "vector":                          
            answer =  search_obj.vector_search(engine,question,filters, filtered_search, semantic_text)

        elif search_type.lower() == "hybrid":
            answer =  search_obj.hybrid_search(engine,question,filters, filtered_search, semantic_text)

        return {"search_type": search_type, "reason": reason, "answer": answer}
    except Exception as e:
        logger.error(f"Error during search: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
