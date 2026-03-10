from db import get_engine
from sqlalchemy import text, bindparam
from config import *
from utils import *
import json, re
from typing import Any, Dict, List, Tuple
import vertexai
from vertexai.preview.generative_models import GenerativeModel
import traceback
import sqlparse

class CloudSQLSearchTypes:
    """
    Encapsulates search operations against Cloud SQL table `cloudsql_demo.fashion_products`.

    Supports:
      - Vector search: ranks by semantic similarity (embedding distance).
      - Hybrid search: blends full-text search and vector similarity.

    Args:
        question: Natural-language user query used to compute embeddings and drive text search.
    """
    async def show_products(self, engine) -> dict:
        """
        Fetch a small set of distinct products for UI display.
        Uses DISTINCT ON(articleType) to avoid repeated article types.

        Returns:
            dict: {"products": List[dict]} or a message when no results found.
        """
        # Compose a SQL statement that samples in-stock, non-free, non-innerwear items
        query = text(
            f"""
            SELECT id, gender, mastercategory, subcategory, articletype, basecolour, season, year,
                   usage, productdisplayname, link, unitprice, discount, finalprice, rating,
                   stockcode, stockstatus
            FROM (
                SELECT DISTINCT ON (articleType) *
                FROM {CLOUDSQL_SCHEMA_NAME}.{TABLE_NAME}
                WHERE stockStatus = 'In Stock'
                  AND masterCategory <> 'Free items'
                  AND subCategory <> 'Innerwear'
                  AND subCategory <> 'Loungewear and Nightwear'
                ORDER BY articleType
            ) AS distinct_articles
            LIMIT 9;
            """
        )

        # Open a short-lived connection and execute the query
        with engine.connect() as connection:
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
                        "masterCategory": r.get("mastercategory"),
                        "subCategory": r.get("subcategory"),
                        "articleType": r.get("articletype"),
                        "baseColour": r.get("basecolour"),
                        "season": r.get("season"),
                        "year": r.get("year"),
                        "usage": r.get("usage"),
                        "productDisplayName": r.get("productdisplayname"),
			"brand":r.get("brand"),
                        "link": r.get("link"),
                        "unitPrice": r.get("unitprice"),
                        "discount": r.get("discount"),
                        "finalPrice": r.get("finalprice"),
                        "rating": r.get("rating"),
                        "stockCode": r.get("stockcode"),
                        "stockStatus": r.get("stockstatus"),
                    }
                )
            logger.info("Query executed successfully for product sampling.")
            return {"products": product_details}

    async def show_brands(self,engine) -> dict:
        """
        Provides data for the UI dropdown on brand selection.
        
        Returns:
            dict: {"brands": List[]} or a message when no results found.
        """
        query = text(f"""
        SELECT DISTINCT brand
        FROM {CLOUDSQL_SCHEMA_NAME}.{TABLE_NAME}
        ORDER BY brand;
        """)
        brand_list = []
        with engine.connect() as connection:
            logger.info(f"Database connection established!")
            result = connection.execute(query)
            rows = result.mappings().all()
            if not rows:
                logger.warning("No results returned from query.")
                return {"brands": "No results found for the Show brands search!"}

        for row in rows:
            brand_list.append(row['brand'])
        logger.info("Query executed successfully for brand details.")
        return{"brands":brand_list}


    async def show_categories(self,engine) -> dict:
        """
        Provides data for the UI dropdown on category selection.
        
        Returns:
            dict: {"categories": List[]} or a message when no results found.
        """
        query = text(f"""
        SELECT DISTINCT mastercategory
        FROM {CLOUDSQL_SCHEMA_NAME}.{TABLE_NAME}
        WHERE mastercategory != 'Free Items'
        ORDER BY mastercategory;
        """)
        category_list = []
        with engine.connect() as connection:
            logger.info(f"Database connection established!")
            result = connection.execute(query)
            rows = result.mappings().all()
            if not rows:
                logger.warning("No results returned from query.")
                return {"categories": "No results found for the Show categories search!"}

        for row in rows:
            category_list.append(row['mastercategory'])
        logger.info("Query executed successfully for category details.")
        return{"categories":category_list}

    # Vector search: uses embedding similarity
    def vector_search(self,engine,question, filters, filtered_search, semantic_text):
        """
        Perform a pure vector similarity search.

        Implementation details:
        - Compares the precomputed column `combined_description_embedding`
          with a query embedding computed via `embedding('text-embedding-005', :question)`.
        - `<=>` is the pgvector distance operator (lower = closer/more similar).
        - Ranks results using ROW_NUMBER over the distance and returns top 10.

        Returns:
            On success: list of dict rows (keys in Title Case).
            On failure: error dict with message and details.
        """
        filters_dict = _normalize_filters(filters)
        where_sql, filter_params = _build_where_clause(filters_dict)

        if semantic_text != None:
            question = semantic_text
            
        if filtered_search != None: 
            if where_sql and filtered_search not in where_sql:
                where_sql = where_sql + " AND " + filtered_search
            else:
                where_sql = "WHERE " + filtered_search

        params = {"question": question, "vector_threshold": VECTOR_THRESHOLD}
        params.update(filter_params)

        query = text(f"""
            WITH top_matches AS (
                SELECT *,
                       combined_description_embedding <=> google_ml.embedding('text-embedding-005', :question)::vector AS vector_score
                FROM {CLOUDSQL_SCHEMA_NAME}.{TABLE_NAME}
                {where_sql}
                ORDER BY vector_score
            )

            SELECT
                productDisplayName,
                vector_score,
                link,
                unitPrice,
                discount,
                finalPrice,
                rating
            FROM top_matches
            WHERE vector_score <= :vector_threshold;
            """
        )

        query = query.bindparams(
                        *(bindparam(k, value=v) for k, v in params.items())
                    )
        compiled = query.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
        raw_sql = str(compiled)
        # Format the string
        formatted_sql = sqlparse.format(
            raw_sql, 
            reindent=True, 
        )
        sql_string = formatted_sql
        try:
            
            with engine.connect() as connection:
                logger.info("CloudSQL Database connection established!")
                logger.info(f"Executing the query for vector search: {sql_string}")
                result = connection.execute(query)
                logger.info("CloudSQL Query for vector search executed successfully!")
                rows = result.fetchall()
                columns = [col.capitalize() for col in result.keys()]
                data = [dict(zip(columns, row)) for row in rows]
                
                return {"sql_command": sql_string, "details": data}
        except Exception as e:
            logger.error(f"Vector search failed: {str(e)}", exc_info=True)
            return {"error": "Database query failed", "details": str(e)}

    def hybrid_search(self,engine,question, filters, filtered_search, semantic_text):
        """
        Perform hybrid ranking: 50% full-text relevance (ts_rank_cd) + 50% vector similarity.

        Steps:
        - CTE `query_embedding`: compute query embedding once.
        - CTE `top_matches`: compute hybrid_score:
            * Text relevance: ts_rank_cd(to_tsvector('english', combined_description),
                                        websearch_to_tsquery(:question))
            * Vector similarity: 1 - (distance) to transform distance into similarity.
            * Weighted blend: 0.5 * text + 0.5 * vector.
          Then order by hybrid_score DESC and limit 10.
        - Final SELECT assigns a ROW_NUMBER based on hybrid_score for display.

        Returns:
            On success: list of dict rows (keys in Title Case).
            On failure: error dict with message and details.
        """
        filters_dict = _normalize_filters(filters)
        where_sql, filter_params = _build_where_clause(filters_dict)

        if semantic_text != None:
            question = semantic_text
            
        if filtered_search != None: 
            if where_sql and filtered_search not in where_sql:
                where_sql = where_sql + " AND " + filtered_search
            else:
                where_sql = "WHERE " + filtered_search

        params = {"question": question, "hybrid_threshold": HYBRID_THRESHOLD}
        params.update(filter_params)

        query = text(
            f"""
            WITH query_embedding AS (
            SELECT embedding('text-embedding-005', :question) AS embed),
            top_matches AS (
                SELECT *,
                0.5 * ts_rank_cd(to_tsvector('english', combined_description), websearch_to_tsquery(:question)) +
                0.5 * (1 - (combined_description_embedding <=> query_embedding.embed::vector)) AS hybrid_score
                FROM {CLOUDSQL_SCHEMA_NAME}.{TABLE_NAME}, query_embedding
                {where_sql}
                ORDER BY hybrid_score DESC
                )

            SELECT 
                p.productDisplayName,
                p.link,
                p.unitPrice,
                p.discount,
                p.finalPrice,
                p.rating
            FROM top_matches p
            WHERE hybrid_score >= :hybrid_threshold;
            """
        )
        query = query.bindparams(
                        *(bindparam(k, value=v) for k, v in params.items())
                    )
        compiled = query.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
        raw_sql = str(compiled)
        # Format the string
        formatted_sql = sqlparse.format(
            raw_sql, 
            reindent=True, 
        )
        sql_string = formatted_sql

        try:
            with engine.connect() as connection:
                logger.info("CloudSQL Database connection established!")
                logger.info(f"Executing the query for Hybrid search: {sql_string}")
                result = connection.execute(query)
                logger.info("CloudSQL Query for hybrid search executed successfully!")
                rows = result.fetchall()
                columns = [col.capitalize() for col in result.keys()]
                data = [dict(zip(columns, row)) for row in rows]
                return {"sql_command": sql_string, "details": data}
        except Exception as e:
            logger.error(f"Hybrid search failed: {str(e)}", exc_info=True)
            return {"error": "Database query failed", "details": str(e)}

class IdentifySearchTypes:
    
    def search_strategy_prompt_cloudsql(self,user_query: str) -> str:
        """
        Decision prompt:
        - Vector Search (Semantic meaning)
        - Hybrid Search (Semantic + Keyword search) 
        """

        system_instruction = """
            You are the Decision Engine for a retail product Search System backed by **Cloud SQL for PostgreSQL**.

            This system supports:
            - **Vector Search** - Semantic meaning based search
            - **Hybrid Search** - Combining PostgreSQL full-text search (FTS) + vector similarity

           ============================================================
        0) CATALOG ATTRIBUTE GATE
        ============================================================
        Process the USER QUERY only if it references at least one of:
        id, gender, masterCategory, subCategory, articleType, baseColour, season, year, usage, productDisplayName, brand, unitPrice, discount, finalPrice, rating, stockCode, stockStatus


            If NONE are detected → return this JSON and STOP:

            {
            "selected_strategy": "reject",
            "reasoning": "No catalog attribute present",
            "message": "No results to display",
            "parameters": { "raw_query": "<original>" },
            "decision_path": ["gate:failed"]
            }

            ===========================================================
            1) SEARCH STRATEGY DECISION RULES
            ===========================================================

            Choose EXACTLY ONE of the strategies below.
            REFERENCE URL:
            - Generate embeddings + pgvector usage in Cloud SQL:
            https://docs.cloud.google.com/sql/docs/postgres/generate-manage-vector-embeddings

            -----------------------------------------------------------
            A) VECTOR SEARCH (Pure Semantic Search)
            -----------------------------------------------------------
           USE WHEN:
           - Meaning matters more than exact keywords.
           - User describes concepts, style, looks, or synonyms of catalog attributes.
           - There may be broad category mentions (articleType/subCategory) but the intent is semantic similarity rather than exact text matching.

            EXAMPLES:
            - "Striped polo tshirts for men"

            OUTPUT: selected_strategy = "vector"

            -----------------------------------------------------------
            B) HYBRID SEARCH (Vector + Keyword/Text Search)
            -----------------------------------------------------------
            USE WHEN:
            - Query contains BOTH semantic meaning AND which require full text search, for example part of product names or product descriptions
              (brand names, ids, specific keywords)

            EXAMPLES:
            - "Levis Men Knit Crew socks"

            OUTPUT: selected_strategy = "hybrid"

            NOTES:
            - Hybrid is implemented in Cloud SQL by combining PostgreSQL FTS (tsvector/ts_rank)
            with pgvector similarity.

            -----------------------------------------------------------
            C) REJECT — If NOTHING fits
            -----------------------------------------------------------
            USE WHEN:
            - Query is off-domain (not about products)
            - Or cannot be answered with product catalog attributes + vector/text retrieval

            OUTPUT:

            {
            "selected_strategy": "reject",
            "reasoning": "User question inappropriate to the dataset or unsupported",
            "message": "The question is inappropriate to the product data, so I can't answer it.",
            "parameters": { "raw_query": "<original>" },
            "decision_path": ["gate:passed","strategy:none","reject"]
            }

            ===========================================================
            2) PRIORITY ORDER
            ===========================================================
            1. If mostly meaning → **Vector**
            2. If semantic + explicit keywords/constraints → **Hybrid**
            3. Else → Reject

            ============================================================
            3) PARAMETERS (semantic_text & sql_constraints)
            ============================================================

            When generating "parameters.semantic_text" and "parameters.sql_constraints",
            use the following STRICT TEMPLATE:

            You must convert the USER QUERY into:

            1) semantic_text
               - A compact semantic phrase
               - Contains ONLY the core product/entity
               - NO colors, prices, brands, gender, season, or other constraints


            2) sql_constraints
               - A valid PostgreSQL WHERE predicate WITHOUT the leading "WHERE"
               - Contains ALL structured filters or attributes extracted from the user query except the core entity captured as semantic text
       	       - Use ONLY the catalog attributes, for example:
                 - Colors points to baseColour ILIKE '%<colour>%'
                 - Brands points to brand ILIKE '%<brand>%'
                 - Gender points to gender = 'Men'/'Women'/'Boys'/'Girls'/'Unisex'
                 - Season points to season ILIKE '%<season>%'
                 - Usage or Wear to usage ILIKE '%<usage>%'
                 - Products to productDisplayName ILIKE '%productname%>
               - Price interpretations:
                  under/less than X points to  finalPrice <= X
                  over/more than X points to  finalPrice >= X
                  between X and Y points to  (finalPrice >= X AND finalPrice <= Y)
                  strip currency symbols (₹, $, €)
               - Rating interpretations:
                 - "X star", "X stars", "X star and up", "X stars and up", "X+", "rating X and above"
                   ➝ rating >= X AND rating <= 5
                 - Top ratings points to ratings above 4
               - Discount interpretations:
                 - Strip percent symbols (%)
                 - "under/less than X percent" → discount <= X
                 - "over/more than X percent"  → discount >= X
                 - "between X and Y percent"   → (discount >= X AND discount <= Y)
                 - high discount points to discount above 40%
               - Negations:
                   "no leather" → NOT (combined_description ILIKE '%leather%')
                   "exclude nike" → NOT (brand ILIKE '%nike%')
               - If NO explicit filters exist → sql_constraints = None

            ============================================================
            4) OUTPUT JSON FORMAT (FINAL DECISION OBJECT)
            ============================================================

            {
            "selected_strategy": "vector" | "hybrid" | "reject",
            "reasoning": "Concise explanation referencing the rules",
            "parameters": {
                "semantic_text": "<core semantic phrase without sql_constraints or filters>",
                "sql_constraints": "<valid SQL predicate>",
                "raw_query": "<user_query>"
            },
            "decision_path": ["gate:<passed|failed>", "strategy:<chosen|none>"]
            }

            ===========================================================
            5) SAFETY RULES
            ===========================================================
            - Never fabricate attributes or external facts.
            - If the question is off-topic (weather, politics, medical advice, etc.) → reject.
            """

        return f"""{system_instruction}
            USER QUERY: "{user_query}"
            """


    def _parse_llm_output_payload(self,payload):
        """
        Converts raw model output into a Python dict.
        Handles Markdown fences (```json ... ```), trims whitespace,
        and raises clear errors if decoding fails.
        """
        if isinstance(payload, dict):
            return payload

        if payload is None:
            raise ValueError("Model returned NULL payload")

        s = str(payload).strip()

        # Strip triple backticks with optional language tag (```json ... ``` or ``` ... ```)
        m = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", s, flags=re.DOTALL | re.IGNORECASE)
        if m:
            s = m.group(1).strip()

        # If extra text around JSON, extract from first '{' to last '}'
        if not (s.startswith("{") and s.rstrip().endswith("}")):
            start = s.find("{")
            end = s.rfind("}")
            if start != -1 and end != -1 and end > start:
                s = s[start:end+1].strip()

        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to decode JSON: {e}; preview={s[:300]!r}") from e

        if not isinstance(obj, dict):
            raise ValueError(f"Decoded JSON is not an object: {type(obj)}; value={obj!r}")
        return obj
        
    def get_search_type(self, question: str) -> Dict[str, Any]:
        prompt = self.search_strategy_prompt_cloudsql(question.strip())
        vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
        model = GenerativeModel(GENERATIVE_MODEL)
        response = model.generate_content(prompt)
        decision = self._parse_llm_output_payload(response.text)
        mode = decision['selected_strategy']
        reason = decision['reasoning']
        return {"mode": mode, "reason":reason, "decision": decision}
       
        
        # print("Search strategy: ", mode)
        # if mode == "No results to display":
        #     return {"search_strategy": mode, "reasoning": reason, "details": []}

        # # Normalize filters and build WHERE clause
        # filters_dict = _normalize_filters(filters)
        # where_sql, filter_params = _build_where_clause(filters_dict)
        # print("WHERE SQL: ", where_sql)
        # print("FILTER PARAMS: ", filter_params)

        # return {"SQL Command":query, "Reasoning":reason, "Filter Params":filter_params}