from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from typing import AsyncIterator, Generator
from pydantic import BaseModel
from service import MySQLSearch
import uvicorn
from sqlalchemy.engine import Engine
from db import get_engine
from config import logger, log_execution

engine: Engine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Asynchronous context manager to handle the application's lifespan events.

    This function is executed when the application starts up and shuts down.
    It creates and disposes of the AlloyDB database engine.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    global engine
    logger.info("Starting up and creating database engine...")

    engine = get_engine()
    yield
    logger.info("Shutting down and disposing database engine...")
    if engine:
        engine.dispose()


def get_db() -> Generator[Engine, None, None]:
    """
    FastAPI dependency to provide a database engine session.

    Yields:
        Engine: The SQLAlchemy engine instance.

    Raises:
        HTTPException: If the database engine is not initialized.
    """
    if not engine:
        raise HTTPException(
            status_code=500, detail="Database connection not initialized."
        )
    yield engine


app = FastAPI(
    title="Hybrid Search Mysql",
    description="An API for RAG based Hybrid search using MySQL database.",
    lifespan=lifespan,
)

# Allow CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


class MySQLVector(BaseModel):
    question: str
    filters: dict


@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
async def root(request: Request):
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
            <h2>Welcome to the Hybrid Search MySQL FastAPI Service!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """


@app.get(
    "/list-products",
    summary="List of products to show for display",
    description="Returns a list of products with image url",
)
@log_execution(is_api=True)
async def get_product_list(engine: Engine = Depends(get_db)):
    """Fetch and return a list of products for display.

    The list includes product details along with image URLs, retrieved from AlloyDB
    using the `show_products` method.

    Returns:
        list: A list of product records with associated image URLs.
    """
    get_product_obj = MySQLSearch(engine)
    product_list = await get_product_obj.show_products()
    return product_list


@app.get(
    "/list-brands",
    summary="List of brands to show in filter",
    description="Returns a list of brand names for the filter",
)
@log_execution(is_api=True)
async def brand_data(engine: Engine = Depends(get_db)):
    """Fetch and return a list of brands for filters.

    The list includes brand details.

    Returns:
        list: A list of brands to show for filters.
    """
    get_brand_obj = MySQLSearch(engine)
    brand_list = await get_brand_obj.show_brands()
    return brand_list


@app.get(
    "/list-categories",
    summary="List of categories to show in filter",
    description="Returns a list of category names for the filter",
)
@log_execution(is_api=True)
async def categories_data(engine: Engine = Depends(get_db)):
    """Fetch and return a list of categories for filters.

    The list includes category details.

    Returns:
        list: A list of categories to show for filters.
    """
    get_category_obj = MySQLSearch(engine)
    category_list = await get_category_obj.show_categories()
    return category_list


@app.post(
    "/mysql/vector",
    summary="Perform vector search on MySQL",
    description="Accepts the question as input parameter and returns result for tabular output",
    responses={
        200: {"description": "Purchase order approved successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def mysql_vector_search(request: MySQLVector, engine: Engine = Depends(get_db)):
    """Execute a vector-based semantic search in MySQL and return matched results.

    Args:
        request (MySQLVector): Request payload containing the user's `question`.

    Returns:
        dict: {
            "vector": Any  # results from the MySQL vector search
        }
    """

    question = request.question
    filters = request.filters
    search_obj = MySQLSearch(engine)
    result = await search_obj.vector_search(question, filters)
    if "Error" in result:
        raise HTTPException(status_code=400, detail=result["Error"])
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)
