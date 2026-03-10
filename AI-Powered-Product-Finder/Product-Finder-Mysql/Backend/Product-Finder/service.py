from sqlalchemy import text, bindparam
import pandas as pd
import sqlparse

from config import (
    MYSQL_SCHEMA_NAME,
    TABLE_NAME,
    VECTOR_THRESHOLD,
    EMBEDDING_MODEL,
    logger,
)

class MySQLSearch:
    """Runs semantic vector search workflows against a MySQL dataset.

    Attributes:
        question (str): Natural-language query used to generate embeddings and search.
    """

    def __init__(self, engine):
        self.engine = engine

    async def show_products(self) -> dict:
        """
        Fetch a small set of distinct products for UI display.
        Uses DISTINCT ON(articleType) to avoid repeated article types.

        Returns:
            dict: {"products": List[dict]} or a message when no results found.
        """
        # Compose a SQL statement that samples in-stock, non-free, non-innerwear items
        query = text(
            f"""
            SELECT
                id, gender, masterCategory, subCategory, articleType, baseColour,
                season, year, `usage`, productDisplayName, link, unitPrice,
                discount, finalPrice, rating, stockCode, stockStatus
            FROM {MYSQL_SCHEMA_NAME}.{TABLE_NAME}
            WHERE id in (
                SELECT MIN(id)
                FROM  {MYSQL_SCHEMA_NAME}.{TABLE_NAME}
                WHERE stockStatus LIKE '%In Stock%'
                AND masterCategory <> 'Free items'
                AND subcategory NOT IN ('Innerwear','Loungewear and Nightwear')
                GROUP BY articleType
            )
            LIMIT 9;
        """
        )

        # Open a short-lived connection and execute the query
        with self.engine.connect() as connection:
            logger.info("Database connection established for product sampling.")
            result = connection.execute(query)

            # Convert rows to mapping dicts for key-based access
            rows = result.mappings().all()

            # Handle empty result set gracefully
            if not rows:
                logger.warning("No results returned from Show products query.")
                return {"products": "No results found for the Show products search!"}

            # Map selected fields to a clean response schema
            product_details = []
            for r in rows:
                product_details.append(
                    {
                        "id": r.get("id"),
                        "gender": r.get("gender"),
                        "masterCategory": r.get("masterCategory"),
                        "subCategory": r.get("subCategory"),
                        "articleType": r.get("articleType"),
                        "baseColour": r.get("baseColour"),
                        "season": r.get("season"),
                        "year": r.get("year"),
                        "usage": r.get("usage"),
                        "productDisplayName": r.get("productDisplayName"),
                        "link": r.get("link"),
                        "unitPrice": r.get("unitPrice"),
                        "discount": r.get("discount"),
                        "finalPrice": r.get("finalPrice"),
                        "rating": r.get("rating"),
                        "stockCode": r.get("stockCode"),
                        "stockStatus": r.get("stockStatus"),
                    }
                )
            logger.info("Query executed successfully for product sampling.")
            return {"products": product_details}

    async def show_brands(self) -> dict:
        """
        Provides data for the UI dropdown on brand selection.

        Returns:
            dict: {"brands": List[]} or a message when no results found.
        """
        query = text(
            f"""
        SELECT DISTINCT brand
        FROM {MYSQL_SCHEMA_NAME}.{TABLE_NAME}
        ORDER BY brand;
        """
        )
        brand_list = []
        with self.engine.connect() as connection:
            logger.info("Database connection established!")
            result = connection.execute(query)
            rows = result.mappings().all()
            if not rows:
                logger.warning("No results returned from query.")
                return {"brands": "No results found for the Show brands search!"}

        for row in rows:
            brand_list.append(row["brand"])
        logger.info("Query executed successfully for brand details.")
        return {"brands": brand_list}

    async def show_categories(self) -> dict:
        """
        Provides data for the UI dropdown on category selection.

        Returns:
            dict: {"categories": List[]} or a message when no results found.
        """
        query = text(
            f"""
        SELECT DISTINCT mastercategory
        FROM {MYSQL_SCHEMA_NAME}.{TABLE_NAME}
        WHERE mastercategory != 'Free Items'
        ORDER BY mastercategory;
        """
        )
        category_list = []
        with self.engine.connect() as connection:
            logger.info("Database connection established!")
            result = connection.execute(query)
            rows = result.mappings().all()
            if not rows:
                logger.warning("No results returned from query.")
                return {
                    "categories": "No results found for the Show categories search!"
                }

        for row in rows:
            category_list.append(row["mastercategory"])
        logger.info("Query executed successfully for category details.")
        return {"categories": category_list}

    # Vector search: uses embedding similarity
    async def vector_search(self, question: str, filters: dict) -> dict:
        """Perform vector-based semantic search in MySQL and return top matches.

        Generates an embedding for the input question, binds it to the SQL query,
        and retrieves the highest-scoring rows by cosine similarity.

        Returns:
            dict: On success, a list of product records
        """
        query = text(
            f"""    
        SELECT
        productDisplayName, 
        link, 
        unitPrice,
        discount,
        finalPrice, 
        rating
        FROM {MYSQL_SCHEMA_NAME}.{TABLE_NAME}
        WHERE
            (:category  IS NULL OR masterCategory = :category)
        AND (:brand     IS NULL OR brand = :brand)
        AND (:min_price IS NULL OR finalPrice >= :min_price)
        AND (:max_price IS NULL OR finalPrice <= :max_price)
        AND (:rating    IS NULL OR rating >= :rating)
        AND 1-(approx_distance(combined_description_embedding, @query_vector, 'distance_measure=cosine')) >= :vector_threshold
        ORDER BY 1-(approx_distance(combined_description_embedding, @query_vector, 'distance_measure=cosine')) DESC;"""
        )

        # Connect to the database and execute the query
        try:
            with self.engine.connect() as conn:
                logger.info("Connected to MySQL DB.")

                conn.execute(
                    text(
                        """
                    SET @query_vector = mysql.ML_EMBEDDING(:embedding, :question);
                """
                    ),
                    {"question": question, "embedding": EMBEDDING_MODEL},
                )
                price = filters.get("price") or {}
                params = {
                    "category": filters.get("category"),
                    "brand": filters.get("brand"),
                    "min_price": price.get("min"),
                    "max_price": price.get("max"),
                    "rating": filters.get("rating"),
                    "vector_threshold": VECTOR_THRESHOLD,
                }
                query = query.bindparams(
                    *(bindparam(k, value=v) for k, v in params.items())
                )
                compiled = query.compile(
                    dialect=self.engine.dialect, compile_kwargs={"literal_binds": True}
                )
                raw_sql = str(compiled)
                formatted_sql = sqlparse.format(
                    raw_sql, 
                    reindent=True, 
                )
                sql_string = formatted_sql
                result = conn.execute(query)
                rows = result.fetchall()
                columns = result.keys()
                df_result = pd.DataFrame(rows, columns=columns)
                logger.info("Query executed successfully !")
                df_result.astype(str)
                details = df_result.to_dict(orient="records")
                result = {"sql_command": sql_string, "details": details}
                return result
        except Exception as e:
            logger.error(f"Error executing the query!! :{e}")
            return {"Error": f"Error occured :{e}"}
