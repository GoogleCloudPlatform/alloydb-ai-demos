from __future__ import annotations
from typing import Dict, Any, Tuple, List
from src.agents.tools import get_vector_retriever
from src.utils.broadcast_decorator import status_broadcast

# Initialize a retriever for policy-related documents.
# Configuration:
#   - table: 'docs' (vector store table)
#   - column: 'embedding' (vector column)
#   - k: 4 (retrieve top 4 most relevant documents)
_retriever = None


def get_policy_retriever(engine):
    global _retriever
    if _retriever is None:
        _retriever = get_vector_retriever(engine, table="docs", column="embedding", k=4)
    return _retriever


@status_broadcast("Policy Agent is working")
async def policy_check(
    broadcast, engine, query: str
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """
    Retrieves policy constraints and supporting citations relevant to a given query.

    This function uses a vector retriever to fetch top-k policy documents based on
    semantic similarity to the query. It then extracts metadata for citations and
    returns a predefined set of constraints for replenishment decisions.

    Args:
        broadcast: Orchestration or messaging object used by the status decorator.
        query (str): Natural language query describing the policy context (e.g.,
            "Caps & substitution for SKU123").

    Returns:
        Tuple[Dict[str, Any], List[Dict[str, str]]]:
            - constraints (Dict[str, Any]): Policy rules applied to replenishment, e.g.:
                * max_single_po (float): Maximum allowed PO value.
                * allow_substitution (bool): Whether substitution is permitted.
                * substitution_scope (str): Scope for substitution (e.g., same_category).
            - citations (List[Dict[str, str]]): Extracted metadata from retrieved docs:
                * source (str): URL or reference source.
                * doc_type (str): Document classification (policy, guideline, etc.).
                * snippet (str): First 220 characters of the document content.
    """

    # -------------------------------------------------------------------------
    # Step 1: Retrieve top-k documents relevant to the policy query.
    # Each document includes metadata and page content for citation extraction.
    # -------------------------------------------------------------------------
    get_policy_retriever(engine)
    docs = _retriever.invoke(query)

    # -------------------------------------------------------------------------
    # Step 2: Build citation list from retrieved documents.
    # For each doc:
    #   - source_url: origin of the document (default empty string if missing).
    #   - doc_type: classification of the document (default empty string).
    #   - snippet: first 220 characters of page content for quick reference.
    # -------------------------------------------------------------------------
    citations = [
        {
            "source": d.metadata.get("source_url", ""),
            "doc_type": d.metadata.get("doc_type", ""),
            "snippet": (d.page_content or "")[:220],
        }
        for d in docs
    ]

    # -------------------------------------------------------------------------
    # Step 3: Define static policy constraints.
    # These values could be dynamically derived from retrieved docs in a
    # production implementation.
    # -------------------------------------------------------------------------
    constraints = {
        "max_single_po": 25000.0,
        "allow_substitution": True,
        "substitution_scope": "same_category",
    }
    return constraints, citations


# @status_broadcast("Policy Agent is working")
# async def policy_check(
#     broadcast, engine, query: str
# ) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:

#     global _retriever

#     # 1. Initialization must be awaited if get_vector_retriever is async
#     if _retriever is None:
#         # Assuming you updated get_vector_retriever to be 'async def'
#         _retriever = await get_vector_retriever(engine, table="docs", column="embedding", k=4)

#     # 2. Retrieval must be awaited and ideally use the async 'ainvoke' method
#     # This prevents blocking the FastAPI event loop and handles the coroutine
#     docs = await _retriever.ainvoke(query)

#     # 3. Citation Extraction (Rest of the code remains the same)
#     citations = [
#         {
#             "source": d.metadata.get("source_url", ""),
#             "doc_type": d.metadata.get("doc_type", ""),
#             "snippet": (d.page_content or "")[:220],
#         }
#         for d in docs
#     ]

#     constraints = {
#         "max_single_po": 25000.0,
#         "allow_substitution": True,
#         "substitution_scope": "same_category",
#     }
#     return constraints, citations
