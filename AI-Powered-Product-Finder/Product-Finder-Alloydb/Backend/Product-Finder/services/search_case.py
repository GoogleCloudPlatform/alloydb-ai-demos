# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

from sqlalchemy import text, bindparam  # Build safe SQL statements
from sqlalchemy.engine import Engine
import logging  # Application-level logging
from typing import Dict, Any
import re
import json
import traceback
import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account

import requests
from config import (
    ALLOYDB_SCHEMA_NAME,
    TABLE_NAME,
    VECTOR_THRESHOLD,
    HYBRID_THRESHOLD,
    EMBEDDING,
    NLA_API,
    NLA_SERVICE_ACCOUNT,
    CLUSTER_ID,
    INSTANCE_ID,
    CONTEXT_SET_ID,
    PROJECT_ID,
    LOCATION,
    SCOPES,
)
from services.utils import (
    normalize_filters,
    build_where_clause,
    merge_filter_where,
    merge_where_clauses,
    remove_single_line_comments,
)

# -----------------------------------------------------------------------------
# Logging configuration (module-level)
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)


# -----------------------------------------------------------------------------
# Search Logic
# -----------------------------------------------------------------------------
class AlloyDbSearchTypes:
    """
    Provides multiple search strategies against an AlloyDB-backed catalog:
      - Product sampling/listing (distinct items)
      - Vector search (semantic similarity via embeddings)
      - Hybrid search (full text search + vector similarity)
      - NL-to-SQL search (natural language to executable SQL)
    """

    def __init__(self, engine: Engine) -> None:
        """
        Initialize search service with an SQLAlchemy Engine.

        Args:
            engine (Engine): A pre-configured SQLAlchemy engine (AlloyDB connection).
        """
        # Store engine for per-call connection scopes
        self.engine = engine

        # Per-class logger; helps identify log lines from this service
        self.logger = logging.getLogger("AlloyDbSearchTypes")

    def get_access_token(self):
        # Ensure this points ONLY to your JSON file
        print(f"Using the NLA service account in path: {NLA_SERVICE_ACCOUNT}")
        KEY_PATH = NLA_SERVICE_ACCOUNT

        # 1. Use the specific Audience for the API if an ID token is needed
        # Or stick to the broad cloud-platform scope
        target_scopes = [SCOPES]

        try:
            creds = service_account.Credentials.from_service_account_file(
                KEY_PATH, scopes=target_scopes
            )

            auth_request = google.auth.transport.requests.Request()
            creds.refresh(auth_request)

            # Verify the token exists
            if not creds.token:
                return None

            return creds.token

        except Exception as e:
            print(f"Auth failed: {e}")
            return None

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
            SELECT id, gender, mastercategory, subcategory, articletype, basecolour, season, year,
                   usage, productdisplayname, link, unitprice, discount, finalprice, rating,
                   stockcode, stockstatus
            FROM (
                SELECT DISTINCT ON (articleType) *
                FROM {ALLOYDB_SCHEMA_NAME}.{TABLE_NAME}
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
        with self.engine.connect() as connection:
            self.logger.info("Database connection established for product sampling.")
            result = connection.execute(query)

            # Convert rows to mapping dicts for key-based access
            rows = result.mappings().all()

            # Handle empty result set gracefully
            if not rows:
                self.logger.warning("No results returned from Show products query.")
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
                        "brand": r.get("brand"),
                        "link": r.get("link"),
                        "unitPrice": r.get("unitprice"),
                        "discount": r.get("discount"),
                        "finalPrice": r.get("finalprice"),
                        "rating": r.get("rating"),
                        "stockCode": r.get("stockcode"),
                        "stockStatus": r.get("stockstatus"),
                    }
                )
            self.logger.info("Query executed successfully for product sampling.")
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
        FROM {ALLOYDB_SCHEMA_NAME}.{TABLE_NAME}
        ORDER BY brand;
        """
        )
        brand_list = []
        with self.engine.connect() as connection:
            self.logger.info("Database connection established!")
            result = connection.execute(query)
            rows = result.mappings().all()
            if not rows:
                self.logger.warning("No results returned from query.")
                return {"brands": "No results found for the Show brands search!"}

        for row in rows:
            brand_list.append(row["brand"])
        self.logger.info("Query executed successfully for brand details.")
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
        FROM {ALLOYDB_SCHEMA_NAME}.{TABLE_NAME}
        WHERE mastercategory != 'Free Items'
        ORDER BY mastercategory;
        """
        )
        category_list = []
        with self.engine.connect() as connection:
            self.logger.info("Database connection established!")
            result = connection.execute(query)
            rows = result.mappings().all()
            if not rows:
                self.logger.warning("No results returned from query.")
                return {
                    "categories": "No results found for the Show categories search!"
                }

        for row in rows:
            category_list.append(row["mastercategory"])
        self.logger.info("Query executed successfully for category details.")
        return {"categories": category_list}

    # -------------------------------------------------------------------------
    # Vector search (semantic similarity)
    # -------------------------------------------------------------------------
    async def vector_search(
        self, question: str, filters: dict, filtered_search: str, semantic_text: str
    ) -> dict:
        """
        Find products semantically similar to the user's query using embeddings.

        Args:
            question (str): Natural-language search text
            filters (dict): Filtered results based on user selected filters
            filtered_search (str): Filters captured from user question (Filtered Vector Search)
            semantic_text (str): Core input from question for semantic search

        Returns:
            dict: {
                "sql_command": string,
                "details": List[dict]  # matched product records
            }
        """

        # Preparing parameteres
        # Normalize filters and build WHERE clause
        filters_dict = normalize_filters(filters)
        where_sql, filter_params = build_where_clause(filters_dict)

        if semantic_text is not None:
            question = semantic_text

        if filtered_search is not None:
            if where_sql and filtered_search not in where_sql:
                where_sql = where_sql + " AND " + filtered_search
            else:
                where_sql = "WHERE " + filtered_search

        params = {
            "question": question,
            "embedding": EMBEDDING,
            "vector_threshold": VECTOR_THRESHOLD,
        }
        params.update(filter_params)

        # Preparing Query
        # Compute similarity using google_ml.embedding('text-embedding-005'). Lower is more similar.
        query = text(
            f"""
            WITH top_matches AS (
                SELECT *,
                       combined_description_embedding <=> google_ml.embedding(:embedding, :question)::vector AS vector_score
                FROM {ALLOYDB_SCHEMA_NAME}.{TABLE_NAME}
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
        query = query.bindparams(*(bindparam(k, value=v) for k, v in params.items()))
        compiled = query.compile(
            dialect=self.engine.dialect, compile_kwargs={"literal_binds": True}
        )
        sql_string = str(compiled)

        try:
            with self.engine.connect() as connection:
                self.logger.info("Database connection established for vector search.")
                self.logger.info(f"Executing the query for Vector Search:{sql_string}")
                result = connection.execute(query)
                rows = result.mappings().all()

                if not rows:
                    self.logger.warning("No results returned from vector search.")

                    return {
                        "sql_command": sql_string,
                        "details": [],
                    }

                self.logger.info("Query executed successfully for vector search.")

                # Capturing details in response
                details = []
                for r in rows:
                    details.append(
                        {
                            "productDisplayName": r.get("productdisplayname"),
                            "link": r.get("link"),
                            "unitPrice": r.get("unitprice"),
                            "discount": r.get("discount"),
                            "finalPrice": r.get("finalprice"),
                            "rating": r.get("rating"),
                        }
                    )
                # Return the executed SQL command and details
                return {"sql_command": sql_string, "details": details}

        except Exception as e:
            # Log the error with context and return a safe message
            traceback_details = traceback.format_exc()
            self.logger.error(f"Error executing Vector Search: {e}")
            return {
                "error": f"Error occured during Vector Search output generation:{e}, Traceback :{traceback_details}"
            }

    # -------------------------------------------------------------------------
    # Hybrid search (full text search + vector similarity)
    # -------------------------------------------------------------------------
    async def hybrid_search(
        self, question: str, filters: dict, filtered_search: str, semantic_text: str
    ) -> dict:
        """
        Combine full-text ranking (ts_rank_cd + websearch_to_tsquery) with
        vector similarity to produce a balanced relevance score.

        Args:
            question (str): Search text.
            filters (dict): Filtered results based on user selected filters
            filtered_search (str): Filters captured from user question (Filtered Vector Search)
            semantic_text (str): Core input from question for semantic search

        Returns:
            dict: {
                "sql_command": string,
                "details": List[dict]
            }

        Scoring:
            hybrid_score = 0.5 * text_rank + 0.5 * (1 - vector_distance)
            Higher hybrid_score indicates more relevance.
        """
        # Preparing parameteres
        # Normalize filters and build WHERE clause
        filters_dict = normalize_filters(filters)
        where_sql, filter_params = build_where_clause(filters_dict)

        if semantic_text is not None:
            question = semantic_text

        if filtered_search is not None:
            if where_sql and filtered_search not in where_sql:
                where_sql = where_sql + " AND " + filtered_search
            else:
                where_sql = "WHERE " + filtered_search

        params = {
            "question": question,
            "embedding": EMBEDDING,
            "hybrid_threshold": HYBRID_THRESHOLD,
        }
        params.update(filter_params)

        # Preparing Query
        query = text(
            f"""
            WITH query_embedding AS (
                SELECT google_ml.embedding(:embedding, :question) AS embed
            ),
            top_matches AS (
                SELECT *,
                    0.5 * ts_rank_cd(to_tsvector('english', combined_description),
                                     websearch_to_tsquery(:question)) +
                    0.5 * (1 - (combined_description_embedding <=> query_embedding.embed::vector)) AS hybrid_score
                FROM {ALLOYDB_SCHEMA_NAME}.{TABLE_NAME}, query_embedding
                {where_sql}
                ORDER BY hybrid_score DESC
            )
            SELECT
                productDisplayName,
                hybrid_score,
                link,
                unitPrice,
                discount,
                finalPrice,
                rating
            FROM top_matches
            WHERE hybrid_score >= :hybrid_threshold;
            """
        )

        # Uncomment the below 'query' block, if preferred approach is HYBRID SEARCH USING RECIPROCAL RANK FUSION, Reference link: https://docs.cloud.google.com/alloydb/docs/ai/run-hybrid-vector-similarity-search
        # query = f"""
        #     WITH query_embedding AS (
        #     SELECT google_ml.embedding(<EMBEDDING_MODEL>, '{question}') AS embed
        #     ),
        #     vector_search AS (
        #       SELECT *,
        #             RANK() OVER (ORDER BY combined_description_embedding <=> query_embedding.embed::vector) AS v_rank
        #       FROM {ALLOYDB_SCHEMA_NAME}.{TABLE_NAME}, query_embedding
        #     ),
        #     text_search AS (
        #       SELECT *,
        #              RANK() OVER (ORDER BY ts_rank_cd(to_tsvector('english', combined_description), websearch_to_tsquery('{question}')) DESC) AS t_rank
        #       FROM {ALLOYDB_SCHEMA_NAME}.{TABLE_NAME}
        #       WHERE to_tsvector('english', combined_description) @@ websearch_to_tsquery('{question}')
        #     ),
        #     combined AS (
        #       SELECT v.*,
        #          -- Reciprocal Rank Fusion (RRF) score
        #          COALESCE(1.0 / (60 + v.v_rank), 0.0) + COALESCE(1.0 / (60 + t.t_rank), 0.0) AS rrf_score
        #       FROM vector_search v
        #       FULL OUTER JOIN text_search t ON v.id = t.id
        #       {where_sql}
        #       ORDER BY rrf_score DESC
        #     )
        #     SELECT
        #         productDisplayName,
        #         hybrid_score,
        #         link,
        #         unitPrice,
        #         discount,
        #         finalPrice,
        #         rating
        #     FROM combined
        #     -- RRF_THRESHOLD Value to be added to config if utilised
        #     WHERE rrf_score >= <RRF_THRESHOLD>;"""

        query = query.bindparams(*(bindparam(k, value=v) for k, v in params.items()))
        compiled = query.compile(
            dialect=self.engine.dialect, compile_kwargs={"literal_binds": True}
        )
        sql_string = str(compiled)

        try:
            with self.engine.connect() as connection:
                self.logger.info("Database connection established for hybrid search.")
                self.logger.info(f"Executing the query for Hybrid Search:{sql_string}")
                result = connection.execute(query)
                rows = result.mappings().all()

                if not rows:
                    self.logger.warning("No results returned from hybrid search.")
                    return {
                        "sql_command": sql_string,
                        "details": [],
                    }

                self.logger.info("Query executed successfully for hybrid search.")

                details = []
                for r in rows:
                    details.append(
                        {
                            "productDisplayName": r.get("productdisplayname"),
                            "link": r.get("link"),
                            "unitPrice": r.get("unitprice"),
                            "discount": r.get("discount"),
                            "finalPrice": r.get("finalprice"),
                            "rating": r.get("rating"),
                        }
                    )
                return {"sql_command": sql_string, "details": details}

        except Exception as e:
            traceback_details = traceback.format_exc()
            self.logger.error(f"Error executing Hybrid Search: {e}")
            return {
                "error": f"Error occured during Hybrid Search output generation:{e}",
                "traceback": traceback_details,
            }

    # -------------------------------------------------------------------------
    # NL-to-SQL search through NLA
    # -------------------------------------------------------------------------
    async def nltosql_search(self, question: str, filters: dict) -> dict:
        """
        Convert natural language into SQL via NLA Agents, execute it,
        and return product details based on the generated filter.

        Flow:
            1) Use Gemini Data Analytics API to generate SQL text.
            2) Rewrite the original SELECT to return full product columns/features for UI.

        Args:
            question (str): Natural-language query
            filters (dict): Filtered results based on user selected filters
        Returns:
            dict: {
                "sql_command": <original NL-generated SQL(string)>,
                "details": List[dict]  # full product details
            }
        """
        # Normalize filters and build WHERE clause
        filters_dict = normalize_filters(filters)
        where_sql, filter_params = build_where_clause(filters_dict)

        access_token = self.get_access_token()

        payload = {
            "prompt": question,
            "context": {
                "datasource_references": {
                    "alloydb": {
                        "database_reference": {
                            "project_id": PROJECT_ID,
                            "region": LOCATION,
                            "cluster_id": CLUSTER_ID,
                            "instance_id": INSTANCE_ID,
                            "database_id": "postgres",
                        },
                        "agent_context_reference": {"context_set_id": CONTEXT_SET_ID},
                    }
                }
            },
            "generation_options": {
                "generate_query_result": False,
                "generate_explanation": True,
            },
        }

        nla_response = requests.post(
            NLA_API,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=120,
        )
        self.logger.info("NLA RESPONSE: ", nla_response)
        if nla_response.status_code != 200:
            # if not nla_response:
            raise RuntimeError(f"queryData failed:  {nla_response.text}")

        nla_response_json = nla_response.json()
        generated_sql = nla_response_json["generatedQuery"]
        generated_sql = remove_single_line_comments(generated_sql)
        self.logger.info("Cleaned query: ", generated_sql)

        try:
            with self.engine.connect() as connection:
                self.logger.info("Database connection established for nltosql search.")

                # Take the original SELECT and replace it with a full-column SELECT
                # so that the UI gets complete product details to display while preserving filters.
                rewritten_sql = merge_where_clauses(where_sql, generated_sql)

                base_select_all = """
                SELECT
                     productDisplayName,
                     link,
                     unitPrice,
                     discount,
                     finalPrice,
                     rating
                """
                # Naive swap: replace everything from SELECT to FROM with UI fields.
                # Works when generated SQL is a single SELECT ... FROM ...
                match_from = re.search(r"\bFROM\b", rewritten_sql, flags=re.IGNORECASE)
                if match_from:
                    rewritten_sql = (
                        base_select_all + "\n" + rewritten_sql[match_from.start() :]
                    )
                # 3) Execute rewritten SQL WITH filter params
                query = text(rewritten_sql)
                query = query.bindparams(
                    *(bindparam(k, value=v) for k, v in filter_params.items())
                )
                compiled = query.compile(
                    dialect=self.engine.dialect, compile_kwargs={"literal_binds": True}
                )
                sql_string = str(compiled)
                self.logger.info(f"Executing the query for NL-to-SQL:{sql_string}")
                rows = connection.execute(query).mappings().all()

                if not rows:
                    return {"sql_command": sql_string, "details": []}

                details = []
                for r in rows:
                    details.append(
                        {
                            "productDisplayName": r.get("productdisplayname"),
                            "link": r.get("link"),
                            "unitPrice": r.get("unitprice"),
                            "discount": r.get("discount"),
                            "finalPrice": r.get("finalprice"),
                            "rating": r.get("rating"),
                        }
                    )
                self.logger.info("Query executed successfully for nltosql search.")

                return {
                    "sql_command": sql_string,  # Return the original NL-generated SQL with the filter parameters
                    "details": details,  # Return product features
                }

        except Exception as e:
            traceback_details = traceback.format_exc()
            self.logger.error(f"Error executing NL-to-SQL: {e}")
            return {
                "error": f"Error occured during NL-to-SQL output generation:{e}",
                "traceback": traceback_details,
            }

    # ---- NL to SQL through AlloyDB AI NL (alloydb_ai_nl.get_sql) ----
    #     async def nltosql_search(self, question: str, filters: dict) -> dict:
    #         """
    #         Convert natural language into SQL via AlloyDB AI NL functions, execute it,
    #         and return product details based on the generated filter.

    #         Flow:
    #             1) Use alloydb_ai_nl.get_sql(cfg, question) to generate SQL text.
    #             2) Rewrite the original SELECT to return full product columns/features for UI.

    #         Args:
    #             question (str): Natural-language query
    #             filters (dict): Filtered results based on user selected filters
    #         Returns:
    #             dict: {
    #                 "sql_command": <original NL-generated SQL(string)>,
    #                 "details": List[dict]  # full product details
    #             }
    #         """
    #         # Normalize filters and build WHERE clause
    #         filters_dict = normalize_filters(filters)
    #         where_sql, filter_params = build_where_clause(filters_dict)

    #         query = text("SELECT alloydb_ai_nl.get_sql(:config_name , :question)")

    #         try:
    #             with self.engine.connect() as connection:
    #                 self.logger.info("Database connection established for nltosql search.")
    #                 result = connection.execute(
    #                     query, {"question": question, "config_name": NLTOSQL_CONFIG}
    #                 )
    #                 rows = result.mappings().all()
    #                 if not rows:
    #                     # If the NL query returns nothing, respond consistently
    #                     return {
    #                         "sql_command": "No results found for NL-to-SQL search!",
    #                         "details": [],
    #                     }

    #                 # Extract the generated SQL from the function output
    #                 sql_command = rows[0].get("get_sql")
    #                 if not sql_command or "sql" not in sql_command:
    #                     return {
    #                         "sql_command": query,
    #                         "details": [],
    #                     }
    #                 generated_sql = sql_command["sql"]
    #                 # Take the original SELECT and replace it with a full-column SELECT
    #                 # so that the UI gets complete product details to display while preserving filters.
    #                 rewritten_sql = merge_where_clauses(where_sql, generated_sql)

    #                 base_select_all = """
    #                 SELECT
    #                      productDisplayName,
    #                      link,
    #                      unitPrice,
    #                      discount,
    #                      finalPrice,
    #                      rating
    #                 """
    #                 # Naive swap: replace everything from SELECT to FROM with UI fields.
    #                 # Works when generated SQL is a single SELECT ... FROM ...
    #                 match_from = re.search(r"\bFROM\b", rewritten_sql, flags=re.IGNORECASE)
    #                 if match_from:
    #                     rewritten_sql = (
    #                         base_select_all + "\n" + rewritten_sql[match_from.start() :]
    #                     )
    #                 # 3) Execute rewritten SQL WITH filter params
    #                 query = text(rewritten_sql)
    #                 query = query.bindparams(
    #                     *(bindparam(k, value=v) for k, v in filter_params.items())
    #                 )
    #                 compiled = query.compile(
    #                     dialect=self.engine.dialect, compile_kwargs={"literal_binds": True}
    #                 )
    #                 sql_string = str(compiled)
    #                 self.logger.info(f"Executing the query for NL-to-SQL:{sql_string}")
    #                 rows = connection.execute(query).mappings().all()
    #                 details = []
    #                 for r in rows:
    #                     details.append(
    #                         {
    #                             "productDisplayName": r.get("productdisplayname"),
    #                             "link": r.get("link"),
    #                             "unitPrice": r.get("unitprice"),
    #                             "discount": r.get("discount"),
    #                             "finalPrice": r.get("finalprice"),
    #                             "rating": r.get("rating"),
    #                         }
    #                     )
    #                 self.logger.info("Query executed successfully for nltosql search.")

    #                 return {
    #                     "sql_command": sql_string,  # Return the original NL-generated SQL with the filter parameters
    #                     "details": details,  # Return product features
    #                 }

    #         except Exception as e:
    #             traceback_details = traceback.format_exc()
    #             self.logger.error(f"Error executing NL-to-SQL: {e}")
    #             return {
    #                 "error": f"Error occured during NL-to-SQL output generation:{e}",
    #                 "traceback": traceback_details,
    #             }

    async def ai_if_case(self, sql_query: str, filters: dict) -> dict:
        """Find products when semantic filtering is required.
        Uses `ai.if` to find relevant products

        Args:
            sql_query (str): The SQL query to be executed using AI.IF.
            filters (dict): Filtered results based on user selected filters
        Returns:
            dict: {
                "sql_command": string,
                "details": List[dict]
            }

        """
        filters_dict = normalize_filters(filters)
        where_sql, filter_params = build_where_clause(filters_dict)
        sql_query = merge_filter_where(sql_query, where_sql)
        query = text(sql_query)
        query = query.bindparams(
            *(bindparam(k, value=v) for k, v in filter_params.items())
        )
        compiled = query.compile(
            dialect=self.engine.dialect, compile_kwargs={"literal_binds": True}
        )
        sql_string = str(compiled)

        try:
            with self.engine.connect() as connection:
                self.logger.info("Database connection established for AI.IF search.")
                result = connection.execute(query)
                rows = result.mappings().all()

                if not rows:
                    # If the query returns nothing, respond consistently
                    return {"sql_command": sql_string, "details": []}
                details = []
                for r in rows:
                    details.append(
                        {
                            "productDisplayName": r.get("productdisplayname"),
                            "link": r.get("link"),
                            "unitPrice": r.get("unitprice"),
                            "discount": r.get("discount"),
                            "finalPrice": r.get("finalprice"),
                            "rating": r.get("rating"),
                        }
                    )
                return {"sql_command": sql_string, "details": details}

        except Exception as e:
            traceback_details = traceback.format_exc()
            self.logger.error(f"Error executing AI.IF search case: {e}")
            return {
                "error": f"Error occured during AI.IF output generation:{e}",
                "traceback": traceback_details,
            }


class IdentifySearchType:
    def __init__(self, question, engine):
        self.user_query = question
        self.engine = engine

    def search_strategy_prompt(self):
        """
        Decides search strategy, SQL Constraints for Vector/Hybrid Search and SQL query for ai.if
        """
        system_instruction = """
        You are the Decision Engine for a retail product Search System backed by AlloyDB for PostgreSQL with AlloyDB AI.

        ============================================================
        0) CATALOG ATTRIBUTE GATE
        ============================================================
        Process the USER QUERY only if it can point at least one of:
        id, gender, masterCategory, subCategory, articleType, baseColour, season, year, usage, productDisplayName, brand, unitPrice, discount, finalPrice, rating, stockCode, stockStatus

        If NONE are detected → return this JSON and STOP:

        {
        "selected_strategy": "reject",
        "reasoning": "Question is irrelevant to the available data",
        "message": "No results to display",
        "parameters": { "raw_query": "<original>" },
        "decision_path": ["gate:failed"]
        }

        ============================================================
        1) SEARCH STRATEGY DECISION RULES
        ============================================================

        Choose EXACTLY ONE of the strategies below.

        ------------------------------------------------------------
        A) NL‑TO‑SQL (Natural Language → SQL)
        ------------------------------------------------------------
        USE WHEN:
        - The question clearly asks for structured SQL-like answers:
        counts, aggregations, filters, exact lookups, listing rows, ordering, grouping etc.
        - The question asks for a category directly or by synonyms of category
        
        EXAMPLES:
        - "shirts with price less than 20$"
        - "List all items with stock code 123ABC"

        OUTPUT: selected_strategy = "nl_to_sql"

        ------------------------------------------------------------
        B) VECTOR SEARCH (Pure Semantic Search)
        ------------------------------------------------------------
        USE WHEN:
        - Meaning matters more than exact keywords.
        - User describes concepts, style, looks, or synonyms of catalog attributes.
        - There may be broad category mentions (articleType/subCategory) but the intent is semantic similarity rather than exact text matching.
        
        EXAMPLES:
        - "dresses for babies"                     
        - "Hoodies for Men"           
        - "office-wear shoes for Women under 20$"

        OUTPUT: selected_strategy = "vector"

        ------------------------------------------------------------
        C) HYBRID SEARCH (Vector + Keyword/Text Search)
        ------------------------------------------------------------
        USE WHEN:
        - Query contains BOTH semantic meaning AND which require full text search, for example part of product names or product descriptions
        (brand names, model lines, product families, ids, or other catalog attributes)

        OUTPUT: selected_strategy = "hybrid"
        
        EXAMPLES:
        - "Levis Men Knit Crew socks"
        - "Cotton leggings"
        

        ------------------------------------------------------------
        D) AI.IF (Semantic Filtering inside SQL)
        ------------------------------------------------------------
        USE ONLY IF:
        - The query does NOT fit NL‑to‑SQL, Hybrid, or Vector
        BUT
        - The user wants semantic filtering inside SQL at row level.

        IMPORTANT — Prompt Shape:
        - Convert the user request into a single YES/NO question applied to each row.
        - Template:
        "<user question rephrased yes/no question based on the user intent>
        Here is the product description:"
        - Keep the question concise and unambiguous.

        EXAMPLES (User → Question Template):
        - "Find men's casual leather belts under $20"
        → "Is this a men's casual leather belt priced at or below 20 Dollars?"
        - "Indian brand shirts (avoid checked patterns)"
        → "Is this an indian brand shirt without checked pattern?"

        OUTPUT: selected_strategy = "ai.if"

        REFERENCE URL:
        - AI.IF semantic filtering operator
        https://docs.cloud.google.com/alloydb/docs/ai/evaluate-semantic-queries-ai-operators

        ------------------------------------------------------------
        E) REJECT — If NOTHING fits (including NOT suitable for AI.IF)
        ------------------------------------------------------------
        USE WHEN:
        - Query is off-domain (not about products), or
        - Even AI.IF cannot apply (no semantic filter on product data is possible).

        OUTPUT:
        {
        "selected_strategy": "reject",
        "reasoning": "User question is inappropriate to the dataset or is unsupported, so unable to provide the answer!",
        "message": "No results to display",
        "parameters": { "raw_query": "<original>" },
        "decision_path": ["gate:passed","strategy:none","ai.if:not_applicable","reject"]
        }

        ============================================================
        2) PRIORITY ORDER
        ============================================================
        1. If mostly meaning → Vector.
        2. If semantic + keywords → Hybrid.
        3. Prefer NL‑to‑SQL if fully solvable with exact SQL only.
        4. If none fit but semantic filter in SQL helps → AI.IF.
        5. Else → Reject.

        ============================================================
        3) PARAMETERS (semantic_text & sql_constraints)
        ============================================================

        When generating "parameters.semantic_text" and "parameters.sql_constraints",
        use the following STRICT TEMPLATE:

        You must convert the USER QUERY into:

        1) semantic_text
        - A compact semantic phrase
        - Contains ONLY the core product/entity
        - NO colors, prices, brands, gender, season, or other attributes


        2) sql_constraints
        - DO NOT INCLUDE attributes or text already present in semantic_text
        - A valid PostgreSQL WHERE predicate WITHOUT the leading "WHERE"
        - Contains ALL structured filters or attributes extracted from the user query except the core entity captured as semantic text
        - Use ONLY the catalog attributes, for example:
            - Colors points to baseColour ILIKE '%<colour>%'
            - Brands points to brand ILIKE '%<brand>%' (search by first word)
            - Gender points to gender = 'Men'/'Women'/'Boys'/'Girls'/'Unisex'
            - Season points to season ILIKE '%<season>%'
            - Usage or Wear points to usage ILIKE '%<usage>%'
            - Products points to productDisplayName ILIKE '%<product name>%'
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

        The final response MUST be a single JSON object with the exact shape:

        {
        "selected_strategy": "vector" | "hybrid" | "nl_to_sql" | "ai.if" | "reject",
        "reasoning": "Concise explanation on why this search strategy is selected",
        "parameters": {
            "semantic_text": "<core semantic phrase without sql_constraints or filters>",
            "sql_constraints": "<valid SQL predicate>",
            "raw_query": "<user_query>",
            "question_template": "<ONLY WHEN selected_strategy = 'ai.if'>"
        },
        "decision_path": ["gate:<passed|failed>", "strategy:<chosen|none>", "ai.if:<applicable|not_applicable>"],
        "sql_query": "<INCLUDE THIS KEY **ONLY** WHEN selected_strategy = 'ai.if'. Omit this key for all other strategies.>"
        }

        ============================================================
        5) HOW TO COMPOSE 'sql_query' WHEN selected_strategy = "ai.if"
            (ARRAY-BASED, QUESTION STYLE)
        ============================================================

        - Table: alloydb_usecase.fashion_products
        - Always pre-filter with a base CTE that applies explicit constraints (e.g., gender, brand, numeric ranges).
        - Use {{sql_constraints}}
        - Use combined_description to form the row text.
        - Build a single YES/NO question string from the user query, stored as {{question_template}}.
        - The ai.if operator returns booleans that can be correlated per row.
        - Use the array-based batch evaluation pattern and correlate ids back to rows via arrays.

        Example shape (adapt filters to your parsed constraints):

        WITH base AS (
        SELECT
            id, productDisplayName, brand, link, unitPrice, discount, finalPrice, rating,
            combined_description
        FROM alloydb_usecase.fashion_products
        <Apply structured constraints detected from the user query: {{sql_constraints}} if not None using WHERE>
        ),
        prompts AS (
        SELECT
            id,
            (
            {{question_template}} || E'\n' ||
            'Here is the product description: ' || combined_description
            ) AS prompt
        FROM base
        ),
        all_prompts AS (
        SELECT
            ARRAY_AGG(id ORDER BY id) AS ids,
            ai.if(prompts => ARRAY_AGG(prompt ORDER BY id)) AS results
        FROM prompts
        ),
        correlated_results AS (
        SELECT
            all_prompts.ids[i]     AS id,
            all_prompts.results[i] AS keep_row
        FROM all_prompts,
            generate_series(1, array_length(all_prompts.ids, 1)) AS i
        )
        SELECT
        b.productDisplayName, b.brand, b.link, b.unitPrice, b.discount, b.finalPrice, b.rating,
        b.combined_description
        FROM base b
        JOIN correlated_results cr
        ON cr.id = b.id
        WHERE cr.keep_row = TRUE;

        ============================================================
        6) SAFETY RULES
        ============================================================
        - Never fabricate attributes or external facts.
        - If the question is off-topic (weather, politics, medical advice, etc.) → reject.
        """
        prompt = f"""
        {system_instruction}
        USER QUERY: "{self.user_query}"
        """
        return prompt

    def _parse_ai_generate_payload(self, payload):
        """
        Converts the raw ai.generate output into a Python dict.
        Handles Markdown code fences (```json ... ``` or ``` ... ```), trims whitespace,
        and raises clear errors if decoding fails.
        """
        if isinstance(payload, dict):
            return payload

        if payload is None:
            raise ValueError("ai.generate returned NULL payload")

        s = str(payload).strip()

        # Strip surrounding triple backticks with optional language tag (e.g., ```json ... ``` or ``` ... ```)
        # Resilient to whitespace and no-newline cases.
        m = re.match(
            r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", s, flags=re.DOTALL | re.IGNORECASE
        )
        if m:
            s = m.group(1).strip()

        # If there is extra text around the JSON (rare), extract from first '{' to last '}'
        if not (s.startswith("{") and s.rstrip().endswith("}")):
            start = s.find("{")
            end = s.rfind("}")
            if start != -1 and end != -1 and end > start:
                s = s[start : end + 1].strip()

        # Finally parse strict JSON
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            preview = s[:300]
            raise ValueError(
                f"Failed to decode ai.generate JSON: {e}; preview={preview!r}"
            ) from e

        if not isinstance(obj, dict):
            raise ValueError(
                f"Decoded JSON is not an object: {type(obj)}; value={obj!r}"
            )

        return obj

    def get_search_type(
        self,
    ) -> Dict[str, Any]:
        """
        Executes a search query on AlloyDB using Vector Search, Hybrid Search and NL to SQL

        Args:
            search_type (str): Type of search to perform. Must be one of:
                - "vector": Uses embedding similarity.
                - "hybrid": Combines full-text search and vector similarity.
                - "nltosql": Converts natural language to SQL.
                - "ai.if": Involves semantic filtering
            question (str): The natural language query to be processed.

        Returns:
            Dict[str, Any]: Structured result:
                {
                    "search_strategy": str,
                    "reasoning": str,
                    "sql_command": str,
                    "details": List[dict]
                }
        """

        with self.engine.connect() as conn:
            # Prompt to identify search strategy
            prompt = self.search_strategy_prompt()
            determine_search_sql = text("SELECT ai.generate(prompt => :prompt)")
            result = conn.execute(determine_search_sql, {"prompt": prompt})

            # Scalar is cleaner for single-value SELECTs
            payload = result.scalar()
            if payload is None:
                raise RuntimeError("ai.generate returned NULL/no response")

            # Sanitize + parse JSON (always)
            decision = self._parse_ai_generate_payload(payload)

            # Selected search mode
            mode = decision.get("selected_strategy")

            # Reasoning behind identifying search strategy
            reason = decision.get("reasoning")

            # if mode == "reject":
            #     return "User question not related to available data!!!"

        return {"mode": mode, "reason": reason, "decision": decision}
