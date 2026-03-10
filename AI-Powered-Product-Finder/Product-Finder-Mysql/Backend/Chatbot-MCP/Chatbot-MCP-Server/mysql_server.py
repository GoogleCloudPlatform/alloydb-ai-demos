
"""
FastMCP server for retrieving product recommendations from CloudSQL for MySQL 
using pgvector-based vector similarity search.
"""

import os
import json
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import time
from typing import List
from config import db_name

# FastMCP
from fastmcp import FastMCP

# Local MySQL connector client
import mysql_connection as mysql_conn

import logging
 
# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mysql-chatbot")
 
logger.info("--- Server Starting: Initializing resources ---")

# --- FastMCP Server and Tool Definitions ---

mcp = FastMCP("MySQL Retail Recommendation Server")

@mcp.tool()
def retrieve_neighbors_from_mysql(question: str) -> str:
    """
    Retrieve nearest-neighbor products from CloudSQL for MySQL for the given natural language query.

    Args:
        question (str): Natural language description of desired product or attributes.
    Returns:
        str: JSON-formatted list of dict records for the top K matches.
    """
    logger.info(f"\n--- TOOL CALLED: retrieve_neighbors_from_mysql for question: '{question}' ---")
    try:
        # 1) Build engine via Cloud SQL Python Connector
        engine = mysql_conn.connect_with_connector()
        
        # 3) Execute vector similarity search using pgvector
        sql = sqlalchemy.text(f"""SELECT id,
                gender,
                masterCategory,
                subCategory,
                articleType,
                baseColour,
                season,
                year,
                `usage`,
                productDisplayName,
                brand,
                link,
                unitPrice,
                discount,
                finalPrice,
                rating,
                stockCode,
                stockStatus,

            combined_description,
            1-(approx_distance(combined_description_embedding, @query_vector, 'distance_measure=cosine')) AS cosine_similarity
        FROM
            {db_name}.fashion_products
        ORDER BY
            cosine_similarity desc
        LIMIT 5;""")

        with engine.connect() as conn:
            conn.execute(text("""
            SET @query_vector = mysql.ML_EMBEDDING('text-embedding-005', :question);
            """),{"question": question})
            result = conn.execute(sql)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
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
