
"""
FastMCP server for retrieving product recommendations from Cloud SQL for PostgreSQL
using pgvector-based vector similarity search.
"""

import os
import json
import pandas as pd
import sqlalchemy
from typing import List

# FastMCP
from fastmcp import FastMCP

# Local Cloud SQL connector client
import cloudsql_connection as cloudsql_conn
from config import schema_name

import logging
 
# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("cloudsql-chatbot")
 
logger.info("--- Server Starting: Initializing resources ---")
# --- FastMCP Server and Tool Definitions ---

mcp = FastMCP("Cloud SQL Retail Recommendation Server")


@mcp.tool()
def retrieve_neighbors_from_cloudsql(question: str) -> str:
    """
    Retrieve nearest-neighbor products from Cloud SQL for PostgreSQL on the given natural language query.

    Args:
        question (str): Natural language description of desired product or attributes.
    Returns:
        str: JSON-formatted list of dict records for the top K matches.
    """
    logger.info(f"\n--- TOOL CALLED: retrieve_neighbors_from_cloudsql for question: '{question}' ---")
    try:
        # 1) Build engine via Cloud SQL Python Connector
        engine = cloudsql_conn.connect_with_connector()


           # convert to pgvector literal

        # 3) Execute vector similarity search using pgvector
        sql = sqlalchemy.text(f"""SELECT p.id,
              p.gender,
              p.masterCategory,
              p.subCategory,
              p.articleType,
              p.baseColour,
              p.season,
              p.year,
              p.usage,
              p.productDisplayName,
              p.brand,
              p.link,
              p.unitPrice,
              p.discount,
              p.finalPrice,
              p.rating,
              p.stockCode,
              p.stockStatus,
              ROW_NUMBER() OVER (
              ORDER BY combined_description_embedding <=> embedding('text-embedding-005', :question)::vector
            ) AS ref_number
          FROM {schema_name}.fashion_products p
          WHERE productDisplayName is not NULL
          ORDER BY ref_number
          LIMIT 5;""")

        with engine.connect() as conn:
            result = conn.execute(sql, {"question": question})
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            logger.info("Data retrieved successfully.")
            if df.empty:
                return "No data was found for this question."

        logger.info("Data retrieved successfully.")
        if df.empty:
            return json.dumps({"message": "No data found for this question.", "items": []})

        return df.to_json(orient="records")

    except Exception as e:
        logger.info(f"Error in tool execution: {e}")
        return json.dumps({"error": f"An error occurred while querying the database: {e}"})


if __name__ == "__main__":
    # For Cloud Run, it's important to listen on '0.0.0.0' and use the PORT environment variable.
    port = int(os.environ.get("PORT", 5005))
    logger.info(f"Starting MCP server on port {port}")
    mcp.run(transport="http", host="0.0.0.0", port=port)
 