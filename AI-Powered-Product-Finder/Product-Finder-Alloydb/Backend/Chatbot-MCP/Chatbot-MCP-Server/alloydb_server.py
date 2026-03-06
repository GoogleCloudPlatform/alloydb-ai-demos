""" FastMCP server for retrieving product recommendations from AlloyDB using vector similarity search."""
import os
import pandas as pd
import sqlalchemy

# Google Cloud Imports
from google.cloud.alloydb.connector import Connector
import allodb_connection as alloydb_conn
from config import INSTANCE_URI, DB_NAME,DB_PASSWORD, DB_USER, SCHEMA_NAME
# FastMCP import
from fastmcp import FastMCP


# --- FastMCP Server and Tool Definitions ---

mcp = FastMCP("AlloyDB Retail Recommendation Server")
alloydb_client = alloydb_conn.AlloyDBClient(INSTANCE_URI,DB_USER,DB_PASSWORD,DB_NAME)
engine = alloydb_client.create_engine()


@mcp.tool()
def retrieve_neighbors_from_alloydb(question: str) -> str:
    """
    Retrieve nearest-neighbor products from AlloyDB for the given natural language query.

    Args:
        question (str):
            A natural language description of the desired product or attributes.
    Returns:
        str:
            A JSON-formatted string (list of dict records) for the top 10 matches
    """
    try:
        with engine.connect() as conn:
            # This uses AlloyDB AI's built-in function to convert natural language to SQL
            query = sqlalchemy.text(f"""
            SELECT p.id,
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
            FROM {SCHEMA_NAME}.fashion_products p
            WHERE productDisplayName is not NULL
            ORDER BY ref_number
            LIMIT 5;""")
            result = conn.execute(query, {"question":question})
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            if df.empty:
                return "No data was found for this question."
            return df.to_json(orient="records")
    except Exception as e:
        return f"An error occurred while querying the database: {e}"


if __name__ == "__main__":
    # For Cloud Run, it's important to listen on '0.0.0.0' and use the PORT environment variable.
    port = int(os.environ.get("PORT", 5005))
    mcp.run(transport="http", host="0.0.0.0", port=port)
